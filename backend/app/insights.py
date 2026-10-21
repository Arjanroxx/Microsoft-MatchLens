"""Command-line entry point for the backend explainability prototype.

Example:
    python -B -m backend.app.insights \
        --input data/examples/short-match/summary.json \
        --team home --mode casual
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evidence import EvidenceError, build_evidence_packet
from .narrative import generate_insight
from .providers import LocalDemoProvider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate one evidence-backed football insight from team statistics."
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to summary.json or a JSON object with a teams mapping.",
    )
    parser.add_argument(
        "--team",
        choices=("home", "away"),
        default="home",
        help="Team to focus the insight on (default: home).",
    )
    parser.add_argument(
        "--mode",
        choices=("casual", "analyst"),
        default="casual",
        help="Audience style (default: casual).",
    )
    parser.add_argument(
        "--match-id",
        default=None,
        help="Optional match ID for live snapshots that do not include one.",
    )
    args = parser.parse_args(argv)

    if not args.input.is_file():
        parser.error(f"Input file does not exist: {args.input}")

    try:
        summary = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        print(f"Could not read input: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"Input is not valid JSON: {exc}", file=sys.stderr)
        return 2

    try:
        packet = build_evidence_packet(
            summary,
            focus_team=args.team,
            match_id=args.match_id,
        )
    except EvidenceError as exc:
        print(f"Evidence error: {exc}", file=sys.stderr)
        return 2

    provider = LocalDemoProvider(packet, args.mode)
    result = generate_insight(packet, args.mode, provider)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
