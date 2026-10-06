# Design

The design is meant to save clinician time. Deciding whether a patient fits a guideline, and gathering the chart facts that back that decision. This tool reads the guideline PDF and the chart PDF it was given, then writes a review packet to summarize the fit of the patient with quotes. A person confirms the quotes and submits. The tool is not meant to approve care and must be seen as a supportive role.

A run starts with a guideline PDF and a chart PDF. The model reads both, writes the criteria to `guideline.json`, and writes the ordered procedure and its quotes to `chart.json`. Python then matches the order to one pathway, checks that each quote appears in the chart, and summarizes the facts up to a headline.

## Application assumptions

- Simplicity with one command, always two PDFs: guideline and patient notes.
- The tool is not meant to make a final decision and must always reccomend and be seen as a resource to assist clinician staff
- Users will have a medical background to parse some of the information provided in the output packet
- As long as not to an unreasonable scope, token and computation load will not be heavily optimized for an initial solution
- There is no worry about security and privacy compliance for this iteration such as HIPAA

## Path of run

`pipeline.py` runs these in order.

1. **Start from the two PDFs.** Code. `cli.py`, `pipeline.py`. One result folder: `out/<chart>__<guideline>/`.
2. **Read each page.** Model. `ocr.py`, `prompts/transcribe.md`. pypdf splits the file. Each page becomes markdown. Cached by file hash under `.cache/ocr/`. The guideline and the chart are cached separately. Extraction and scoring are not cached.
3. **Shorten a very long guideline.** Code, only past 100,000 characters. `trim.py`. Bibliography pages go first, then pages that do not look like indications, coding, or documentation requirements.
4. **Pull the rules from the guideline.** Model. `extract.py`, `prompts/guideline.md`, `schemas.py`. Pathways, required facts, alternatives, exclusions, and non-covered codes. Code then gives every id a unique name, and splits a finding that is joined to a class, stage, grade, or score so each fact can be quoted on its own. `decide.py`.
5. **Pull the facts from the chart.** Model. `extract.py`, `prompts/chart.md`. The ordered procedure, its codes, and quotes. Historical procedures are not the order.
6. **Name a pathway only if the codes do not.** Model, often skipped. `extract.py`, `prompts/propose.md`. May name one pathway id, or none. Skipped when there is no order, a non-covered code already hit, exactly one pathway shares the order’s codes, or both sides have codes and none overlap.
7. **Score that pathway only.** Model, skipped when nothing matched. `extract.py`, `prompts/score.md`. Each requirement is met, not met, not documented, or not applicable. Other pathways are not scored.
8. **Recheck quotes that are not in the chart.** Model, only for quotes that missed. `extract.py`, `prompts/rescore.md`. One more ask. The new quote is kept only when those words are in the chart. `decide.py`.
9. **Decide.** Code. `decide.py`. Pick the pathway, check the quotes, write the headline. No model call.
10. **Write the packet.** Code. `render.py`. `packet.html` is rendered from `determination.json`. Rendering does not score again. The command prints that path and opens it.

Left in the result folder:

- `packet.html` — what staff read
- `determination.json` — the headline, the matched pathway, each fact, the letter
- `guideline.json` — the rules from this PDF
- `chart.json` — the order and the facts
- `ocr/` — the page text

## How the headline is chosen

| Line              | When                                                                                          | Letter                      |
| ----------------- | --------------------------------------------------------------------------------------------- | --------------------------- |
| Do not submit     | Outside this policy, a non-covered code, an exclusion, or the chart contradicts a requirement | No                          |
| Fix before submit | The order matches, and a fact is missing or a quote needs a person to confirm it              | No                          |
| Ready for review  | Every requirement has a quote that appears in the chart                                       | Yes, from those quotes only |

A person still confirms the quotes and submits.

### 1. Pick a pathway, or stop

The first stop ends the case. Nothing else is scored.

- No ordered procedure → do not submit.
- An order code is on the policy’s non-covered list → do not submit, even when a pathway name looks similar.
- Exactly one pathway shares the order’s CPT or HCPCS codes → that pathway. The model is not asked.
- Several pathways share the codes → the model’s pathway id, when it is one of them. Otherwise the pathway with the largest overlap.
- No overlap, and both sides have codes → do not submit. A model pathway name is not used. CPT 33207 against the vein policy is this case.
- No overlap because one side has no codes → the model’s pathway id, when it is a real id on this guideline. An empty or unknown id is do not submit.

### 2. Is the quote actually in the chart?

Spacing and capitalization do not matter. The words do.

- The quote is in the chart → the status stands.
- Several verbatim spans joined by a slash, ellipsis, newline, or the word “and” count when every span is in the chart.
- The quote is not in the chart → ask once more, for that leaf only. Keep the retry only when the new words are in the chart.
- It still misses → the leaf is not documented. The cited words stay on the packet for a person to confirm. They do not count as met, and they are not a denial.
- Marked met with no quote → not documented.

