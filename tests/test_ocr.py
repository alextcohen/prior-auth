import json
from pathlib import Path

from prior_auth.ocr import ocr_pdf


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
