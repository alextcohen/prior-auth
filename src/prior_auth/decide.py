"""Pathway matching, quote checks, and outcome rollup.

This module does not call a model and does not contain medical criteria.
A leaf is met only when the caller says so and the quote is actually in the chart.
"""

import re
from dataclasses import dataclass

from prior_auth.schemas import (
    Chart,
    CriterionResult,
    Determination,
    Guideline,
    Leaf,
    LeafScore,
    LeafStatus,
    NonCovered,
    Outcome,
    Pathway,
)

_CODE = re.compile(r"\b(?:\d{5}|\d{4}[A-Z]|[A-Z]\d{4})\b", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+")


@dataclass
class PathwayMatch:
    pathway: Pathway | None
    non_covered: NonCovered | None
    reason: str
    warnings: list[str]


def codes_in(value: str) -> list[str]:
    """CPT and HCPCS tokens inside a free-text code field."""
    found: list[str] = []
    for match in _CODE.finditer(value.upper()):
        code = match.group(0).upper()
        if code not in found:
            found.append(code)
    return found


def _codes(values: list[str]) -> set[str]:
    found: set[str] = set()
    for value in values:
        found.update(codes_in(value))
    return found


def chart_codes(chart: Chart) -> set[str]:
    found: set[str] = set()
    for procedure in chart.planned_procedures:
        found |= _codes(procedure.cpt_codes)
    return found


def normalize_ws(text: str) -> str:
    text = (
        text.replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u00a0", " ")
    )
    return re.sub(r"\s+", " ", text).strip().casefold()


def quote_in_text(quote: str, source: str) -> bool:
    needle = normalize_ws(quote)
    if not needle:
        return False
    return needle in normalize_ws(source)


_CAPS_AND = re.compile(r"\s+AND\s+")
_LOWER_AND = re.compile(r"\s+and\s+", re.IGNORECASE)
_THERE_IS = re.compile(r"^there\s+(?:is|are)\b", re.IGNORECASE)
_VERB_CONTINUATION = re.compile(
    r"^(?:does|do|did|has|have|had|is|are|was|were|will|can|cannot|may|must)\b",
    re.IGNORECASE,
)
_SCALE_HEAD = re.compile(
    r"^(?:(?:an?|the)\s+)?"
    r"(?:[A-Za-z][\w./()-]*\s+){0,8}"
    r"(?:\([^)]*\)\s*)?"
    r"(?:class|stage|grade|score)\s+(?:of\s+)?"
    r"(?:[A-Za-z]?\d+[a-z]?|[IVXLC]{1,6})\b",
    re.IGNORECASE,
)
_MEASURE = re.compile(
    r"\b(?:at least|or greater|or more|or higher|greater than|months?|weeks?|days?|hours?|mm|millimeters?|cm|centimeters?)\b",
    re.IGNORECASE,
)
_STITCH = re.compile(r"\s*(?:\n+|\s/\s|\s\|\s|\.{3,}|…)\s*")


def quote_is_grounded(quote: str, source: str) -> bool:
    """True when every stored span appears in the chart."""
    parts = [part.strip() for part in quote.split("\n") if part.strip()]
    return bool(parts) and all(quote_in_text(part, source) for part in parts)


def grounded_quotes(quote: str, source: str) -> list[str]:
    """Chart spans cited by a score.

    One contiguous span is kept when it appears in the chart. Spans joined by a
    slash, ellipsis, newline, or the word "and" are kept when each span appears.
    A paraphrase returns nothing.
    """
    cleaned = quote.strip()
    if not cleaned:
        return []
    if quote_in_text(cleaned, source):
        return [cleaned]
    pieces = [piece.strip(" \"'") for piece in _STITCH.split(cleaned) if piece.strip(" \"'")]
    if len(pieces) <= 1:
        pieces = [
            piece.strip(" \"'")
            for piece in _parts_outside_parens(cleaned, _LOWER_AND)
            if len(piece.strip(" \"'")) >= 12 and " " in piece
        ]
    if len(pieces) > 1 and all(quote_in_text(piece, source) for piece in pieces):
        return pieces
    return []


def split_compound_requirement(text: str) -> list[str]:
    """Split a leaf that still joins two checkable facts.

    This is structure, not a coverage rule. A class, stage, grade, or score
    stays its own leaf so it can be quoted on its own. An any_of alternative
    that is already a list of leaves is left as that list.
    """
    cleaned = text.strip()
    if not cleaned:
        return [text]
    parts = _split_requirement_once(cleaned)
    if not parts:
        return [cleaned]
    expanded: list[str] = []
    for part in parts:
        expanded.extend(split_compound_requirement(part))
    return expanded


def normalize_guideline(guideline: Guideline) -> Guideline:
    """Make leaf and pathway ids unique so later scoring cannot collide."""
    seen_pathways: set[str] = set()
    for index, pathway in enumerate(guideline.pathways, start=1):
        base = _slug(pathway.id) or f"pathway_{index}"
        candidate = base
        suffix = 2
        while candidate in seen_pathways:
            candidate = f"{base}_{suffix}"
            suffix += 1
        seen_pathways.add(candidate)
        pathway.id = candidate
        seen: set[str] = set()

        def fix(leaf: Leaf) -> Leaf:
            leaf_base = _slug(leaf.id) or "criterion"
            leaf_id = leaf_base
            leaf_suffix = 2
            while leaf_id in seen:
                leaf_id = f"{leaf_base}_{leaf_suffix}"
                leaf_suffix += 1
            seen.add(leaf_id)
            if leaf_id == leaf.id:
                return leaf
            return leaf.model_copy(update={"id": leaf_id})

        def expand(leaves: list[Leaf]) -> list[Leaf]:
            expanded: list[Leaf] = []
            for leaf in leaves:
                parts = split_compound_requirement(leaf.text)
                if len(parts) == 1:
                    expanded.append(fix(leaf))
                    continue
                for index, part in enumerate(parts, start=1):
                    new_id = leaf.id if index == 1 else f"{leaf.id}_{index}"
                    expanded.append(fix(leaf.model_copy(update={"id": new_id, "text": part})))
            return expanded

        pathway.all_of = expand(pathway.all_of)
        seen_options: set[str] = set()
        for group_index, group in enumerate(pathway.any_of_groups, start=1):
            group.id = _slug(group.id) or f"group_{group_index}"
            group.leaves = expand(group.leaves)
            for option_index, option in enumerate(group.all_of_options, start=1):
                option_base = _slug(option.id) or f"option_{option_index}"
                option_id = option_base
                option_suffix = 2
                while option_id in seen_options:
                    option_id = f"{option_base}_{option_suffix}"
                    option_suffix += 1
                seen_options.add(option_id)
                option.id = option_id
                option.leaves = expand(option.leaves)
        pathway.exclusions = expand(pathway.exclusions)
    return guideline


def needs_model_proposal(guideline: Guideline, chart: Chart) -> bool:
    """Ask the model only when CPT codes do not already identify one pathway."""
    if not chart.planned_procedures:
        return False
    codes = chart_codes(chart)
    if _noncovered_hits(guideline, codes):
        return False
    overlaps = _overlaps(guideline, codes)
    if len(overlaps) == 1:
        return False
    # Both sides named codes and none match. That is a mismatch, not a naming problem.
    if codes and not overlaps and _policy_has_codes(guideline):
        return False
    return True


def match_pathway(
    guideline: Guideline,
    chart: Chart,
    proposed_pathway_id: str | None,
) -> PathwayMatch:
    if not chart.planned_procedures:
        return PathwayMatch(
            pathway=None,
            non_covered=None,
            reason="No ordered procedure was found in the chart, so there is nothing to submit.",
            warnings=[],
        )

    codes = chart_codes(chart)
    warnings: list[str] = []
    hits = _noncovered_hits(guideline, codes)
    if hits:
        return PathwayMatch(
            pathway=None,
            non_covered=hits[0],
            reason=_noncovered_reason(guideline, chart, hits[0], codes),
            warnings=warnings,
        )

    overlaps = _overlaps(guideline, codes)
    if len(overlaps) == 1:
        pathway, shared = overlaps[0]
        if proposed_pathway_id and proposed_pathway_id != pathway.id:
            warnings.append(
                f"CPT overlap selected pathway {pathway.id}. "
                f"The model proposal {proposed_pathway_id} was not used."
            )
        codes_text = ", ".join(sorted(shared))
        return PathwayMatch(
            pathway=pathway,
            non_covered=None,
            reason=f"CPT overlap on {codes_text} selects {pathway.name}.",
            warnings=warnings,
        )

    if len(overlaps) > 1:
        by_id = {pathway.id: (pathway, shared) for pathway, shared in overlaps}
        if proposed_pathway_id and proposed_pathway_id in by_id:
            pathway, shared = by_id[proposed_pathway_id]
            codes_text = ", ".join(sorted(shared))
            return PathwayMatch(
                pathway=pathway,
                non_covered=None,
                reason=(
                    f"Several pathways share CPT codes. "
                    f"The model proposal {pathway.name} was used ({codes_text})."
                ),
                warnings=warnings,
            )
        pathway, shared = max(overlaps, key=lambda item: len(item[1]))
        warnings.append(
            "Several pathways share CPT codes with the order. "
            "The pathway with the largest overlap was selected."
        )
        codes_text = ", ".join(sorted(shared))
        return PathwayMatch(
            pathway=pathway,
            non_covered=None,
            reason=f"CPT overlap on {codes_text} selects {pathway.name}.",
            warnings=warnings,
        )

    if codes and _policy_has_codes(guideline):
        if proposed_pathway_id:
            warnings.append(
                "CPT codes on the order do not appear in this policy, "
                "so the model pathway proposal was not used."
            )
        return PathwayMatch(
            pathway=None,
            non_covered=None,
            reason=f"{_procedure_phrase(chart)} is not addressed by {_policy_label(guideline)}.",
            warnings=warnings,
        )

    if proposed_pathway_id:
        for pathway in guideline.pathways:
            if pathway.id == proposed_pathway_id:
                return PathwayMatch(
                    pathway=pathway,
                    non_covered=None,
                    reason=f"No CPT overlap. The model matched {pathway.name}.",
                    warnings=warnings,
                )
        warnings.append(f"The model proposed unknown pathway id {proposed_pathway_id}.")

    return PathwayMatch(
        pathway=None,
        non_covered=None,
        reason=f"{_procedure_phrase(chart)} is not addressed by {_policy_label(guideline)}.",
        warnings=warnings,
    )


def verify_scores(
    scores: list[LeafScore],
    chart_text: str,
) -> tuple[list[LeafScore], list[str]]:
    """Drop quotes that are not in the chart. A failed quote cannot support a leaf."""
    verified: list[LeafScore] = []
    warnings: list[str] = []
    for score in scores:
        quote = score.quote.strip()
        if not quote:
            if score.status == LeafStatus.MET:
                warnings.append(
                    f"Criterion {score.criterion_id} was marked met without a chart quote "
                    "and was changed to not documented."
                )
                verified.append(
                    score.model_copy(
                        update={
                            "status": LeafStatus.NOT_DOCUMENTED,
                            "quote": "",
                            "rationale": "Marked met without a verbatim chart quote.",
                        }
                    )
                )
            else:
                verified.append(score.model_copy(update={"quote": ""}))
            continue
        spans = grounded_quotes(quote, chart_text)
        if spans:
            verified.append(score.model_copy(update={"quote": "\n".join(spans)}))
            continue
        warnings.append(
            f"Quote for criterion {score.criterion_id} is not in the chart and was discarded."
        )
        verified.append(
            score.model_copy(
                update={
                    "status": LeafStatus.NOT_DOCUMENTED,
                    "quote": "",
                    "rationale": "Cited text does not appear in the chart.",
                }
            )
        )
    return verified, warnings


def decide(
    guideline: Guideline,
    chart: Chart,
    chart_text: str,
    scores: list[LeafScore],
    proposed_pathway_id: str | None = None,
) -> Determination:
    match = match_pathway(guideline, chart, proposed_pathway_id)
    verified_scores, quote_warnings = verify_scores(scores, chart_text)
    warnings = [*match.warnings, *quote_warnings]
    payer_warning = _payer_warning(chart.payer, guideline.payer)
    if payer_warning:
        warnings.append(payer_warning)

    base = dict(
        patient_name=chart.patient_name,
        payer_on_chart=chart.payer,
        guideline_title=guideline.title,
        guideline_policy_id=guideline.policy_id,
        guideline_payer=guideline.payer,
        ordered_procedures=list(chart.planned_procedures),
        required_documents=list(guideline.required_documents),
        warnings=warnings,
    )

    if match.pathway is None:
        risks = [match.reason]
        if match.non_covered is not None and len(_noncovered_hits(guideline, chart_codes(chart))) > 1:
            risks.append("More than one non-covered code on the order matches this policy.")
        return Determination(
            outcome=Outcome.DO_NOT_SUBMIT,
            outcome_reason=match.reason,
            matched_pathway_id="",
            matched_pathway_name="",
            pathway_match_note=match.reason,
            criteria=[],
            missing_items=[],
            denial_risks=risks,
            letter=None,
            **base,
        )

    criteria = _criterion_results(match.pathway, verified_scores, chart_text)
    outcome, reason, missing, risks = _evaluate(match.pathway, criteria)
    letter = _letter(chart, match.pathway, criteria) if outcome == Outcome.READY_FOR_REVIEW else None
    return Determination(
        outcome=outcome,
        outcome_reason=reason,
        matched_pathway_id=match.pathway.id,
        matched_pathway_name=match.pathway.name,
        pathway_match_note=match.reason,
        criteria=criteria,
        missing_items=missing,
        denial_risks=risks,
        letter=letter,
        **base,
    )


def _policy_has_codes(guideline: Guideline) -> bool:
    if any(_codes(pathway.cpt_codes) for pathway in guideline.pathways):
        return True
    return any(_codes(item.cpt_codes) for item in guideline.non_covered)


def _overlaps(guideline: Guideline, codes: set[str]) -> list[tuple[Pathway, set[str]]]:
    overlaps: list[tuple[Pathway, set[str]]] = []
    for pathway in guideline.pathways:
        shared = _codes(pathway.cpt_codes) & codes
        if shared:
            overlaps.append((pathway, shared))
    return overlaps


def _noncovered_hits(guideline: Guideline, codes: set[str]) -> list[NonCovered]:
    hits: list[NonCovered] = []
    for item in guideline.non_covered:
        if _codes(item.cpt_codes) & codes:
            hits.append(item)
    return hits


def _criterion_results(
    pathway: Pathway,
    scores: list[LeafScore],
    chart_text: str,
) -> list[CriterionResult]:
    by_id: dict[str, LeafScore] = {}
    for score in scores:
        by_id[score.criterion_id] = score

    rows: list[CriterionResult] = []

    def add(leaf: Leaf, group: str) -> None:
        score = by_id.get(leaf.id)
        if score is None:
            rows.append(
                CriterionResult(
                    criterion_id=leaf.id,
                    text=leaf.text,
                    group=group,
                    status=LeafStatus.NOT_DOCUMENTED,
                    rationale="The scorer did not return this criterion.",
                )
            )
            return
        quote = score.quote.strip()
        rows.append(
            CriterionResult(
                criterion_id=leaf.id,
                text=leaf.text,
                group=group,
                status=score.status,
                quote=quote,
                section=score.section,
                rationale=score.rationale,
                quote_verified=bool(quote)
                and score.status == LeafStatus.MET
                and quote_is_grounded(quote, chart_text),
            )
        )

    for leaf in pathway.all_of:
        add(leaf, "all_of")
    for group in pathway.any_of_groups:
        for leaf in group.leaves:
            add(leaf, f"any_of:{group.name}")
        for option in group.all_of_options:
            for leaf in option.leaves:
                add(leaf, f"any_of:{group.name} / all_of:{option.name}")
    for leaf in pathway.exclusions:
        add(leaf, "exclusion")
    return rows


def _option_status(leaves: list[Leaf], status_of) -> LeafStatus:
    """An AND alternative fails on any contradiction, and stays open on a gap."""
    if not leaves:
        return LeafStatus.NOT_DOCUMENTED
    statuses = [status_of(leaf.id) for leaf in leaves]
    if any(status == LeafStatus.NOT_MET for status in statuses):
        return LeafStatus.NOT_MET
    if any(status == LeafStatus.NOT_DOCUMENTED for status in statuses):
        return LeafStatus.NOT_DOCUMENTED
    if any(status == LeafStatus.MET for status in statuses):
        return LeafStatus.MET
    return LeafStatus.NOT_APPLICABLE


def _evaluate(
    pathway: Pathway,
    criteria: list[CriterionResult],
) -> tuple[Outcome, str, list[str], list[str]]:
    by_id = {row.criterion_id: row for row in criteria}

    def status_of(leaf_id: str) -> LeafStatus:
        row = by_id.get(leaf_id)
        if row is None:
            return LeafStatus.NOT_DOCUMENTED
        return row.status

    if not pathway.all_of and not pathway.any_of_groups and not pathway.exclusions:
        return (
            Outcome.FIX_BEFORE_SUBMIT,
            f"{pathway.name} matched, but no criteria were extracted from the guideline.",
            ["The pathway has no requirements to check. Review the guideline text before submitting."],
            [],
        )

    risks: list[str] = []
    for leaf in pathway.exclusions:
        if status_of(leaf.id) == LeafStatus.MET:
            risks.append(f"Exclusion applies: {leaf.text}")

    unmet = [leaf for leaf in pathway.all_of if status_of(leaf.id) == LeafStatus.NOT_MET]
    missing_leaves = [
        leaf for leaf in pathway.all_of if status_of(leaf.id) == LeafStatus.NOT_DOCUMENTED
    ]

    failed_groups = []
    open_groups = []
    for group in pathway.any_of_groups:
        leaf_states = [
            status_of(leaf.id)
            for leaf in group.leaves
            if status_of(leaf.id) != LeafStatus.NOT_APPLICABLE
        ]
        option_states = [
            _option_status(option.leaves, status_of)
            for option in group.all_of_options
            if _option_status(option.leaves, status_of) != LeafStatus.NOT_APPLICABLE
        ]
        states = [*leaf_states, *option_states]
        if any(state == LeafStatus.MET for state in states):
            continue
        if not states or any(state == LeafStatus.NOT_DOCUMENTED for state in states):
            open_groups.append(group)
        else:
            failed_groups.append(group)

    missing = [leaf.text for leaf in missing_leaves]
    for group in open_groups:
        noted = False
        for leaf in group.leaves:
            if status_of(leaf.id) == LeafStatus.NOT_DOCUMENTED:
                missing.append(leaf.text)
                noted = True
        for option in group.all_of_options:
            if _option_status(option.leaves, status_of) != LeafStatus.NOT_DOCUMENTED:
                continue
            for leaf in option.leaves:
                if status_of(leaf.id) == LeafStatus.NOT_DOCUMENTED:
                    missing.append(f"{option.name}: {leaf.text}")
                    noted = True
        if not noted:
            options = "; ".join(leaf.text for leaf in group.leaves)
            missing.append(f"At least one of ({group.name}): {options}")

    for leaf in unmet:
        risks.append(f"Required criterion not met: {leaf.text}")
    for group in failed_groups:
        risks.append(f"No qualifying indication met in {group.name}.")

    # A hard failure outranks a documentation gap. Staff should not "fix" a case
    # the policy already contradicts.
    if risks:
        lead = risks[0]
        if unmet and not lead.startswith("Exclusion"):
            lead = f"The chart contradicts a required criterion: {unmet[0].text}"
        elif failed_groups and lead.startswith("No qualifying"):
            lead = f"None of the qualifying indications in {failed_groups[0].name} are met."
        return Outcome.DO_NOT_SUBMIT, lead, missing, risks

    if missing:
        return (
            Outcome.FIX_BEFORE_SUBMIT,
            f"The ordered procedure matches {pathway.name}, but the chart is missing documentation this policy requires.",
            missing,
            [],
        )

    return (
        Outcome.READY_FOR_REVIEW,
        f"Every required criterion for {pathway.name} is supported by a quote in the chart. A reviewer still confirms the quotes and submits the request.",
        [],
        [],
    )


def _letter(chart: Chart, pathway: Pathway, criteria: list[CriterionResult]) -> str:
    supported = [
        row
        for row in criteria
        if row.status == LeafStatus.MET
        and row.quote_verified
        and not row.group.startswith("exclusion")
    ]
    patient = chart.patient_name or "the patient"
    procedure = _procedure_phrase(chart)
    lines = [
        "To the medical review team,",
        "",
        f"Please authorize {procedure} for {patient}.",
        f"The request is filed under {pathway.name}.",
        "",
        "The following statements are copied from the chart. Each one supports a criterion in the coverage guideline:",
        "",
    ]
    for row in supported:
        location = f" ({row.section})" if row.section else ""
        spans = [span.strip() for span in row.quote.split("\n") if span.strip()]
        for span in spans:
            lines.append(f'- {row.text}: "{span}"{location}')
    return "\n".join(lines)


def _procedure_phrase(chart: Chart) -> str:
    parts: list[str] = []
    for procedure in chart.planned_procedures:
        codes = sorted(_codes(procedure.cpt_codes))
        name = procedure.name or "unnamed procedure"
        if codes:
            parts.append(f"{name} (CPT {', '.join(codes)})")
        else:
            parts.append(name)
    return "; ".join(parts) or "The ordered procedure"


def _policy_label(guideline: Guideline) -> str:
    if guideline.policy_id and guideline.title:
        return f"{guideline.title} ({guideline.policy_id})"
    return guideline.policy_id or guideline.title or "this guideline"


def _noncovered_reason(
    guideline: Guideline,
    chart: Chart,
    item: NonCovered,
    codes: set[str],
) -> str:
    matched = sorted(_codes(item.cpt_codes) & codes)
    code_bit = f" (CPT {', '.join(matched)})" if matched else ""
    reason = item.reason.strip() or "non-covered"
    return (
        f"{_procedure_phrase(chart)} is listed as {reason} by {_policy_label(guideline)}: "
        f"{item.name}{code_bit}."
    )


def _payer_warning(chart_payer: str, guideline_payer: str) -> str | None:
    if not chart_payer.strip() or not guideline_payer.strip():
        return None
    chart_tokens = _payer_tokens(chart_payer)
    guideline_tokens = _payer_tokens(guideline_payer)
    if chart_tokens & guideline_tokens:
        return None
    return (
        f"Chart payer ({chart_payer}) does not match the guideline payer ({guideline_payer}). "
        "Confirm this policy applies to this plan before submitting."
    )


_PAYER_ALIASES = {
    "bcbs": ("blue", "cross", "shield"),
    "uhc": ("united", "healthcare"),
}


def _payer_tokens(value: str) -> set[str]:
    stop = {"plan", "insurance", "health", "company", "the", "of"}
    tokens = {token for token in _WORD.findall(value.casefold()) if len(token) > 3 and token not in stop}
    for token in list(tokens):
        tokens.update(_PAYER_ALIASES.get(token, ()))
    return tokens


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return slug


def _split_requirement_once(text: str) -> list[str] | None:
    caps = _parts_outside_parens(text, _CAPS_AND)
    if len(caps) > 1:
        return caps
    there = _split_there_is_and(text)
    if there:
        return there
    return _split_finding_and_scale(text)


def _split_there_is_and(text: str) -> list[str] | None:
    parts = _parts_outside_parens(text, _LOWER_AND)
    if len(parts) < 2 or not _THERE_IS.match(parts[0]):
        return None
    if any(not _separate_fact(part) for part in parts[1:]):
        return None
    return parts


def _split_finding_and_scale(text: str) -> list[str] | None:
    parts = _parts_outside_parens(text, _LOWER_AND)
    if len(parts) < 2 or len(parts[0].split()) < 3:
        return None
    if any(not _SCALE_HEAD.match(part) for part in parts[1:]):
        return None
    return parts


def _separate_fact(part: str) -> bool:
    """A second conjunct that can be checked without the first."""
    if _VERB_CONTINUATION.match(part):
        return False
    if _SCALE_HEAD.match(part):
        return True
    return len(part.split()) >= 4 and bool(re.search(r"\d", part) and _MEASURE.search(part))


def _parts_outside_parens(text: str, pattern: re.Pattern[str]) -> list[str]:
    """Split on pattern only outside parentheses."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
            buf.append(char)
            index += 1
            continue
        if char == ")" and depth:
            depth -= 1
            buf.append(char)
            index += 1
            continue
        if depth == 0:
            match = pattern.match(text, index)
            if match:
                piece = "".join(buf).strip(" ;")
                if piece:
                    parts.append(piece)
                buf = []
                index = match.end()
                continue
        buf.append(char)
        index += 1
    tail = "".join(buf).strip(" ;")
    if tail:
        parts.append(tail)
    return parts
