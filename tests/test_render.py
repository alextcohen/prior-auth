from prior_auth.render import render_html, render_markdown
from prior_auth.schemas import Determination, Outcome


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
    markdown = render_markdown(determination)
    html = render_html(determination)
    assert markdown.splitlines()[0] == "Do not submit"
    assert "33207" in markdown
    assert "Not drafted" in markdown
    assert "<h1>Do not submit</h1>" in html
    assert "Not drafted" in html
    assert "<script" not in html


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
