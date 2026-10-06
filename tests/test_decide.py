from prior_auth.decide import (
    chart_codes,
    codes_in,
    decide,
    needs_model_proposal,
    normalize_guideline,
    quote_in_text,
)
from prior_auth.schemas import (
    AllOfOption,
    AnyOfGroup,
    Chart,
    Guideline,
    Leaf,
    LeafScore,
    LeafStatus,
    NonCovered,
    Outcome,
    Pathway,
    PlannedProcedure,
)


CHART_TEXT = (
    "Duplex ultrasound demonstrates saphenous reflux. "
    "The vein diameter is 4.2 mm. "
    "Compression stockings for 4 months without improvement. "
    "Symptoms interfere with activities of daily living. "
    "Performed at the same time as great saphenous ablation."
)


def _leaf(leaf_id: str, text: str) -> Leaf:
    return Leaf(id=leaf_id, text=text)


def _score(leaf_id: str, status: LeafStatus, quote: str = "", section: str = "Note") -> LeafScore:
    return LeafScore(
        criterion_id=leaf_id,
        status=status,
        quote=quote,
        section=section,
        rationale="test",
    )


def _pathway(**overrides) -> Pathway:
    data = dict(
        id="gsv",
        name="Great saphenous ablation",
        procedure_names=["endovenous laser ablation"],
        cpt_codes=["36478"],
        all_of=[
            _leaf("reflux", "Demonstrated saphenous reflux"),
            _leaf("size", "Varicosities at least 3 millimeters"),
            _leaf("compression", "Compression therapy for at least 3 months"),
        ],
        any_of_groups=[
            AnyOfGroup(
                id="indications",
                name="clinical indications",
                leaves=[
                    _leaf("ulcer", "Ulceration secondary to venous stasis"),
                    _leaf("symptoms", "Symptoms interfere with activities of daily living"),
                ],
            )
        ],
        exclusions=[_leaf("concurrent", "Concurrent perforator treatment")],
    )
    data.update(overrides)
    return Pathway(**data)


def _guideline(*pathways: Pathway, non_covered: list[NonCovered] | None = None) -> Guideline:
    return Guideline(
        payer="BCBS Florida",
        title="Treatments for Varicose Veins",
        policy_id="02-33000-31",
        pathways=list(pathways) or [_pathway()],
        non_covered=non_covered or [],
        required_documents=["Duplex ultrasound report"],
    )


def _chart(*codes: str, name: str = "Endovenous laser ablation", payer: str = "BCBS Florida") -> Chart:
    return Chart(
        patient_name="Alex Stone",
        payer=payer,
        planned_procedures=[
            PlannedProcedure(name=name, cpt_codes=list(codes), laterality="right leg", indication="")
        ],
        facts=[],
    )


def _met_scores() -> list[LeafScore]:
    return [
        _score("reflux", LeafStatus.MET, "Duplex ultrasound demonstrates saphenous reflux."),
        _score("size", LeafStatus.MET, "The vein diameter is 4.2 mm."),
        _score("compression", LeafStatus.MET, "Compression stockings for 4 months without improvement."),
        _score("ulcer", LeafStatus.NOT_DOCUMENTED),
        _score("symptoms", LeafStatus.MET, "Symptoms interfere with activities of daily living."),
        _score("concurrent", LeafStatus.NOT_MET),
    ]


def test_codes_in_reads_cpt_and_hcpcs():
    assert codes_in("CPT 33207") == ["33207"]
    assert codes_in("36478-59") == ["36478"]
    assert codes_in("S2202 and 0524T") == ["S2202", "0524T"]
    assert codes_in("onset 2025") == []


def test_quote_ignores_case_and_whitespace():
    assert quote_in_text("duplex   ultrasound\ndemonstrates saphenous reflux", CHART_TEXT)


def test_all_required_criteria_met_is_ready_and_letter_uses_quotes():
    determination = decide(_guideline(), _chart("36478"), CHART_TEXT, _met_scores())
    assert determination.outcome == Outcome.READY_FOR_REVIEW
    assert determination.letter is not None
    assert "Duplex ultrasound demonstrates saphenous reflux." in determination.letter
    assert "No perforator treatment is planned." not in determination.letter
    assert "not an approval" not in determination.letter
    assert determination.missing_items == []


