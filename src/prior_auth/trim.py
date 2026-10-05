"""Drop bibliography pages when a guideline is too long for one model call.

The trimmer looks at headings and citation density. It does not decide medical necessity.
"""

import re

CHAR_BUDGET = 100_000

_PAGE_SPLIT = re.compile(r"\n\n---\n\n")
_NUMBERED = re.compile(r"^\d+\.\s+\S")
_KEYWORDS = (
    "position statement",
    "medical necessity",
    "criteria",
    "billing",
    "coding",
    "cpt",
    "documentation",
    "indication",
    "exclusion",
    "investigational",
    "cosmetic",
    "not covered",
)


def trim_guideline(markdown: str, budget: int = CHAR_BUDGET) -> tuple[str, bool]:
    """Return markdown and whether any text was removed."""
    if len(markdown) <= budget:
        return markdown, False

    pages = split_pages(markdown)
    kept: list[str] = []
    in_references = False
    for page in pages:
        if in_references or page_is_references(page):
            in_references = True
            continue
        kept.append(page)
    if not kept:
        kept = pages[:1]

    text = join_pages(kept)
    if len(text) <= budget:
        return text, True

    selected: list[str] = []
    used = 0
    for index, page in enumerate(kept):
        take = index == 0 or keyword_score(page) > 0
        if not take:
            continue
        if index != 0 and selected and used + len(page) > budget:
            continue
        selected.append(page)
        used += len(page)
    if not selected:
        selected = kept[:1]
    return join_pages(selected), True


def split_pages(markdown: str) -> list[str]:
    parts = [part for part in _PAGE_SPLIT.split(markdown) if part.strip()]
    return parts or [markdown]


def join_pages(pages: list[str]) -> str:
    return "\n\n---\n\n".join(pages)


def page_is_references(page: str) -> bool:
    head = "\n".join(page.splitlines()[:12])
    if re.search(r"\b(references|bibliography)\b", head, re.IGNORECASE):
        return True
    if not re.search(r"\b(pmid|doi:|et al)\b", page, re.IGNORECASE):
        return False
    lines = [line.strip() for line in page.splitlines() if line.strip()]
    if len(lines) < 5:
        return False
    numbered = sum(1 for line in lines if _NUMBERED.match(line))
    return numbered >= 5 and numbered / len(lines) > 0.4


def keyword_score(page: str) -> int:
    lowered = page.casefold()
    return sum(lowered.count(keyword) for keyword in _KEYWORDS)


def clip(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    return text[:budget] + "\n\n[truncated]\n"