### 3. Inside the matched pathway

The shape comes from this PDF. The same rollup runs for every policy. A fact marked not applicable does not block the pathway.

- **AND** (`all_of`). Every fact is required.
- **OR** (`any_of`). One alternative is enough.
  - One fact. A single yes covers the group.
  - **AND inside the OR** (`all_of_options`). Several facts, all required, as one option. One contradicted fact fails that option. A gap, with no contradiction, keeps the option open.
- **Exclusion.** If this fact is met, stop. Exclusions do not go in the letter.

An OR group fails only when every alternative is not met. A gap in one alternative keeps the group open.

### 4. Which of the three headlines

A contradiction beats a missing fact.

- An exclusion is met, a required AND fact is not met, or an OR group fails → do not submit.
- A required fact is missing, or a quote is still unconfirmed → fix before submit.
- Every requirement is supported by a quote that survived the check → ready for review. The letter copies only those quotes.
- The pathway extracted with no requirements at all → fix before submit. There was nothing to check.

A payer-name mismatch adds a warning. It does not change the headline.

### Four answers for each fact

The model assigns these from `prompts/score.md`. The code rolls them up. It does not reinterpret the medicine.

- **met** — the chart supports it, and the quote is in the chart.
- **not met** — the chart says the opposite. An absent finding, or a measurement below a stated minimum. This beats a gap.
- **not documented** — the chart does not say. A recorded trial shorter than the required length counts as this. So does an unconfirmed quote.
- **not applicable** — this order is not that situation.

## Where the logic lives

- `src/prior_auth/prompts/` — what the model is told. Reading pages, filling the guideline, filling the chart, naming a pathway, scoring, rechecking a quote.
- `schemas.py` — the shape of a guideline, a chart, a score, and a determination. No payer and no procedure are hardcoded here.
- `decide.py` — pathway match, quote check, rollup, and whether a letter is allowed. It does not call a model.
- `render.py` — turns `determination.json` into `packet.html`. It does not score.

## Where it breaks

- A rule that lives only in a table can be missed. `guideline.json` shows that before the headline does.
- A chart that never states the ordered procedure stops at do not submit.
- A garbled transcription can miss or misread a CPT. The page markdown in `ocr/` is where to look.
- A paraphrase or abbreviation can cause a function to be read as not met. The words stay visible so a person can confirm them. The case under-calls rather than citing a sentence the chart does not contain.
- A guideline past the character budget can lose a rule that lived only on a dropped page. Bibliography pages go first. This sample policy fits without trimming. I am doing this to prevent overuse of tokens or time for files too long.
- A wrong pathway match means subsequent right requirements are never scored as only a first match is scored.
- The quote recheck is only run a single time to catch missed quotes. A second paraphrase stays unconfirmed and does not allow for final recommendations.

## How I would extend it

- Allow flags on the command to pass info to AI Model prompts to adjust an output if a rerun on the same guide/patient is desired.
- Add flags for scan depth to have shallower scans and allow for determining quick output on bulk patients
- A deeper logic tree than AND, OR, and AND-inside-OR: extend `schemas.py`, the guideline prompt, and `_evaluate`.
- Take a look at AI token and computation usage to determine if any parts need to be optimized or altered for cheaper / faster runtime
- A deeper set of logic on the quote rule: `verify_scores` and `merge_rescored` in `decide.py`, plus `prompts/rescore.md` if the retry instruction changes to help improve output certainty.
- Methods for rescan of an initial bad scan. Extraction still reads new markdown. Keep the cache key tied to rescanned file.

## Tradeoffs

- One model reads the pages and fills the records. A separate OCR model could do better on scans and was not used.
- Page text is cached. Extraction, scoring, and the quote recheck are not. The same PDF is cheap to reread. A prompt change always calls the model again.
- Codes select the pathway before the model names one. A model cannot move an order onto a policy that lists different codes. A policy whose codes were missed in extraction can look like “no overlap” and stop.
- Only the matched pathway is scored. The packet stays about one procedure. A wrong match means the right requirements are never checked.
- A quote has to appear in the chart. The packet under-calls met when the wording is a paraphrase. The words stay on the page, and there is one retry, not a loop.
- The logic shape is AND, OR, AND-inside-OR, and exclusions. A NOT, or a tree deeper than that, has to be flattened during extraction or it is missed.
- Long guidelines are cut only after 100,000 characters, bibliography first. Reading the PDF in several calls would keep those pages and could disagree with itself.
- The letter is written only for ready for review, and only from quotes found in the chart. A case that should not be submitted does not get persuasive language.
