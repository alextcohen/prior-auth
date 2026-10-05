"""Read a PDF into per-page markdown with OpenAI, cached by file hash.

The cache key is the PDF bytes, so a rerun on the same file does not call the model again.
Transcription is ingestion. It does not decide coverage.
"""

import base64
import hashlib
import io
import json
import re
import sys
from pathlib import Path

from prior_auth.errors import PriorAuthError
from prior_auth.llm import complete_text, load_prompt

DEFAULT_CACHE = Path(".cache") / "ocr"
_FENCE = re.compile(r"^```[a-zA-Z]*\n?|```$")


def ocr_pdf(path: Path, cache_dir: Path = DEFAULT_CACHE, fetcher=None) -> str:
    if not path.is_file():
        raise PriorAuthError(f"File not found: {path}")
    data = path.read_bytes()
    if not data:
        raise PriorAuthError(f"File is empty: {path}")

    digest = hashlib.sha256(data).hexdigest()
    cache_file = cache_dir / f"{digest}.json"
    cached = _read_cache(cache_file)
    if cached is not None:
        return cached

    fetch = fetcher or openai_read_pdf
    try:
        markdown = fetch(path.name, data)
    except PriorAuthError:
        raise
    except Exception as exc:
        raise PriorAuthError(f"PDF read failed for {path.name}: {exc}") from exc

    if not markdown.strip():
        raise PriorAuthError(f"PDF read returned no text for {path.name}.")

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps({"source_name": path.name, "markdown": markdown}, indent=2),
        encoding="utf-8",
    )
    return markdown


def openai_read_pdf(filename: str, data: bytes) -> str:
    """Transcribe each page. Page numbers follow the PDF, not the model's wording."""
    pages = pdf_pages(data)
    prompt = load_prompt("transcribe.md")
    blocks: list[str] = []
    bodies: list[str] = []
    for number, page in enumerate(pages, start=1):
        _log(f"Reading {filename} page {number} of {len(pages)}")
        text = _strip_fence(
            complete_text(
                [
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "file",
                                "file": {
                                    "filename": f"{Path(filename).stem}-page-{number}.pdf",
                                    "file_data": _data_url(page),
                                },
                            },
                            {"type": "text", "text": "Transcribe this page."},
                        ],
                    },
                ],
                allow_empty=True,
            )
        )
        bodies.append(text)
        blocks.append(f"## Page {number}\n\n{text}".rstrip())
    if not any(body.strip() for body in bodies):
        raise PriorAuthError(f"OpenAI returned no text for {filename}.")
    return "\n\n---\n\n".join(blocks)


def pdf_pages(data: bytes) -> list[bytes]:
    """One PDF per page. A file that cannot be split is sent whole."""
    try:
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(io.BytesIO(data))
        if getattr(reader, "is_encrypted", False):
            reader.decrypt("")
        if not reader.pages:
            return [data]
        pages: list[bytes] = []
        for page in reader.pages:
            writer = PdfWriter()
            writer.add_page(page)
            buffer = io.BytesIO()
            writer.write(buffer)
            pages.append(buffer.getvalue())
        return pages or [data]
    except Exception:
        return [data]


def _data_url(data: bytes) -> str:
    encoded = base64.standard_b64encode(data).decode("ascii")
    return f"data:application/pdf;base64,{encoded}"


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _FENCE.sub("", stripped).strip()
    return stripped


def _read_cache(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    markdown = payload.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        return None
    return markdown


def _log(message: str) -> None:
    print(message, file=sys.stderr)
