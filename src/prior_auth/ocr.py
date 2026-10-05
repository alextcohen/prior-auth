"""Mistral OCR with a content-hash cache.

The cache key is the PDF bytes, so a rerun on the same file does not call Mistral again.
"""

import base64
import hashlib
import json
import os
from pathlib import Path

from prior_auth.errors import PriorAuthError

DEFAULT_CACHE = Path(".cache") / "ocr"


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

    fetch = fetcher or mistral_ocr
    try:
        markdown = fetch(path.name, data)
    except PriorAuthError:
        raise
    except Exception as exc:
        raise PriorAuthError(f"Mistral OCR failed for {path.name}: {exc}") from exc

    if not markdown.strip():
        raise PriorAuthError(f"Mistral OCR returned no text for {path.name}.")

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps({"source_name": path.name, "markdown": markdown}, indent=2),
        encoding="utf-8",
    )
    return markdown


def mistral_ocr(filename: str, data: bytes) -> str:
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    if not api_key:
        raise PriorAuthError("Missing environment variable MISTRAL_API_KEY.")

    try:
        from mistralai.client import Mistral
    except ImportError:
        from mistralai import Mistral

    encoded = base64.standard_b64encode(data).decode("ascii")
    model = os.environ.get("MISTRAL_OCR_MODEL", "mistral-ocr-latest")
    document = {
        "type": "document_url",
        "document_url": f"data:application/pdf;base64,{encoded}",
        "document_name": filename,
    }
    with Mistral(api_key=api_key) as client:
        try:
            response = client.ocr.process(
                model=model,
                document=document,
                include_image_base64=False,
                include_blocks=False,
                timeout_ms=180_000,
            )
        except TypeError:
            response = client.ocr.process(model=model, document=document)
        pages = _page_markdowns(response)
    if not pages:
        raise PriorAuthError(f"Mistral OCR returned no pages for {filename}.")
    blocks = [f"## Page {number}\n\n{text.strip()}" for number, text in pages]
    return "\n\n---\n\n".join(blocks)


def _page_markdowns(response) -> list[tuple[int, str]]:
    pages = getattr(response, "pages", None)
    if pages is None and isinstance(response, dict):
        pages = response.get("pages")
    if not pages:
        return []
    blocks: list[tuple[int, str]] = []
    for number, page in enumerate(pages, start=1):
        if isinstance(page, dict):
            text = page.get("markdown") or ""
        else:
            text = getattr(page, "markdown", "") or ""
        blocks.append((number, text))
    return blocks


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