def test_missing_compression_is_a_gap_and_omits_the_letter():
    scores = _met_scores()
    scores[2] = _score("compression", LeafStatus.NOT_DOCUMENTED)
    determination = decide(_guideline(), _chart("36478"), CHART_TEXT, scores)
    assert determination.outcome == Outcome.FIX_BEFORE_SUBMIT
    assert any("3 months" in item for item in determination.missing_items)
    assert determination.letter is None


def test_not_met_beats_a_documentation_gap():
    scores = _met_scores()
    scores[1] = _score("size", LeafStatus.NOT_MET, "The vein diameter is 4.2 mm.")
    scores[2] = _score("compression", LeafStatus.NOT_DOCUMENTED)
    determination = decide(_guideline(), _chart("36478"), CHART_TEXT, scores)
    assert determination.outcome == Outcome.DO_NOT_SUBMIT
    assert "3 millimeters" in determination.outcome_reason
    assert determination.letter is None


def test_triggered_exclusion_blocks_submission():
    scores = _met_scores()
    scores[-1] = _score(
        "concurrent",
        LeafStatus.MET,
        "Performed at the same time as great saphenous ablation.",
    )
    determination = decide(_guideline(), _chart("36478"), CHART_TEXT, scores)
    assert determination.outcome == Outcome.DO_NOT_SUBMIT
    assert determination.outcome_reason.startswith("Exclusion applies")
    assert determination.letter is None


def test_investigational_cpt_is_do_not_submit_even_if_a_pathway_lists_it():
    pathway = _pathway(cpt_codes=["36473", "36478"])
    guideline = _guideline(
        pathway,
        non_covered=[
            NonCovered(name="Mechanochemical ablation", cpt_codes=["36473", "36474"], reason="investigational")
        ],
    )
    determination = decide(
        guideline,
        _chart("36473", name="Mechanochemical ablation"),
        "Order CPT 36473 mechanochemical ablation.",
        [],
        proposed_pathway_id="gsv",
    )
    assert determination.outcome == Outcome.DO_NOT_SUBMIT
    assert "investigational" in determination.outcome_reason
    assert "36473" in determination.outcome_reason
    assert determination.matched_pathway_id == ""
    assert determination.letter is None
    assert needs_model_proposal(guideline, _chart("36473")) is False


def test_conflicting_cpt_ignores_a_model_proposal():
    chart = _chart("33207", name="Permanent pacemaker implantation")
    determination = decide(
        _guideline(),
        chart,
        "Planned procedure CPT 33207.",
        _met_scores(),
        proposed_pathway_id="gsv",
    )
    assert determination.outcome == Outcome.DO_NOT_SUBMIT
    assert determination.matched_pathway_id == ""
    assert determination.criteria == []
    assert determination.letter is None
    assert any("was not used" in warning for warning in determination.warnings)
    assert needs_model_proposal(_guideline(), chart) is False


def test_pacemaker_cpt_is_outside_the_vein_policy():
    determination = decide(
        _guideline(),
        _chart("33207", name="Permanent pacemaker implantation", payer="UnitedHealthcare"),
        "Planned Procedure: Permanent pacemaker CPT 33207.",
        [],
        proposed_pathway_id=None,
    )
    assert determination.outcome == Outcome.DO_NOT_SUBMIT
    assert determination.matched_pathway_id == ""
    assert "33207" in determination.outcome_reason
    assert "02-33000-31" in determination.outcome_reason
    assert determination.letter is None
    assert determination.criteria == []
    assert any("UnitedHealthcare" in warning for warning in determination.warnings)


def test_rejected_quote_becomes_not_documented():
    scores = [
        _score("reflux", LeafStatus.MET, "duplex shows reflux of 1.2 seconds"),
    ]
    pathway = _pathway(all_of=[_leaf("reflux", "Demonstrated saphenous reflux")], any_of_groups=[], exclusions=[])
    determination = decide(_guideline(pathway), _chart("36478"), CHART_TEXT, scores)
    assert determination.criteria[0].status == LeafStatus.NOT_DOCUMENTED
    assert determination.criteria[0].quote == ""
    assert determination.outcome == Outcome.FIX_BEFORE_SUBMIT
    assert any("not in the chart" in warning for warning in determination.warnings)
    assert determination.letter is None


