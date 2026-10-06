"""Render the clinician packet from a determination.

The packet is a view of determination.json. It does not re-score criteria.
"""

import html
from collections import Counter

from prior_auth.schemas import CriterionResult, Determination, LeafStatus, Outcome, PlannedProcedure

_HEADINGS = {
    Outcome.DO_NOT_SUBMIT: "Do not submit",
    Outcome.FIX_BEFORE_SUBMIT: "Fix before submit",
    Outcome.READY_FOR_REVIEW: "Ready for review",
}

_LETTER_NOTE = (
    "This draft is for staff review before submission. "
    "It does not add facts beyond the quotes above, and it is not an approval."
)

_STATUS_LABELS = {
    "met": "Met",
    "not_met": "Not met",
    "not_documented": "Not documented",
    "not_applicable": "Not applicable",
}

_STATUS_MARK = {
    "met": "✓",
    "not_met": "✕",
    "not_documented": "!",
    "not_applicable": "–",
}

def letter_body(letter: str) -> str:
    """The copyable request. The staff note is rendered beside it, not inside it."""
    return letter.replace(f"\n\n{_LETTER_NOTE}", "").replace(_LETTER_NOTE, "").strip()


def render_markdown(determination: Determination) -> str:
    heading = _HEADINGS[determination.outcome]
    lines = [heading, "", determination.outcome_reason, ""]
    lines.extend(_action_markdown(determination))
    lines.extend(
        [
            "## Case",
            "",
            f"- Patient: {_or_unknown(determination.patient_name)}",
            f"- Chart payer: {_or_unknown(determination.payer_on_chart)}",
            f"- Guideline payer: {_or_unknown(determination.guideline_payer)}",
            f"- Policy: {_policy(determination)}",
            "- Ordered procedure:",
        ]
    )
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
    presented = _present_all(determination.criteria)
    tally = _tally(presented)
    if tally:
        lines.extend([tally, ""])
    if determination.criteria:
        for row, presentation in zip(determination.criteria, presented, strict=True):
            lines.extend(_criterion_markdown(row, presentation))
    else:
        lines.append("No criteria were scored. The ordered procedure did not match a covered pathway.")
        lines.append("")
    lines.extend(["## Documents this policy asks for", ""])
    if not determination.matched_pathway_name and determination.required_documents:
        lines.append(
            "These documents belong to this policy. They may not apply to the ordered procedure."
        )
        lines.append("")
    lines.extend(_bullets(determination.required_documents, "The policy did not list required documents."))
    lines.extend(["", "## Letter of medical necessity", ""])
    if determination.letter:
        lines.append(letter_body(determination.letter))
        lines.extend(["", _LETTER_NOTE])
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
    presented = _present_all(determination.criteria)
    criteria = (
        "\n".join(
            _criterion_html(row, presentation)
            for row, presentation in zip(determination.criteria, presented, strict=True)
        )
        if determination.criteria
        else "<p>No criteria were scored. The ordered procedure did not match a covered pathway.</p>"
    )
    document_note = ""
    if not determination.matched_pathway_name and determination.required_documents:
        document_note = (
            "<p class=\"meta\">These documents belong to this policy. They may not apply to the ordered procedure.</p>"
        )
    letter = (
        f"<pre>{html.escape(letter_body(determination.letter))}</pre>"
        f"<p class=\"meta\">{html.escape(_LETTER_NOTE)}</p>"
        if determination.letter
        else "<p>Not drafted. A letter is written only when every required criterion is supported by a quote from the chart.</p>"
    )
    procedures = _procedure_lines(determination.ordered_procedures) or ["None found in the chart"]
    procedure_html = "".join(f"<dd>{html.escape(line)}</dd>" for line in procedures)
    match_note = (
        f"<p class=\"meta\">{html.escape(determination.pathway_match_note)}</p>"
        if determination.pathway_match_note
        else ""
    )
    matched = determination.matched_pathway_name or "none"
    tally = _tally_html(presented)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(heading)} — prior authorization review</title>
  <style>
    :root {{
      --ink: #1c1917;
      --muted: #57534e;
      --line: #e7e5e4;
      --paper: #f6f5f2;
      --card: #ffffff;
      --met: #166534;
      --met-bg: #f0fdf4;
      --met-line: #86efac;
      --gap: #9a3412;
      --gap-bg: #fffbeb;
      --gap-line: #fcd34d;
      --bad: #991b1b;
      --bad-bg: #fef2f2;
      --bad-line: #fca5a5;
      --na: #57534e;
      --na-bg: #f5f5f4;
      --na-line: #d6d3d1;
    }}
    body {{ font-family: system-ui, sans-serif; color: var(--ink); margin: 0; background: var(--paper); line-height: 1.45; }}
    main {{ max-width: 820px; margin: 0 auto; padding: 1.5rem 1.25rem 4rem; }}
    h1 {{ font-size: 1.85rem; line-height: 1.15; margin: 0; }}
    h2 {{ font-size: 1.05rem; margin: 1.75rem 0 0.6rem; }}
    h3 {{ font-size: 1rem; margin: 0.35rem 0 0.45rem; }}
    .banner {{ display: flex; gap: 0.9rem; align-items: flex-start; padding: 1.1rem 1.2rem; border-radius: 14px; border: 1px solid transparent; }}
    .mark {{ flex: 0 0 auto; width: 2.6rem; height: 2.6rem; border-radius: 999px; display: grid; place-items: center; color: white; }}
    .mark svg {{ width: 1.35rem; height: 1.35rem; }}
    .do_not_submit {{ background: var(--bad-bg); border-color: var(--bad-line); }}
    .do_not_submit .mark {{ background: #b91c1c; }}
    .fix_before_submit {{ background: var(--gap-bg); border-color: var(--gap-line); }}
    .fix_before_submit .mark {{ background: #d97706; }}
    .ready_for_review {{ background: var(--met-bg); border-color: var(--met-line); }}
    .ready_for_review .mark {{ background: #15803d; }}
    .reason {{ margin: 0.4rem 0 0; font-size: 1.02rem; }}
    .panel {{ margin-top: 0.9rem; background: var(--card); border-radius: 14px; padding: 0.95rem 1.1rem 0.4rem; border: 2px solid var(--line); }}
    .panel.stop {{ border-color: #ef4444; background: #fffafa; }}
    .panel.fix {{ border-color: #f59e0b; background: #fffdf6; }}
    .panel.ready {{ border-color: #22c55e; background: #f7fef9; }}
    .panel h2 {{ margin: 0; display: flex; align-items: center; gap: 0.45rem; }}
    .panel .sub {{ margin: 0.35rem 0 0.2rem; color: var(--muted); }}
    .steps {{ list-style: none; margin: 0.35rem 0 0.6rem; padding: 0; }}
    .steps li {{ display: flex; gap: 0.75rem; align-items: flex-start; padding: 0.7rem 0; border-top: 1px solid #f0eeeb; font-size: 1.02rem; }}
    .num {{ flex: 0 0 auto; width: 1.65rem; height: 1.65rem; border-radius: 999px; display: grid; place-items: center; color: white; font-weight: 700; font-size: 0.85rem; }}
    .stop .num {{ background: #b91c1c; }}
    .fix .num {{ background: #d97706; }}
    .ready .num {{ background: #15803d; }}
    .also {{ margin: 0 0 0.8rem; color: var(--muted); }}
    .facts {{ display: grid; grid-template-columns: 9.5rem 1fr; gap: 0.35rem 0.75rem; margin: 0; }}
    .facts dt {{ color: var(--muted); }}
    .facts dd {{ margin: 0; }}
    .tally {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.2rem 0 0.7rem; }}
    .chip {{ display: inline-flex; align-items: center; gap: 0.3rem; border-radius: 999px; padding: 0.15rem 0.6rem; font-size: 0.82rem; font-weight: 700; background: var(--na-bg); }}
    .chip.met {{ background: var(--met-bg); color: var(--met); }}
    .chip.not_met {{ background: var(--bad-bg); color: var(--bad); }}
    .chip.not_documented {{ background: var(--gap-bg); color: var(--gap); }}
    .chip.clear, .chip.spare {{ background: var(--met-bg); color: var(--met); }}
    .chip.aside, .chip.not_applicable {{ background: var(--na-bg); color: var(--na); }}
    .card {{ background: var(--card); border: 1px solid var(--line); border-left: 5px solid var(--na-line); border-radius: 12px; padding: 0.75rem 0.95rem 0.85rem; margin: 0.55rem 0; }}
    .card.met, .card.clear, .card.spare {{ border-left-color: #16a34a; }}
    .card.not_met {{ border-left-color: #dc2626; background: #fffafa; }}
    .card.not_documented {{ border-left-color: #d97706; background: #fffdf6; }}
    .card.aside, .card.not_applicable {{ border-left-color: #a8a29e; }}
    .card-top {{ display: flex; flex-wrap: wrap; gap: 0.4rem 0.7rem; align-items: center; }}
    .pill {{ display: inline-flex; align-items: center; gap: 0.28rem; font-size: 0.78rem; font-weight: 700; padding: 0.12rem 0.5rem 0.12rem 0.35rem; border-radius: 999px; }}
    .pill svg {{ width: 0.95rem; height: 0.95rem; }}
    .pill.met, .pill.clear, .pill.spare {{ background: #dcfce7; color: var(--met); }}
    .pill.not_met {{ background: #fee2e2; color: var(--bad); }}
    .pill.not_documented {{ background: #fef3c7; color: var(--gap); }}
    .pill.aside, .pill.not_applicable {{ background: #e7e5e4; color: var(--na); }}
    .group {{ color: var(--muted); font-size: 0.82rem; }}
    blockquote {{ margin: 0.35rem 0; padding: 0.15rem 0 0.15rem 0.75rem; border-left: 3px solid #d6d3d1; white-space: pre-wrap; }}
    pre {{ white-space: pre-wrap; font-family: inherit; background: var(--card); padding: 1rem; border: 1px solid var(--line); border-radius: 10px; }}
    .meta {{ color: var(--muted); }}
    .icon {{ width: 1.1rem; height: 1.1rem; vertical-align: -0.15rem; }}
    @media (max-width: 640px) {{
      .facts {{ grid-template-columns: 1fr; gap: 0.1rem; }}
      .facts dd {{ margin-bottom: 0.45rem; }}
    }}
  </style>
</head>
<body>
<main>
  <div class="banner {css_class}">
    <div class="mark">{_icon(_OUTCOME_ICON[determination.outcome])}</div>
    <div>
      <h1>{html.escape(heading)}</h1>
      <p class="reason">{html.escape(determination.outcome_reason)}</p>
    </div>
  </div>
  {_action_html(determination)}
  <h2>Case</h2>
  <dl class="facts">
    <dt>Patient</dt><dd>{html.escape(_or_unknown(determination.patient_name))}</dd>
    <dt>Chart payer</dt><dd>{html.escape(_or_unknown(determination.payer_on_chart))}</dd>
    <dt>Guideline payer</dt><dd>{html.escape(_or_unknown(determination.guideline_payer))}</dd>
    <dt>Policy</dt><dd>{html.escape(_policy(determination))}</dd>
    <dt>Ordered procedure</dt>{procedure_html}
    <dt>Pathway</dt><dd>{html.escape(matched)}</dd>
  </dl>
  {match_note}
  <h2>Criteria</h2>
  {tally}
  {criteria}
  <h2>Documents this policy asks for</h2>
  {document_note}
  {_html_list(determination.required_documents, "The policy did not list required documents.")}
  <h2>Letter of medical necessity (if initial request is denied)</h2>
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


_OUTCOME_ICON = {
    Outcome.DO_NOT_SUBMIT: "stop",
    Outcome.FIX_BEFORE_SUBMIT: "alert",
    Outcome.READY_FOR_REVIEW: "check",
}

def _icon(name: str) -> str:
    paths = {
        "check": '<path d="M5 12.5l4.2 4.2L19 7.5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
        "x": '<path d="M7 7l10 10M17 7L7 17" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>',
        "alert": '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 8v5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/><circle cx="12" cy="16.2" r="1.05" fill="currentColor"/>',
        "minus": '<path d="M6 12h12" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>',
        "stop": '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8.2 8.2l7.6 7.6" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
    }
    return f'<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>'


def _action_markdown(determination: Determination) -> list[str]:
    block = _action_content(determination)
    if block is None:
        return []
    title, _kind, intro, steps, also = block
    lines = [f"## {title}", "", intro, ""]
    lines.extend(f"{index}. {step}" for index, step in enumerate(steps, start=1))
    if also:
        lines.extend(["", "Also undocumented:", ""])
        lines.extend(f"- {item}" for item in also)
    lines.append("")
    return lines


def _action_html(determination: Determination) -> str:
    block = _action_content(determination)
    if block is None:
        return ""
    title, kind, intro, steps, also = block
    items = "".join(
        f"<li><span class=\"num\">{index}</span><span>{html.escape(step)}</span></li>"
        for index, step in enumerate(steps, start=1)
    )
    extra = ""
    if also:
        extra = "<p class=\"also\">Also undocumented: " + "; ".join(html.escape(item) for item in also) + "</p>"
    icon = {"stop": "stop", "fix": "alert", "ready": "check"}[kind]
    return (
        f"<section class=\"panel {kind}\">"
        f"<h2>{_icon(icon)}{html.escape(title)}</h2>"
        f"<p class=\"sub\">{html.escape(intro)}</p>"
        f"<ol class=\"steps\">{items}</ol>"
        f"{extra}"
        "</section>"
    )


def _action_content(
    determination: Determination,
) -> tuple[str, str, str, list[str], list[str]] | None:
    """Title, style, intro, numbered steps, and extra undocumented items."""
    risks = list(determination.denial_risks)
    gaps = list(determination.missing_items)
    reason = determination.outcome_reason.strip()
    if risks:
        steps = risks
        if len(steps) == 1 and steps[0].strip() == reason and not gaps:
            return None
        return (
            "This would be denied",
            "stop",
            "Hard stops. Adding a note will not clear these.",
            steps,
            gaps,
        )
    if gaps:
        if all(item.startswith("Confirm this sentence in the chart") for item in gaps):
            return (
                "Confirm the cited sentence",
                "fix",
                "The quote was not found verbatim. It does not count as met, and it is not a denial.",
                gaps,
                [],
            )
        return (
            "Add this before submitting",
            "fix",
            "Documentation gaps. The chart does not contradict this policy.",
            gaps,
            [],
        )
    if determination.outcome == Outcome.READY_FOR_REVIEW:
        return (
            "Next step",
            "ready",
            "A reviewer still confirms the quotes. This packet does not submit the request.",
            [
                "Confirm the ordered procedure, CPT, and site against the chart.",
                "Open each quote in the chart and confirm it was not taken out of context.",
                "Review the letter below before anyone sends it.",
            ],
            [],
        )
    return None


def _presentation(row: CriterionResult, or_states: dict[str, str]) -> tuple[str, str, str]:
    """Tone, mark, and label for one row.

    An exclusion that is met blocks the request. An exclusion the chart
    contradicts, or does not document, is cleared. An exclusion about a
    different situation stays not applicable.

    In an OR group, a branch that is not met is not a failure when another
    branch is met. It is also not a failure when another branch is still
    missing documentation. It stays a failure only when every branch is ruled out.
    """
    if row.group == "exclusion" and row.status == LeafStatus.MET:
        return "not_met", "✕", "Applies"
    if row.group == "exclusion" and row.status in (LeafStatus.NOT_MET, LeafStatus.NOT_DOCUMENTED):
        return "clear", "✓", "Exclusion cleared"
    parsed = _or_parts(row.group)
    if parsed:
        state = or_states.get(parsed[0])
        if state == "met" and row.status in (LeafStatus.NOT_MET, LeafStatus.NOT_DOCUMENTED):
            return "spare", "–", "Not needed"
        if state == "open" and row.status == LeafStatus.NOT_MET:
            return "aside", "–", "Not this option"
    status = row.status.value
    return status, _STATUS_MARK.get(status, ""), _STATUS_LABELS.get(status, status)


def _present_all(criteria: list[CriterionResult]) -> list[tuple[str, str, str]]:
    states = _or_states(criteria)
    return [_presentation(row, states) for row in criteria]


def _or_parts(group: str) -> tuple[str, str | None] | None:
    if not group.startswith("any_of:"):
        return None
    rest = group.split(":", 1)[1]
    marker = " / all_of:"
    if marker in rest:
        parent, option = rest.split(marker, 1)
        return parent, option
    return rest, None


def _or_states(criteria: list[CriterionResult]) -> dict[str, str]:
    """Whether each OR group is met, still open, or failed."""
    leaves: dict[str, list[CriterionResult]] = {}
    options: dict[str, dict[str, list[CriterionResult]]] = {}
    for row in criteria:
        parsed = _or_parts(row.group)
        if parsed is None:
            continue
        parent, option = parsed
        if option is None:
            leaves.setdefault(parent, []).append(row)
        else:
            options.setdefault(parent, {}).setdefault(option, []).append(row)
    states: dict[str, str] = {}
    for name in set(leaves) | set(options):
        alternative_states: list[LeafStatus] = []
        for row in leaves.get(name, []):
            if row.status != LeafStatus.NOT_APPLICABLE:
                alternative_states.append(row.status)
        for option_rows in options.get(name, {}).values():
            option_state = _option_display_status(option_rows)
            if option_state is not None and option_state != LeafStatus.NOT_APPLICABLE:
                alternative_states.append(option_state)
        if any(state == LeafStatus.MET for state in alternative_states):
            states[name] = "met"
        elif not alternative_states or any(state == LeafStatus.NOT_DOCUMENTED for state in alternative_states):
            states[name] = "open"
        else:
            states[name] = "failed"
    return states


def _option_display_status(rows: list[CriterionResult]) -> LeafStatus | None:
    active = [row.status for row in rows if row.status != LeafStatus.NOT_APPLICABLE]
    if not active:
        return None
    if any(status == LeafStatus.NOT_MET for status in active):
        return LeafStatus.NOT_MET
    if any(status == LeafStatus.NOT_DOCUMENTED for status in active):
        return LeafStatus.NOT_DOCUMENTED
    if any(status == LeafStatus.MET for status in active):
        return LeafStatus.MET
    return LeafStatus.NOT_APPLICABLE


def _criterion_markdown(row: CriterionResult, presentation: tuple[str, str, str]) -> list[str]:
    _tone, mark, label = presentation
    lines = [
        f"### {mark} {row.text}",
        "",
        f"- Group: {_group_label(row.group)}",
        f"- Status: {mark} {label}",
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


_TONE_ICON = {
    "met": "check",
    "clear": "check",
    "spare": "minus",
    "aside": "minus",
    "not_met": "x",
    "not_documented": "alert",
    "not_applicable": "minus",
}

_TONE_ORDER = (
    ("not_documented", "not documented"),
    ("not_met", "not met"),
    ("met", "met"),
    ("clear", "exclusion cleared"),
    ("spare", "not needed"),
    ("aside", "not this option"),
    ("not_applicable", "not applicable"),
)


def _criterion_html(row: CriterionResult, presentation: tuple[str, str, str]) -> str:
    tone, _mark, label = presentation
    spans = [span.strip() for span in row.quote.split("\n") if span.strip()]
    unverified = bool(spans) and row.status == LeafStatus.NOT_DOCUMENTED and not row.quote_verified
    quote = (
        (
            "<p class=\"meta\">Unverified citation. These words were not found verbatim in the chart.</p>"
            if unverified
            else ""
        )
        + (
            "".join(f"<blockquote>{html.escape(span)}</blockquote>" for span in spans)
            if spans
            else "<p class=\"meta\">No quote</p>"
        )
    )
    source = f"<p class=\"meta\">Source: {html.escape(row.section)}</p>" if row.section else ""
    note = f"<p class=\"meta\">{html.escape(row.rationale)}</p>" if row.rationale else ""
    return (
        f"<article class=\"card {tone}\">"
        "<div class=\"card-top\">"
        f"<span class=\"pill {tone}\">{_icon(_TONE_ICON.get(tone, 'minus'))}{html.escape(label)}</span>"
        f"<span class=\"group\">{html.escape(_group_label(row.group))}</span>"
        "</div>"
        f"<h3>{html.escape(row.text)}</h3>"
        f"{quote}{source}{note}"
        "</article>"
    )


def _tally(presented: list[tuple[str, str, str]]) -> str:
    counts = Counter(tone for tone, _mark, _label in presented)
    bits = [f"{counts[tone]} {label}" for tone, label in _TONE_ORDER if counts[tone]]
    return "Criteria: " + ", ".join(bits) + "." if bits else ""


def _tally_html(presented: list[tuple[str, str, str]]) -> str:
    counts = Counter(tone for tone, _mark, _label in presented)
    chips = []
    for tone, label in _TONE_ORDER:
        count = counts[tone]
        if not count:
            continue
        chips.append(
            f"<span class=\"chip {tone}\">{_icon(_TONE_ICON[tone])}{count} {html.escape(label)}</span>"
        )
    if not chips:
        return ""
    return "<p class=\"tally\">" + "".join(chips) + "</p>"


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
