"""Structured reads. These calls do not choose the packet outcome. decide.py does that."""

import json

from prior_auth.llm import load_prompt, parse_model
from prior_auth.schemas import (
    Chart,
    Guideline,
    LeafScore,
    Pathway,
    PathwayProposal,
    ScoreBatch,
)
from prior_auth.trim import clip


def extract_guideline(markdown: str) -> Guideline:
    return parse_model(
        [
            {"role": "system", "content": load_prompt("guideline.md")},
            {"role": "user", "content": "GUIDELINE:\n\n" + clip(markdown, 120_000)},
        ],
        Guideline,
    )


def extract_chart(markdown: str) -> Chart:
    return parse_model(
        [
            {"role": "system", "content": load_prompt("chart.md")},
            {"role": "user", "content": "CHART:\n\n" + clip(markdown, 120_000)},
        ],
        Chart,
    )


def propose_pathway(guideline: Guideline, chart: Chart) -> PathwayProposal:
    payload = {
        "ordered_procedures": [item.model_dump() for item in chart.planned_procedures],
        "pathways": [
            {
                "id": pathway.id,
                "name": pathway.name,
                "procedure_names": pathway.procedure_names,
                "cpt_codes": pathway.cpt_codes,
            }
            for pathway in guideline.pathways
        ],
        "non_covered": [item.model_dump() for item in guideline.non_covered],
    }
    return parse_model(
        [
            {"role": "system", "content": load_prompt("propose.md")},
            {"role": "user", "content": json.dumps(payload, indent=2)},
        ],
        PathwayProposal,
    )


def score_pathway(pathway: Pathway, chart: Chart, chart_markdown: str) -> list[LeafScore]:
    criteria: list[dict[str, str]] = []
    for leaf in pathway.all_of:
        criteria.append({"id": leaf.id, "group": "all_of", "text": leaf.text})
    for group in pathway.any_of_groups:
        for leaf in group.leaves:
            criteria.append({"id": leaf.id, "group": f"any_of:{group.name}", "text": leaf.text})
        for option in group.all_of_options:
            for leaf in option.leaves:
                criteria.append(
                    {
                        "id": leaf.id,
                        "group": f"any_of:{group.name} / all_of:{option.name}",
                        "text": leaf.text,
                    }
                )
    for leaf in pathway.exclusions:
        criteria.append({"id": leaf.id, "group": "exclusion", "text": leaf.text})
    if not criteria:
        return []

    payload = {
        "criteria": criteria,
        "extracted_facts": [fact.model_dump() for fact in chart.facts],
        "chart": clip(chart_markdown, 120_000),
    }
    batch = parse_model(
        [
            {"role": "system", "content": load_prompt("score.md")},
            {"role": "user", "content": json.dumps(payload, indent=2)},
        ],
        ScoreBatch,
    )
    return batch.scores
