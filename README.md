# Prior authorization review packet

A one-command review for clinic staff. It reads a coverage-guideline PDF and a patient-chart PDF, then writes a packet a reviewer can use before submitting prior authorization. It does not submit the request.

The packet opens with one of three lines:

- **Do not submit** — the ordered procedure is outside this policy, an exclusion applies, or the chart contradicts a required criterion.
- **Fix before submit** — the procedure matches, and at least one required fact is missing.
- **Ready for review** — every required criterion is supported by a quote that appears in the chart. A person still confirms the quotes and submits.

## Run

Export `OPENAI_API_KEY`, or copy `.env.example` to `.env` and fill it in.

```bash
uv run prior-auth --guideline Documents/guideline.pdf --chart Documents/robert_mitchell_chart_final.pdf
```

`uv run --env-file .env` loads a local `.env` if the variable is not already exported. Optional model override: `OPENAI_MODEL` (default `gpt-4.1`). That model transcribes each PDF page and fills the structured records.

Without uv:

```bash
python -m venv .venv && source .venv/bin/activate && pip install -e . && python -m prior_auth --guideline Documents/guideline.pdf --chart Documents/robert_mitchell_chart_final.pdf
```

Output lands in `out/<chart>__<guideline>/`:

- `packet.html` — the review. It opens in the browser when the command finishes.
- `determination.json` — the decision the packet is rendered from
- `guideline.json` and `chart.json` — extracted criteria and chart facts
- `ocr/` — page markdown from both PDFs

Page transcription is cached by file hash under `.cache/ocr/`. Delete that directory to force a fresh read.

## The sample pair does not match

`Documents/guideline.pdf` is BCBS Florida policy 02-33000-31, treatments for varicose veins. `Documents/robert_mitchell_chart_final.pdf` orders CPT 33207, a single-chamber pacemaker. The expected packet is **Do not submit**: that code is not in this policy. The tool is not a varicose-vein checker. Criteria come from whatever guideline PDF you pass.

## Tests

Unit tests do not call the APIs.

```bash
uv run pytest
```
