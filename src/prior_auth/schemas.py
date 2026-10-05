"""Structured records shared by extraction, decision, and rendering.

Medical criteria are instances of these models, filled from a guideline PDF.
They are not hardcoded for any payer or procedure.
"""

from enum import Enum

from pydantic import BaseModel, Field


class LeafStatus(str, Enum):
    MET = "met"
    NOT_MET = "not_met"
    NOT_DOCUMENTED = "not_documented"
    NOT_APPLICABLE = "not_applicable"


class Outcome(str, Enum):
    DO_NOT_SUBMIT = "do_not_submit"
    FIX_BEFORE_SUBMIT = "fix_before_submit"
    READY_FOR_REVIEW = "ready_for_review"


class Leaf(BaseModel):
    id: str = Field(description="Stable snake_case id, unique within the pathway.")
    text: str = Field(description="One atomic requirement, in the guideline's own words.")


class AnyOfGroup(BaseModel):
    id: str = Field(description="Stable snake_case id for this indication group.")
    name: str = Field(description="Short name, such as 'clinical indications'.")
    leaves: list[Leaf] = Field(
        description="The group is satisfied when at least one leaf is met."
    )


class Pathway(BaseModel):
    id: str = Field(description="Stable snake_case id.")
    name: str = Field(description="Name of the covered procedure family.")
    procedure_names: list[str] = Field(
        description="Treatments that share these criteria."
    )
    cpt_codes: list[str] = Field(
        description="CPT or HCPCS codes the policy explicitly ties to these treatments. Empty if the policy does not list codes."
    )
    all_of: list[Leaf] = Field(description="Every leaf must be met.")
    any_of_groups: list[AnyOfGroup] = Field(
        description="Each group is an OR list: one leaf must be met."
    )
    exclusions: list[Leaf] = Field(
        description="If a leaf is met, this pathway does not meet medical necessity."
    )


class NonCovered(BaseModel):
    name: str = Field(description="Procedure or technique the policy excludes.")
    cpt_codes: list[str] = Field(
        description="Codes the policy explicitly ties to this exclusion. Empty if none are listed."
    )
    reason: str = Field(
        description="One of: investigational, cosmetic, non_covered."
    )


class Guideline(BaseModel):
    payer: str = Field(description="Payer or plan named on the policy. Empty if unstated.")
    title: str = Field(description="Policy title.")
    policy_id: str = Field(description="Policy or guideline number. Empty if unstated.")
    pathways: list[Pathway] = Field(description="Covered procedure families and their criteria.")
    non_covered: list[NonCovered] = Field(
        description="Procedures the policy calls investigational, cosmetic, or non-covered."
    )
    required_documents: list[str] = Field(
        description="Documents the policy says to submit with a request."
    )


class Fact(BaseModel):
    id: str = Field(description="Stable snake_case id.")
    statement: str = Field(description="One clinical fact, paraphrased only for indexing.")
    quote: str = Field(description="Exact contiguous span copied from the chart.")
    section: str = Field(description="Note title, date, or section. Empty if unknown.")


class PlannedProcedure(BaseModel):
    name: str = Field(description="Procedure that is ordered, planned, or pending authorization.")
    cpt_codes: list[str] = Field(
        description="CPT or HCPCS codes printed in the chart for this order. Empty if none are printed."
    )
    laterality: str = Field(description="Laterality or site if stated. Empty if unstated.")
    indication: str = Field(description="Stated reason for the order. Empty if unstated.")


class Chart(BaseModel):
    patient_name: str = Field(description="Patient name. Empty if absent.")
    payer: str = Field(description="Payer or plan named in the chart. Empty if absent.")
    planned_procedures: list[PlannedProcedure] = Field(
        description="Procedures ordered or pending authorization. Not historical procedures."
    )
    facts: list[Fact] = Field(
        description="Atomic chart facts that could support or refute medical necessity."
    )


class LeafScore(BaseModel):
    criterion_id: str = Field(description="Id of the criterion being scored.")
    status: LeafStatus
    quote: str = Field(
        description="Verbatim chart span when status is met or not_met. Empty otherwise."
    )
    section: str = Field(description="Where the quote appears. Empty if unknown.")
    rationale: str = Field(description="One sentence on why this status was chosen.")


class ScoreBatch(BaseModel):
    scores: list[LeafScore]


class PathwayProposal(BaseModel):
    pathway_id: str = Field(
        description="Id of the pathway that covers the ordered procedure. Empty string if none do."
    )
    reason: str = Field(description="One sentence.")


class CriterionResult(BaseModel):
    criterion_id: str
    text: str
    group: str
    status: LeafStatus
    quote: str = ""
    section: str = ""
    rationale: str = ""
    quote_verified: bool = False


class Determination(BaseModel):
    outcome: Outcome
    outcome_reason: str
    patient_name: str = ""
    payer_on_chart: str = ""
    guideline_title: str = ""
    guideline_policy_id: str = ""
    guideline_payer: str = ""
    ordered_procedures: list[PlannedProcedure] = Field(default_factory=list)
    matched_pathway_id: str = ""
    matched_pathway_name: str = ""
    pathway_match_note: str = ""
    criteria: list[CriterionResult] = Field(default_factory=list)
    missing_items: list[str] = Field(default_factory=list)
    denial_risks: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    letter: str | None = None
    warnings: list[str] = Field(default_factory=list)
