# Microsoft-MatchLens

Synthetic football simulation, replay, and evidence-backed local AI match intelligence. Originally built for the Microsoft × Premier League hackathon; now runnable without Azure.

## Local AI quick start

Use Python **3.12+**, Node **22+** for frontend tests, and [Ollama](https://ollama.com/download). The tested local model is `qwen3:1.7b`.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ai.txt
ollama pull qwen3:1.7b
.\.venv\Scripts\python.exe -m backend.app.server --provider ollama --port 8082
```

Open **http://127.0.0.1:8082/**. Select a shot or goal and click **Explain this moment**. The Analyst, Story, and Experience roles run through Microsoft Agent Framework and Ollama. Evidence, model status, stage timings, and token counts are visible in the insight panel. English/Hindi, casual/analyst modes, favourite team/player, metric focus, and interval recaps are supported.

The models choose a supported story, reviewed narrative frame, and presentation style. **Python calculates the statistics and renders the final wording from exact source facts.** This is constrained AI storytelling, with explicit demo/fallback labels. It does not connect to Azure Foundry or recognize video.

For a dependency-free functional preview: `python -m backend.app.server --provider demo --port 8082`. This mode performs **no AI inference**. Setup/run helpers are in `scripts/`. No Azure account or paid API key is needed for local inference.

Start with the [completion checklist and runbook](docs/PROJECT-COMPLETION.md), [agent architecture and limitations](docs/LOCAL-AGENTS.md), and [frontend AI integration contract](docs/AI-UI-INTEGRATION.md). Existing detailed simulator/UI documentation remains below.

## Current implementation

- Reproducible two-half matches with original synthetic teams and players.
- Acceleration-limited support movement, controlled carrying, live-flight player runs and recorded restart/recovery paths.
- Lane-aware passing choices and reachable lead targets, alongside interceptions, possession changes, shots and goals.
- Automatic changes in match behaviour and temporary higher pressing after conceding.
- Pass difficulty derived from intended geometry and defender positions.
- Ball and shot speeds calculated from timestamped simulated trajectories.
- Side-by-side team statistics and time-based possession, derived from events.
- Per-player statistics and explainable, role-aware 1–10 event ratings for every match.
- Rating-driven, position-compatible substitutions with bench/active lineups and exact player stint minutes.
- Whole-ball touchline/goal-line detection, throw-ins, goal kicks and corners.
- Keeper holds/parries, connected rebounds and defender clearances.
- Natural substitution stoppages, logged lost time and added-time clocks.
- Evidence-backed tackles/fouls, direct/indirect free kicks, advantage and penalties.
- Cautions, second-yellow/straight-red dismissals, emergency keepers and rating model v2.
- Contact-time point-player offside, restart exceptions, save/deflection phases and IFK decisions.
- Frozen offside evidence replay and local API for authoritative live player ratings.
- Validation, replay to the terminal, and automated tests.

This repository includes the **data generator**, buildless **Replay Studio frontend**, and **local agent backend**. A static preview (`python -m http.server 8080`, then `/frontend/`) supports replay only. Use the local AI quick start above for intelligence and authoritative prefix statistics. See [frontend/README.md](frontend/README.md) for replay controls and [docs/AI-UI-INTEGRATION.md](docs/AI-UI-INTEGRATION.md) for agent integration.

For all P1-P3 features and live player ratings, run `python -m simulator.ui_server --input data/examples/movement-match --port 8080` and open `http://127.0.0.1:8080/`. The complete teammate handoff, field mappings and copyable Sol task are in [docs/UI-INTEGRATION.md](docs/UI-INTEGRATION.md).

## Quick start

The simulator requires Python 3.10+ and no external packages. The local AI backend is tested with Python 3.12.14 and the pinned packages in `requirements-ai.txt`. Replace `py -3.13` below with `.\.venv\Scripts\python.exe` when using the project environment.

From the repository root, on Windows:

```powershell
py -3.13 -m simulator.generate --seed 42 --output data/generated/evolving-match
py -3.13 -m simulator.replay --input data/generated/evolving-match --speed 60
```

On systems where Python is exposed as `python` or `python3`, substitute that executable. Replay prints JSON events; it does not display a visual match.

For ten regulation minutes plus added time (two five-minute halves):

```powershell
py -3.13 -m simulator.generate --seed 51 --minutes-per-half 5 --output data/generated/priority-one-demo
```

The same version, seed, profile, and duration reproduce the same match. Output folders are overwritten when reused. Generated matches under `data/generated/` are ignored by Git. The current showcase is `data/examples/movement-match/`; legacy fixtures remain available.

## Output

| File | Contents |
|---|---|
| `metadata.json` | Rosters, pitch dimensions, direction, clock, model assumptions |
| `events.jsonl` | Ordered match events, pitch snapshots, ball observations, calculated metrics |
| `summary.json` | Team statistics, possession, `players` records, `player_rating_model`, difficulty/speed summaries |
| `evaluation-only.json` | Internal scenario/behaviour changes for debugging; exclude from narrative/detector input |

## Tests

```powershell
py -3.13 -m unittest discover -s simulator -p "test_*.py" -v
```

Tests cover reproducibility, multiple seeds, event consistency, geometry-based outcomes, metric calculations, corruption rejection, and goal-triggered progression.

## Team handoff

- [Movement/pass realism model and UI migration](docs/REALISM-AND-MOVEMENT.md)
- [Generator instructions and metric definitions](simulator/README.md)
- [UI and virtual board integration](docs/UI-INTEGRATION.md)
- [Player statistics and rating definitions](docs/PLAYER-RATINGS.md)
- [Substitutions and frontend integration](docs/SUBSTITUTIONS.md)
- [Priority 3 offside and evidence contract](docs/OFFSIDE.md)
- [Priority 2 fouls, cards, set pieces and UI contract](docs/DISCIPLINE-AND-SET-PIECES.md)
- [Priority 1 implementation, clock migration and UI contract](docs/RESTARTS-AND-CLOCK.md)
- [Match-realism checklist and priorities](docs/MATCH-REALISM-CHECKLIST.md)
- [Hackathon approach and stack audit](MatchLens-Hackathon-Guide.md)

The pipeline is **shared pitch state → action → resolved outcome → event evidence → metrics**. Randomness drives synthetic player skills and choices; reported metrics are calculated from the resulting evidence.

To add team statistics to an existing match without regenerating or changing its events:

```powershell
py -3.13 -m simulator.statistics --input data/generated/evolving-match
```

Read `summary.teams.home` and `summary.teams.away` for comparable metrics. Possession percentages use each team's possession-phase time, exclude unassigned gaps, and sum to 100 when some possession has been observed. See the UI guide for exact definitions and live updates.

`summary.players` contains every roster player's action statistics, speed/difficulty distributions, assists/key passes, and a rating breakdown. Scores use only recorded events, are position-aware heuristics, and remain NR when evidence is insufficient. The same statistics command upgrades existing match summaries with player records without regenerating their events. See [rating definitions](docs/PLAYER-RATINGS.md) for weights, evidence links, and limitations.

## Limitations

This is a simplified, uncalibrated 2D simulation, not professional match tracking. It does not model offside, ball height, every offence in the Laws, or complete goalkeeper/restart physics. Player snapshots are not continuous tracking. Difficulty is a heuristic, not a probability; speeds are synthetic pitch-plane measurements. See the generator documentation for detailed assumptions.

New schema 1.6 matches include 11 starters and nine bench players per team, mainly 60–70 minute substitutions, and occasional half-time changes. Substitutions now wait for ball-out, goal or foul stoppages. Added time extends both halves: consumers must use `match_time_ms`, actual period offsets and `match_duration_ms`, as described in the Priority 1 guide. Offsides and the remaining realism gaps are documented on the checklist; they are not yet generated.


Priority 2 showcase: `py -3.13 -m simulator.generate --seed 6 --output data/generated/priority-two-demo`. Load its metadata/events into Replay Studio, or use `data/examples/discipline-match/`. The UI adapter handles reduced lineups, shown-card badges, advantage carries, current keeper assignments and new side-by-side counters. Read the Priority 2 guide before assuming 22 active markers or using original keeper IDs.

### Expected goals (schema 1.9)

Every new shot has an explainable, uncalibrated pre-shot xG estimate based on its original geometry. Team and player statistics now include xG, non-penalty xG, xG per shot, goals minus xG, xG assisted, shot conversion/accuracy and coverage. The replay shows team comparisons, player metrics and shot evidence. Existing fixtures derive xG from their recorded frames. See [the model and UI integration guide](docs/EXPECTED-GOALS.md) and the small `data/examples/xg-match` fixture.
