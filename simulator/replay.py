"""Replay JSONL to stdout using event time, without contacting any service."""
import argparse
import json
import time
from pathlib import Path

from simulator.generate import validate


def scheduled_time(event, period_duration_ms):
    return (event["period"] - 1) * period_duration_ms + event["period_time_ms"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/generated/demo"))
    parser.add_argument("--speed", type=float, default=60)
    parser.add_argument("--no-delay", action="store_true")
    args = parser.parse_args()
    if not 0 < args.speed < float("inf"):
        parser.error("--speed must be finite and greater than zero")
    for filename in ("metadata.json", "events.jsonl"):
        if not (args.input / filename).is_file():
            parser.error(
                f'Match file not found: {args.input / filename}. '
                'Generate this match first with: '
                f'py -3.13 -m simulator.generate --seed 42 --output "{args.input}"'
            )
    metadata = json.loads((args.input / "metadata.json").read_text(encoding="utf-8"))
    events = [json.loads(line) for line in (args.input / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]
    validate(metadata, events)
    started = time.monotonic()
    for event in events:
        target = scheduled_time(event, metadata["period_duration_ms"]) / 1000 / args.speed
        if not args.no_delay:
            remaining = target - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)
        print(json.dumps(event), flush=True)


if __name__ == "__main__":
    main()
