# Design note

Clinic staff lose time when they submit prior authorization from memory of what a payer denies. This tool reads the guideline that was handed to it and the chart that was handed to it, then writes a review packet. It does not approve care and it does not submit a request.

## Where judgment lives

**The model reads. The code decides.**

OpenAI transcribes each PDF page into markdown. That is ingestion, not a coverage decision. A later OpenAI call fills three schemas:

- a guideline becomes pathways, each with `all_of` leaves, `any_of` groups, and exclusions, plus a side list of investigational or cosmetic codes. An alternative inside an `any_of` group may itself be an `all_of` list
- a chart becomes the ordered procedure and atomic facts with verbatim quotes
- when CPT codes do not already pick a single pathway, the model may name a pathway id, or none
- the leaves of the matched pathway are scored `met`, `not_met`, `not_documented`, or `not_applicable`

`normalize_guideline` gives every pathway and leaf a unique id. It also splits a leaf that still joins two facts with "and" when one fact is a class, stage, grade, or score, or when the leaf is an existence claim covering two separate facts. Each fact can then be quoted on its own. An `any_of` alternative that is already a list of leaves stays a list.

Prompts are files in `src/prior_auth/prompts/`. The medical criteria for a case are the extracted JSON (`guideline.json`), not Python. A new guideline should change that JSON and leave the decision module alone.

`decide.py` is the decision:

- CPT overlap selects the pathway. A code on the policy's non-covered list is do-not-submit even if a pathway name looks similar.
- If the order and the policy both carry CPT or HCPCS codes and none of them overlap, the order is outside the policy. A model pathway name is not allowed to override that.
- If there is no CPT overlap because one side has no codes, the model's pathway id is used. If that id is empty or unknown, the procedure is outside the policy.
- Every `all_of` leaf must be met. Each `any_of` group needs one met leaf, or one nested `all_of` alternative whose leaves are all met. A met exclusion denies.
- A `not_met` leaf outranks a documentation gap. Gaps, with no hard contradiction, are "fix before submit."
- A quote that is not in the chart text, after whitespace and case folding, cannot support `met`. The cited words stay on the criterion as an unverified citation, and the packet asks a reviewer to find that sentence. Those leaves are scored once more, and a retried quote is kept only when it is actually in the chart. Several verbatim spans joined by a slash, ellipsis, or the word "and" are kept when every span is in the chart. The letter is built only from quotes that survived the check, and only when the outcome is ready for review.

The packet is one HTML page rendered from `determination.json`. Rendering does not score anything again.

## What breaks first

Rules that live only in a table are an extraction failure. The pathway JSON will show the damage before the outcome does.

A chart that never states the ordered procedure stops at "do not submit," because there is nothing to match. A scanned order sticker that the transcription garbles fails the same way, or matches the wrong CPT. The page markdown in `ocr/` is the place to look.

Paraphrased evidence is rejected on purpose. The packet will under-call "met" rather than cite a sentence the chart does not contain. The cited words stay visible and unverified, and they are not a denial.

A very long guideline is shortened only after it passes a character budget. Bibliography pages go first, then pages that do not look like indications, coding, or documentation requirements. A rule that lives only in a dropped page would be missed. This sample policy fits without trimming. The bibliography is the part that would go.

The sample chart and the sample vein policy are supposed to disagree. CPT 33207 is not in policy 02-33000-31. A correct packet says do not submit and does not invent vein findings or a letter.
