"""Render the clinician packet from a determination.

The packet is a view of determination.json. It does not re-score criteria.
"""

import html

from prior_auth.schemas import CriterionResult, Determination, Outcome, PlannedProcedure

_HEADINGS = {
    Outcome.DO_NOT_SUBMIT: "Do not submit",
    Outcome.FIX_BEFORE_SUBMIT: "Fix before submit",
    Outcome.READY_FOR_REVIEW: "Ready for review",
}

_STATUS_LABELS = {
    "met": "Met",
    "not_met": "Not met",
    "not_documented": "Not documented",
    "not_applicable": "Not applicable",
}


def render_markdown(determination: Determination) -> str:
    heading = _HEADINGS[determination.outcome]
    lines = [
        heading,
        "",
        determination.outcome_reason,
        "",
        "## Case",
        "",
        f"- Patient: {_or_unknown(determination.patient_name)}",
        f"- Chart payer: {_or_unknown(determination.payer_on_chart)}",
        f"- Guideline payer: {_or_unknown(determination.guideline_payer)}",
        f"- Policy: {_policy(determination)}",
        "- Ordered procedure:",
    ]
    procedures = _procedure_lines(determination.ordered_procedures)
    if procedures:
        lines.extend(f"  - {line}" for line in procedures)
    else:
        lines.append("  - None found in the chart")
    lines.extend(["", "## Pathway", ""])
    if determination.matched_pathway_name:
        lines.append(f"- Matched: {determination.matched_pathway_name}")
    else:
        lines.append("- Matched: none")
    if determination.pathway_match_note:
        lines.append(f"- How it was matched: {determination.pathway_match_note}")
    lines.extend(["", "## Criteria", ""])
    if determination.criteria:
        for row in determination.criteria:
            lines.extend(_criterion_markdown(row))
    else:
        lines.append("No criteria were scored. The ordered procedure did not match a covered pathway.")
    lines.extend(["", "## What to add before submitting", ""])
    lines.extend(_bullets(determination.missing_items, "Nothing to add from this review."))
    lines.extend(["", "## Denial risks", ""])
    lines.extend(_bullets(determination.denial_risks, "No hard denial risk was identified."))
    lines.extend(["", "## Documents this policy asks for", ""])
    if not determination.matched_pathway_name and determination.required_documents:
        lines.append(
            "These documents belong to this policy. They may not apply to the ordered procedure."
        )
        lines.append("")
    lines.extend(_bullets(determination.required_documents, "The policy did not list required documents."))
    lines.extend(["", "## Letter of medical necessity", ""])
    if determination.letter:
        lines.append(determination.letter)
    else:
        lines.append(
            "Not drafted. A letter is written only when every required criterion is supported by a quote from the chart."
        )
    lines.extend(["", "## Warnings", ""])
    lines.extend(_bullets(determination.warnings, "None."))
    lines.extend(
        [
            "",
            "## Reviewer checklist",
            "",
            "- Confirm the ordered procedure, CPT, and site against the chart.",
            "- Open each quote in the chart and confirm it was not taken out of context.",
            "- This packet does not submit the request to the payer.",
            "",
        ]
    )
    return "\n".join(lines)