def test_letter_keeps_only_verified_quotes_when_a_sibling_quote_is_invented():
    scores = _met_scores()
    scores[3] = _score("ulcer", LeafStatus.MET, "active venous ulcer for 6 weeks")
    determination = decide(_guideline(), _chart("36478"), CHART_TEXT, scores)
    assert determination.outcome == Outcome.READY_FOR_REVIEW
    assert determination.letter is not None
    assert "active venous ulcer" not in determination.letter
    assert "Symptoms interfere with activities of daily living." in determination.letter
    ulcer = next(row for row in determination.criteria if row.criterion_id == "ulcer")
    assert ulcer.status == LeafStatus.NOT_DOCUMENTED


def test_cpt_overlap_overrides_a_wrong_proposal():
    spider = _pathway(
        id="spider",
        name="Spider veins",
        procedure_names=["sclerotherapy of telangiectasia"],
        cpt_codes=["36468"],
        all_of=[_leaf("spider_present", "Spider veins are present")],
        any_of_groups=[],
        exclusions=[],
    )
    determination = decide(
        _guideline(_pathway(), spider),
        _chart("36478"),
        CHART_TEXT,
        _met_scores(),
        proposed_pathway_id="spider",
    )
    assert determination.matched_pathway_id == "gsv"
    assert any("was not used" in warning for warning in determination.warnings)
    assert determination.outcome == Outcome.READY_FOR_REVIEW


def test_model_proposal_is_used_when_no_codes_overlap():
    determination = decide(
        _guideline(),
        _chart(name="Endovenous laser ablation of the right great saphenous vein"),
        CHART_TEXT,
        _met_scores(),
        proposed_pathway_id="gsv",
    )
    assert determination.matched_pathway_id == "gsv"
    assert "model matched" in determination.pathway_match_note.casefold()
    assert needs_model_proposal(_guideline(), _chart(name="Endovenous laser ablation")) is True


def test_unique_cpt_does_not_need_a_proposal():
    assert needs_model_proposal(_guideline(), _chart("36478")) is False


def test_no_ordered_procedure():
    chart = Chart(patient_name="Alex Stone", payer="", planned_procedures=[], facts=[])
    determination = decide(_guideline(), chart, CHART_TEXT, [])
    assert determination.outcome == Outcome.DO_NOT_SUBMIT
    assert "No ordered procedure" in determination.outcome_reason
    assert needs_model_proposal(_guideline(), chart) is False


def test_any_of_group_fully_unmet_is_a_denial():
    scores = _met_scores()
    scores[3] = _score("ulcer", LeafStatus.NOT_MET, "No ulceration.")
    scores[4] = _score("symptoms", LeafStatus.NOT_MET, "Symptoms do not interfere with daily activities.")
    # The not_met quotes must actually be in the chart or they are discarded.
    text = CHART_TEXT + " No ulceration. Symptoms do not interfere with daily activities."
    determination = decide(_guideline(), _chart("36478"), text, scores)
    assert determination.outcome == Outcome.DO_NOT_SUBMIT
    assert "clinical indications" in determination.outcome_reason


def test_normalize_guideline_dedupes_ids():
    pathway = _pathway(
        id="GSV Ablation",
        all_of=[_leaf("Reflux!", "reflux"), _leaf("Reflux!", "size")],
        any_of_groups=[],
        exclusions=[],
    )
    guideline = normalize_guideline(_guideline(pathway))
    ids = [leaf.id for leaf in guideline.pathways[0].all_of]
    assert ids[0] != ids[1]
    assert guideline.pathways[0].id == "gsv_ablation"


def test_ambiguous_cpt_uses_the_proposal():
    first = _pathway(id="laser", name="Laser", cpt_codes=["36478"])
    second = _pathway(id="radiofrequency", name="Radiofrequency", cpt_codes=["36478", "36475"])
    chart = _chart("36478")
    guideline = _guideline(first, second)
    assert needs_model_proposal(guideline, chart) is True
    determination = decide(guideline, chart, CHART_TEXT, _met_scores(), proposed_pathway_id="radiofrequency")
    assert determination.matched_pathway_id == "radiofrequency"


