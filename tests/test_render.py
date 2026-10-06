from prior_auth.render import render_html
from prior_auth.schemas import CriterionResult, Determination, LeafStatus, Outcome


def test_packet_opens_with_the_outcome_and_omits_an_unready_letter():
    determination = Determination(
        outcome=Outcome.DO_NOT_SUBMIT,
        outcome_reason="Permanent pacemaker implantation (CPT 33207) is not addressed by Treatments for Varicose Veins (02-33000-31).",
        patient_name="Robert James Mitchell",
        payer_on_chart="UnitedHealthcare",
        guideline_title="Treatments for Varicose Veins",
        guideline_policy_id="02-33000-31",
        guideline_payer="BCBS Florida",
        letter=None,
    )
    html = render_html(determination)
    assert "<h1>Do not submit</h1>" in html
    assert "33207" in html
    assert "Not drafted" in html
    assert "<script" not in html


def test_fix_packet_leads_with_the_gaps():
    determination = Determination(
        outcome=Outcome.FIX_BEFORE_SUBMIT,
        outcome_reason="The chart is missing documentation this policy requires.",
        missing_items=["Compression therapy for at least 3 months"],
        criteria=[
            CriterionResult(
                criterion_id="compression",
                text="Compression therapy for at least 3 months",
                group="all_of",
                status=LeafStatus.NOT_DOCUMENTED,
            ),
            CriterionResult(
                criterion_id="size",
                text="Varicosities at least 3 millimeters",
                group="all_of",
                status=LeafStatus.MET,
                quote="The vein diameter is 6.2 mm.",
            ),
        ],
    )
    page = render_html(determination)
    assert page.index("Add this before submitting") < page.index("<h2>Criteria</h2>")
    assert 'class="panel fix"' in page
    assert 'class="card not_documented"' in page
    assert 'class="card met"' in page
    assert "<script" not in page


def test_letter_note_sits_outside_the_copyable_box():
    determination = Determination(
        outcome=Outcome.READY_FOR_REVIEW,
        outcome_reason="Every required criterion is supported.",
        letter="To the medical review team,\n\nPlease authorize the procedure.",
    )
    html = render_html(determination)
    pre, after = html.split("</pre>", 1)
    assert "not an approval" not in pre
    assert "not an approval" in after
    assert "not an approval" not in determination.letter
