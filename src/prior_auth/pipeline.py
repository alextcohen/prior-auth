"""Run OCR, extraction, scoring, and rendering for one chart-guideline pair."""

import sys
from pathlib import Path

from prior_auth.decide import (
    decide,
    match_pathway,
    merge_rescored,
    needs_model_proposal,
    normalize_guideline,
    ungrounded_scores,
)
from prior_auth.errors import PriorAuthError
from prior_auth.extract import extract_chart, extract_guideline, propose_pathway, rescore_quotes, score_pathway
from prior_auth.ocr import ocr_pdf
from prior_auth.render import render_html
from prior_auth.trim import trim_guideline


def run_case(guideline_path: Path, chart_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    _log(f"Reading guideline {guideline_path.name}")
    guideline_markdown = ocr_pdf(guideline_path)
    _log(f"Reading chart {chart_path.name}")
    chart_markdown = ocr_pdf(chart_path)
    _write(out_dir / "ocr" / "guideline.md", guideline_markdown)
    _write(out_dir / "ocr" / "chart.md", chart_markdown)

    guideline_for_model, trimmed = trim_guideline(guideline_markdown)
    _log("Extracting coverage criteria")
    guideline = normalize_guideline(extract_guideline(guideline_for_model))
    _write_model(out_dir / "guideline.json", guideline)

    _log("Extracting chart facts")
    chart = extract_chart(chart_markdown)
    _write_model(out_dir / "chart.json", chart)

    proposed_id = None
    extra_warnings: list[str] = []
    if trimmed:
        extra_warnings.append(
            "Guideline text was shortened before extraction because it exceeded the context budget. "
            "Reference lists were dropped first."
        )
    if needs_model_proposal(guideline, chart):
        _log("Matching the ordered procedure to a pathway")
        proposal = propose_pathway(guideline, chart)
        proposed_id = proposal.pathway_id.strip() or None
        extra_warnings.append(f"Pathway proposal: {proposal.reason}")

    peeked = match_pathway(guideline, chart, proposed_id)
    scores = []
    if peeked.pathway is not None and peeked.non_covered is None:
        _log(f"Scoring criteria for {peeked.pathway.name}")
        scores = score_pathway(peeked.pathway, chart, chart_markdown)
        failed = ungrounded_scores(scores, chart_markdown)
        if failed:
            _log(f"Rechecking {len(failed)} quote(s) that were not copied from the chart")
            try:
                retried = rescore_quotes(peeked.pathway, chart, chart_markdown, failed)
            except PriorAuthError as exc:
                extra_warnings.append(f"Quote recheck failed: {exc}")
            else:
                scores = merge_rescored(scores, retried, chart_markdown)

    determination = decide(
        guideline,
        chart,
        chart_markdown,
        scores,
        proposed_pathway_id=proposed_id,
    )
    determination.warnings = [*extra_warnings, *determination.warnings]
    _write_model(out_dir / "determination.json", determination)
    packet = out_dir / "packet.html"
    _write(packet, render_html(determination))
    _log(f"Wrote {packet}")
    return packet


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _write_model(path: Path, model) -> None:
    _write(path, model.model_dump_json(indent=2))


def _log(message: str) -> None:
    print(message, file=sys.stderr)