def test_chart_codes_from_planned_procedures():
    assert chart_codes(_chart("CPT 36478")) == {"36478"}


def _symptom_pathway() -> Pathway:
    return _pathway(
        all_of=[_leaf("reflux", "Demonstrated saphenous reflux")],
        any_of_groups=[
            AnyOfGroup(
                id="indications",
                name="clinical indications",
                leaves=[_leaf("ulcer", "Ulceration secondary to venous stasis")],
                all_of_options=[
                    AllOfOption(
                        id="symptoms",
                        name="symptomatic reflux",
                        leaves=[
                            _leaf("pain", "Symptoms associated with saphenous reflux"),
                            _leaf("months", "Compression therapy for at least 3 months"),
                        ],
                    )
                ],
            )
        ],
        exclusions=[],
    )


def test_nested_and_satisfies_the_or_when_every_part_is_met():
    scores = [
        _score("reflux", LeafStatus.MET, "Duplex ultrasound demonstrates saphenous reflux."),
        _score("ulcer", LeafStatus.NOT_MET, "No ulceration."),
        _score("pain", LeafStatus.MET, "Symptoms interfere with activities of daily living."),
        _score("months", LeafStatus.MET, "Compression stockings for 4 months without improvement."),
    ]
    text = CHART_TEXT + " No ulceration."
    determination = decide(_guideline(_symptom_pathway()), _chart("36478"), text, scores)
    assert determination.outcome == Outcome.READY_FOR_REVIEW
    assert determination.letter is not None
    assert "Compression stockings for 4 months without improvement." in determination.letter


def test_nested_and_with_a_missing_part_is_a_gap():
    scores = [
        _score("reflux", LeafStatus.MET, "Duplex ultrasound demonstrates saphenous reflux."),
        _score("ulcer", LeafStatus.NOT_MET, "No ulceration."),
        _score("pain", LeafStatus.MET, "Symptoms interfere with activities of daily living."),
        _score("months", LeafStatus.NOT_DOCUMENTED),
    ]
    text = CHART_TEXT + " No ulceration."
    determination = decide(_guideline(_symptom_pathway()), _chart("36478"), text, scores)
    assert determination.outcome == Outcome.FIX_BEFORE_SUBMIT
    assert any("3 months" in item for item in determination.missing_items)
    assert determination.letter is None


def test_finding_and_class_split_into_two_required_leaves():
    pathway = _pathway(
        all_of=[
            _leaf("combo", "There is demonstrated saphenous reflux and CEAP class C2 or greater"),
            _leaf("compression", "Compression therapy for at least 3 months"),
        ],
        any_of_groups=[],
        exclusions=[
            _leaf(
                "cosmetic",
                "Treatment is considered cosmetic and does not meet the definition of medical necessity",
            )
        ],
    )
    pathway.any_of_groups = []
    guideline = normalize_guideline(_guideline(pathway))
    leaves = guideline.pathways[0].all_of
    assert [leaf.text for leaf in leaves] == [
        "There is demonstrated saphenous reflux",
        "CEAP class C2 or greater",
        "Compression therapy for at least 3 months",
    ]
    assert len(guideline.pathways[0].exclusions) == 1
    assert "and does not" in guideline.pathways[0].exclusions[0].text

    text = "Duplex ultrasound demonstrates saphenous reflux. CEAP class C4a, symptomatic."
    scores = [
        _score(leaves[0].id, LeafStatus.MET, "Duplex ultrasound demonstrates saphenous reflux."),
        _score(leaves[1].id, LeafStatus.MET, "CEAP class C4a, symptomatic."),
        _score(leaves[2].id, LeafStatus.NOT_DOCUMENTED),
    ]
    determination = decide(guideline, _chart("36478"), text, scores)
    assert determination.outcome == Outcome.FIX_BEFORE_SUBMIT
    assert determination.missing_items == ["Compression therapy for at least 3 months"]
    assert determination.letter is None


