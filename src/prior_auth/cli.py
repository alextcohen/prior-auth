"""Command line entry point."""

import argparse
import os
import re
import sys
import traceback
from pathlib import Path

from prior_auth.errors import PriorAuthError
from prior_auth.pipeline import run_case


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"))
    parser = argparse.ArgumentParser(
        prog="prior-auth",
        description=(
            "Build a prior authorization review packet from a coverage guideline PDF "
            "and a patient chart PDF."
        ),
    )
    parser.add_argument("--guideline", required=True, type=Path, help="Coverage guideline PDF")
    parser.add_argument("--chart", required=True, type=Path, help="Patient chart PDF")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory. Default: out/<chart>__<guideline>/",
    )
    args = parser.parse_args(argv)
    out_dir = args.out or default_out_dir(args.chart, args.guideline)
    try:
        _require_files(args.guideline, args.chart)
        _require_env()
        packet = run_case(args.guideline, args.chart, out_dir)
    except PriorAuthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1
    print(packet)
    return 0


def default_out_dir(chart: Path, guideline: Path) -> Path:
    return Path("out") / f"{_stem(chart)}__{_stem(guideline)}"


def load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines that are not already in the environment."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _require_files(guideline: Path, chart: Path) -> None:
    missing = [str(path) for path in (guideline, chart) if not path.is_file()]
    if missing:
        raise PriorAuthError("File not found: " + ", ".join(missing))


def _require_env() -> None:
    missing = [name for name in ("OPENAI_API_KEY",) if not os.environ.get(name)]
    if missing:
        raise PriorAuthError(
            "Missing environment variable(s): "
            + ", ".join(missing)
            + ". Copy .env.example to .env or export them."
        )


def _stem(path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip("-")
    return stem or "document"


if __name__ == "__main__":
    raise SystemExit(main())
