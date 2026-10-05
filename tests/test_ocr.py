import io
import json
from pathlib import Path

from pypdf import PdfWriter

from prior_auth.ocr import ocr_pdf, openai_read_pdf


def test_ocr_uses_the_cache_on_the_second_call(tmp_path: Path):
    pdf = tmp_path / "chart.pdf"
    pdf.write_bytes(b"%PDF-1.4 sample")
    calls = {"count": 0}

    def fetcher(filename: str, data: bytes) -> str:
        calls["count"] += 1
        assert filename == "chart.pdf"
        assert data.startswith(b"%PDF")
        return "## Page 1\n\nPacemaker planned."

    cache = tmp_path / "cache"
    first = ocr_pdf(pdf, cache_dir=cache, fetcher=fetcher)
    second = ocr_pdf(pdf, cache_dir=cache, fetcher=fetcher)
    assert first == second
    assert "Pacemaker planned." in first
    assert calls["count"] == 1
    stored = json.loads(next(cache.glob("*.json")).read_text())
    assert stored["source_name"] == "chart.pdf"


def test_openai_read_sends_each_page_as_a_pdf(monkeypatch):
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_blank_page(width=72, height=72)
    buffer = io.BytesIO()
    writer.write(buffer)
    seen: list[dict] = []

    def fake_complete(messages, *, allow_empty=False):
        seen.append(messages[1])
        assert allow_empty is True
        return f"CPT 3320{len(seen)}"

    monkeypatch.setattr("prior_auth.ocr.complete_text", fake_complete)
    markdown = openai_read_pdf("chart.pdf", buffer.getvalue())
    assert len(seen) == 2
    file_part = seen[0]["content"][0]
    assert file_part["type"] == "file"
    assert file_part["file"]["filename"] == "chart-page-1.pdf"
    assert file_part["file"]["file_data"].startswith("data:application/pdf;base64,")
    assert markdown.splitlines()[0] == "## Page 1"
    assert "CPT 33202" in markdown
    assert "\n\n---\n\n## Page 2\n\n" in markdown