def render_html(determination: Determination) -> str:
    heading = _HEADINGS[determination.outcome]
    css_class = determination.outcome.value
    criteria = (
        "\n".join(_criterion_html(row) for row in determination.criteria)
        if determination.criteria
        else "<p>No criteria were scored. The ordered procedure did not match a covered pathway.</p>"
    )
    document_note = ""
    if not determination.matched_pathway_name and determination.required_documents:
        document_note = (
            "<p>These documents belong to this policy. They may not apply to the ordered procedure.</p>"
        )
    letter = (
        f"<pre>{html.escape(determination.letter)}</pre>"
        if determination.letter
        else "<p>Not drafted. A letter is written only when every required criterion is supported by a quote from the chart.</p>"
    )
    procedures = _procedure_lines(determination.ordered_procedures) or ["None found in the chart"]
    procedure_html = "".join(f"<li>{html.escape(line)}</li>" for line in procedures)
    match_note = (
        f"<p>{html.escape(determination.pathway_match_note)}</p>"
        if determination.pathway_match_note
        else ""
    )
    matched = determination.matched_pathway_name or "none"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(heading)} — prior authorization review</title>
  <style>
    body {{ font-family: system-ui, sans-serif; color: #1c1917; margin: 0; background: #fafaf9; }}
    main {{ max-width: 760px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }}
    h1 {{ font-size: 1.8rem; margin: 0 0 0.75rem; }}
    h2 {{ font-size: 1.1rem; margin: 2rem 0 0.5rem; }}
    .banner {{ padding: 0.9rem 1rem; border-radius: 8px; }}
    .do_not_submit {{ background: #fee2e2; }}
    .fix_before_submit {{ background: #fef3c7; }}
    .ready_for_review {{ background: #dcfce7; }}
    .card {{ padding: 0.75rem 0; border-top: 1px solid #e7e5e4; }}
    .status {{ font-weight: 700; }}
    blockquote {{ margin: 0.4rem 0; padding-left: 0.8rem; border-left: 3px solid #d6d3d1; white-space: pre-wrap; }}
    pre {{ white-space: pre-wrap; font-family: inherit; background: #fff; padding: 1rem; border: 1px solid #e7e5e4; }}
    .meta {{ color: #57534e; }}
  </style>
</head>
<body>
<main>
  <div class="banner {css_class}">
    <h1>{html.escape(heading)}</h1>
    <p>{html.escape(determination.outcome_reason)}</p>
  </div>
  <h2>Case</h2>
  <ul>
    <li>Patient: {html.escape(_or_unknown(determination.patient_name))}</li>
    <li>Chart payer: {html.escape(_or_unknown(determination.payer_on_chart))}</li>
    <li>Guideline payer: {html.escape(_or_unknown(determination.guideline_payer))}</li>
    <li>Policy: {html.escape(_policy(determination))}</li>
    <li>Ordered procedure:<ul>{procedure_html}</ul></li>
  </ul>
  <h2>Pathway</h2>
  <p>Matched: {html.escape(matched)}</p>
  {match_note}
  <h2>Criteria</h2>
  {criteria}
  <h2>What to add before submitting</h2>
  {_html_list(determination.missing_items, "Nothing to add from this review.")}
  <h2>Denial risks</h2>
  {_html_list(determination.denial_risks, "No hard denial risk was identified.")}
  <h2>Documents this policy asks for</h2>
  {document_note}
  {_html_list(determination.required_documents, "The policy did not list required documents.")}
  <h2>Letter of medical necessity</h2>
  {letter}
  <h2>Warnings</h2>
  {_html_list(determination.warnings, "None.")}
  <h2>Reviewer checklist</h2>
  <ul>
    <li>Confirm the ordered procedure, CPT, and site against the chart.</li>
    <li>Open each quote in the chart and confirm it was not taken out of context.</li>
    <li>This packet does not submit the request to the payer.</li>
  </ul>
</main>
</body>
</html>
"""


def _criterion_markdown(row: CriterionResult) -> list[str]:
    lines = [
        f"### {row.text}",
        "",
        f"- Group: {_group_label(row.group)}",
        f"- Status: {_STATUS_LABELS.get(row.status.value, row.status.value)}",
    ]
    spans = [span.strip() for span in row.quote.split("\n") if span.strip()]
    if spans:
        lines.extend(f'- Quote: "{span}"' for span in spans)
    else:
        lines.append("- Quote: none")
    if row.section:
        lines.append(f"- Source: {row.section}")
    if row.rationale:
        lines.append(f"- Note: {row.rationale}")
    lines.append("")
    return lines


def _criterion_html(row: CriterionResult) -> str:
    spans = [span.strip() for span in row.quote.split("\n") if span.strip()]
    quote = (
        "".join(f"<blockquote>{html.escape(span)}</blockquote>" for span in spans)
        if spans
        else "<p class=\"meta\">No quote</p>"
    )
    source = f"<p class=\"meta\">Source: {html.escape(row.section)}</p>" if row.section else ""
    note = f"<p class=\"meta\">{html.escape(row.rationale)}</p>" if row.rationale else ""
    return (
        "<article class=\"card\">"
        f"<h3>{html.escape(row.text)}</h3>"
        f"<p class=\"status\">{html.escape(_STATUS_LABELS.get(row.status.value, row.status.value))}</p>"
        f"<p class=\"meta\">{html.escape(_group_label(row.group))}</p>"
        f"{quote}{source}{note}"
        "</article>"
    )


def _procedure_lines(procedures: list[PlannedProcedure]) -> list[str]:
    lines: list[str] = []
    for procedure in procedures:
        bits = [procedure.name or "Unnamed procedure"]
        if procedure.cpt_codes:
            bits.append("CPT " + ", ".join(procedure.cpt_codes))
        if procedure.laterality:
            bits.append(procedure.laterality)
        if procedure.indication:
            bits.append(procedure.indication)
        lines.append(" — ".join(bits))
    return lines


def _policy(determination: Determination) -> str:
    title = determination.guideline_title
    policy_id = determination.guideline_policy_id
    if title and policy_id:
        return f"{title} ({policy_id})"
    return title or policy_id or "Unknown policy"


def _group_label(group: str) -> str:
    if group == "all_of":
        return "Required"
    if group == "exclusion":
        return "Exclusion"
    if group.startswith("any_of:"):
        rest = group.split(":", 1)[1]
        marker = " / all_of:"
        if marker in rest:
            parent, option = rest.split(marker, 1)
            return f"One of: {parent}; all of: {option}"
        return f"One of: {rest}"
    return group


def _or_unknown(value: str) -> str:
    return value.strip() or "Not stated"


def _bullets(items: list[str], empty: str) -> list[str]:
    if not items:
        return [f"- {empty}"]
    return [f"- {item}" for item in items]


def _html_list(items: list[str], empty: str) -> str:
    rows = items or [empty]
    return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in rows) + "</ul>"
