"""Turn OCR markdown into guideline and chart records."""

from prior_auth.llm import load_prompt, parse_model
from prior_auth.schemas import Chart, Guideline
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
