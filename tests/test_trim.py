from prior_auth.trim import page_is_references, trim_guideline


def test_short_guideline_is_unchanged():
    text = "Position statement. Treatment meets medical necessity when reflux is shown."
    trimmed, changed = trim_guideline(text, budget=10_000)
    assert trimmed == text
    assert changed is False


def test_reference_page_is_dropped_only_after_the_budget():
    clinical = "## Page 1\n\nPosition statement. Medical necessity requires documented reflux and billing criteria."
    references = "\n".join(
        [
            "## Page 2",
            "",
            "References",
            "",
            "1. Smith A. A paper about veins.",
            "2. Jones B. Another paper about veins.",
            "3. Lee C. A third paper.",
            "4. Ng D. A fourth paper.",
            "5. Ortiz E. A fifth paper.",
            "6. Patel F. A sixth paper.",
        ]
    )
    text = f"{clinical}\n\n---\n\n{references}"
    assert page_is_references(references)
    unchanged, changed = trim_guideline(text, budget=len(text))
    assert changed is False
    assert "Smith A" in unchanged

    trimmed, changed = trim_guideline(text, budget=len(text) - 1)
    assert changed is True
    assert "Medical necessity" in trimmed
    assert "Smith A" not in trimmed
