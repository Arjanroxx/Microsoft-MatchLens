# Microsoft-MatchLens

Synthetic football match simulation and explainable match intelligence for the Microsoft × Premier League hackathon.

## Current implementation

- Reproducible two-half matches with original synthetic teams and players.
- Persistent pitch positions, passes, interceptions, possession changes, shots, and goals.
- Automatic changes in match behaviour and temporary higher pressing after conceding.
- Pass difficulty derived from intended geometry and defender positions.
- Ball and shot speeds calculated from timestamped simulated trajectories.
- Validation, replay to the terminal, and automated tests.

This repository currently provides the **data-generation layer**. A virtual board, UI, AI narratives, cloud deployment, and video recognition are not implemented.

## Quick start

Python 3.10+ is required; Python 3.13 is the development baseline. No external Python packages are required.

From the repository root, on Windows:

```powershell
py -3.13 -m simulator.generate --seed 42 --output data/generated/evolving-match
py -3.13 -m simulator.replay --input data/generated/evolving-match --speed 60
```

On systems where Python is exposed as `python` or `python3`, substitute that executable. Replay prints JSON events; it does not display a visual match.

For a ten-minute demonstration (two five-minute halves):

```powershell
py -3.13 -m simulator.generate --seed 123 --minutes-per-half 5 --output data/generated/short-match
```

The same version, seed, profile, and duration reproduce the same match. Output folders are overwritten when reused. Generated matches under `data/generated/` are ignored by Git. A small checked-in example is available in `data/examples/short-match/`.

## Output

| File | Contents |
|---|---|
| `metadata.json` | Rosters, pitch dimensions, direction, clock, model assumptions |
| `events.jsonl` | Ordered match events, pitch snapshots, ball observations, calculated metrics |
| `summary.json` | Score, counts, pass accuracy, difficulty/speed summaries |
| `evaluation-only.json` | Internal scenario/behaviour changes for debugging; exclude from narrative/detector input |

## Tests

```powershell
py -3.13 -m unittest discover -s simulator -p "test_*.py" -v
```

Tests cover reproducibility, multiple seeds, event consistency, geometry-based outcomes, metric calculations, corruption rejection, and goal-triggered progression.

## Team handoff

- [Generator instructions and metric definitions](simulator/README.md)
- [UI and virtual board integration](docs/UI-INTEGRATION.md)
- [Hackathon approach and stack audit](MatchLens-Hackathon-Guide.md)

The pipeline is **shared pitch state → action → resolved outcome → event evidence → metrics**. Randomness drives synthetic player skills and choices; reported metrics are calculated from the resulting evidence.

## Limitations

This is a simplified, uncalibrated 2D simulation, not professional match tracking. It does not model offside, fouls, ball height, or complete goalkeeper/restart physics. Player snapshots are not continuous tracking. Difficulty is a heuristic, not a probability; speeds are synthetic pitch-plane measurements. See the generator documentation for detailed assumptions.
