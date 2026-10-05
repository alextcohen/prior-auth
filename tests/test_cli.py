import subprocess
import sys

from prior_auth.cli import open_html


def test_open_html_uses_the_platform_launcher(tmp_path, monkeypatch):
    html = tmp_path / "packet.html"
    html.write_text("<h1>Do not submit</h1>\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(args, check):
        calls.append(args)
        assert check is False

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run", fake_run)
    open_html(html)
    assert calls == [["open", str(html)]]


def test_open_html_skips_a_missing_file(tmp_path, monkeypatch):
    def fail_run(*_args, **_kwargs):
        raise AssertionError("launcher should not run")

    monkeypatch.setattr(subprocess, "run", fail_run)
    open_html(tmp_path / "missing.html")