def test_and_inside_a_parenthetical_or_a_single_course_stays_one_leaf():
    pathway = _pathway(
        all_of=[
            _leaf(
                "tributaries",
                "The superficial veins (accessory saphenous and symptomatic tributaries) have been previously eliminated",
            ),
            _leaf(
                "ulcers",
                "Ulcers have not resolved following combined superficial vein treatment and compression therapy for at least 3 months",
            ),
            _leaf("pain", "There is pain and swelling"),
        ],
        any_of_groups=[],
        exclusions=[],
    )
    guideline = normalize_guideline(_guideline(pathway))
    assert [leaf.text for leaf in guideline.pathways[0].all_of] == [
        "The superficial veins (accessory saphenous and symptomatic tributaries) have been previously eliminated",
        "Ulcers have not resolved following combined superficial vein treatment and compression therapy for at least 3 months",
        "There is pain and swelling",
    ]


def test_uppercase_and_splits_inside_a_nested_option():
    pathway = _symptom_pathway()
    pathway.any_of_groups[0].all_of_options[0].leaves = [
        _leaf("combo", "Pain is present AND compression failed for 3 months")
    ]
    guideline = normalize_guideline(_guideline(pathway))
    option = guideline.pathways[0].any_of_groups[0].all_of_options[0]
    assert [leaf.text for leaf in option.leaves] == [
        "Pain is present",
        "compression failed for 3 months",
    ]


def test_joined_verbatim_spans_stay_met():
    scores = [
        _score(
            "reflux",
            LeafStatus.MET,
            "Duplex ultrasound demonstrates saphenous reflux. / The vein diameter is 4.2 mm.",
        )
    ]
    pathway = _pathway(
        all_of=[_leaf("reflux", "Demonstrated saphenous reflux")],
        any_of_groups=[],
        exclusions=[],
    )
    determination = decide(_guideline(pathway), _chart("36478"), CHART_TEXT, scores)
    assert determination.criteria[0].status == LeafStatus.MET
    assert determination.criteria[0].quote_verified
    assert "Duplex ultrasound demonstrates saphenous reflux." in determination.criteria[0].quote
    assert "The vein diameter is 4.2 mm." in determination.criteria[0].quote
    assert determination.letter is not None
    assert "Duplex ultrasound demonstrates saphenous reflux." in determination.letter


def test_and_joined_verbatim_spans_stay_met_and_a_paraphrase_does_not():
    pathway = _pathway(
        all_of=[
            _leaf("reflux", "Demonstrated saphenous reflux"),
            _leaf("size", "Varicosities at least 3 millimeters"),
        ],
        any_of_groups=[],
        exclusions=[],
    )
    scores = [
        _score(
            "reflux",
            LeafStatus.MET,
            "Duplex ultrasound demonstrates saphenous reflux. and The vein diameter is 4.2 mm.",
        ),
        _score("size", LeafStatus.MET, "duplex shows a vein wider than 3 mm"),
    ]
    determination = decide(_guideline(pathway), _chart("36478"), CHART_TEXT, scores)
    reflux = determination.criteria[0]
    size = determination.criteria[1]
    assert reflux.status == LeafStatus.MET
    assert "Duplex ultrasound demonstrates saphenous reflux." in reflux.quote
    assert size.status == LeafStatus.NOT_DOCUMENTED
    assert size.quote == ""


def test_nested_and_contradiction_denies_when_no_alternative_remains():
    scores = [
        _score("reflux", LeafStatus.MET, "Duplex ultrasound demonstrates saphenous reflux."),
        _score("ulcer", LeafStatus.NOT_MET, "No ulceration."),
        _score("pain", LeafStatus.MET, "Symptoms interfere with activities of daily living."),
        _score("months", LeafStatus.NOT_MET, "Symptoms resolved after stockings."),
    ]
    text = CHART_TEXT + " No ulceration. Symptoms resolved after stockings."
    determination = decide(_guideline(_symptom_pathway()), _chart("36478"), text, scores)
    assert determination.outcome == Outcome.DO_NOT_SUBMIT
    assert "clinical indications" in determination.outcome_reason
    assert determination.letter is None
