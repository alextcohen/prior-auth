# Prior authorization review packet

One command for clinic staff. A coverage-guideline PDF and a patient-chart PDF go in. A review packet comes out. A person confirms the quotes and submits. The tool does not approve care.

The path of a run, where the logic lives, and the tradeoffs are in [DESIGN.md](DESIGN.md).

The packet opens with one of three lines:

- **Do not submit** — outside this policy, a non-covered code, an exclusion, or the chart contradicts a requirement. No letter.
- **Fix before submit** — the order matches, and a required fact is missing or a quote needs a person to confirm it. No letter.
- **Ready for review** — every requirement has a quote that appears in the chart. A person still confirms the quotes and submits.

## Run

This was built and tested on macOS. The Windows and Linux commands below were not built or tested on those systems.

Export `OPENAI_API_KEY`, or copy `.env.example` to `.env` and fill it in. A local `.env` is loaded if the variable is not already exported. Optional model override: `OPENAI_MODEL` (default `gpt-4.1`). That model transcribes each PDF page and fills the structured records.

macOS:

```bash
python -m venv .venv && source .venv/bin/activate && pip install -e . && python -m prior_auth --guideline Documents/guideline.pdf --chart Documents/robert_mitchell_chart_final.pdf
```

Linux (not built or tested):

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -e . && .venv/bin/python -m prior_auth --guideline Documents/guideline.pdf --chart Documents/robert_mitchell_chart_final.pdf
```

Windows PowerShell (not built or tested):

```powershell
py -m venv .venv; .venv\Scripts\python.exe -m pip install -e .; .venv\Scripts\python.exe -m prior_auth --guideline Documents\guideline.pdf --chart Documents\robert_mitchell_chart_final.pdf
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

Unit tests do not call the APIs. They were run on macOS only.

macOS, after `pip install -e ".[dev]"`:

```bash
pytest
```

Linux (not built or tested), after `.venv/bin/python -m pip install -e ".[dev]"`:

```bash
.venv/bin/python -m pytest
```

Windows PowerShell (not built or tested), after `.venv\Scripts\python.exe -m pip install -e ".[dev]"`:

```powershell
.venv\Scripts\python.exe -m pytest
```

## Copyright

Copyright (c) 2026 Alexander Cohen. All rights reserved. See [LICENSE](LICENSE).
