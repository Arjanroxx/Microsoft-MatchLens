# Synthetic match data: first working version

This generator creates original, explicitly synthetic event streams. No downloaded football data, real player identities, cloud account, AI model, paid service, or third-party Python package is needed.

## What you need to do

1. Install Python 3.13 if you do not already have Python 3.10 or newer. On Windows, `winget install --exact --id Python.Python.3.13`, then reopen your terminal.
2. Open a terminal in the Microsoft Hackathon workspace folder.
3. Generate a match using a command below.
4. Inspect `summary.json`, `metadata.json`, and the first few lines of `events.jsonl`.
5. Replay it, then connect that stream to the application's ingestion endpoint once the backend exists.

The Windows Python launcher was present when this was created, but it reported no installed Python runtimes. The initial checks used Codex's bundled Python; a normal Python installation is recommended for team development.

## Generate and test

For an ordinary evolving match, use the default mode. There is no need to choose a fixed scenario:

```powershell
py -3.13 -m simulator.generate --seed 42 --output data/generated/evolving-match
py -3.13 -m simulator.replay --input data/generated/evolving-match --speed 60
```

In this mode each team changes behaviour independently every **5–8 match minutes**. After conceding, that team adopts higher pressing for **three match minutes**. The reaction takes priority over interval changes, then the team returns to its current scheduled behaviour. These are simulation design choices, not a claim that real teams always react this way. A goal does not guarantee a recovery, equaliser, or successful press.

Behaviours are simple internal rules: balanced play, higher pressing, patient possession, or quicker decisions. They change existing movement and action selection. You do not configure formations or tactics. Changes apply at the next action decision, with player positions still moving gradually rather than jumping to a new shape. Post-goal pressing affects the conceding team when it next defends; the conceding team first receives the kickoff.

For short demos, both the interval and reaction duration scale down. Timing uses playing time; a response near the end of a half can carry into the next half. The simplified clock does not model a 15-minute half-time break.

`evaluation-only.json` records the actual applied behaviour changes, their reasons, and the goal event ID behind each response. It is a debugging record, not an input to analytics. Match narratives must still be inferred from passes, pressure, shots, and other observations.

The older profiles below remain available for controlled tests:

```powershell
py -3.13 -m simulator.generate --seed 42 --scenario balanced --output data/generated/balanced
py -3.13 -m simulator.generate --seed 42 --scenario high-press --output data/generated/high-press
py -3.13 -m simulator.generate --seed 42 --scenario quiet-possession --output data/generated/quiet-possession
py -3.13 -m simulator.generate --seed 42 --scenario chaotic --output data/generated/chaotic
py -3.13 -m unittest simulator.test_generate simulator.test_metrics simulator.test_pitch simulator.test_progression -v
```

Use `python` instead of `py -3.13` if that is how your environment exposes Python. Same generator version, seed, scenario, and duration produce identical content. Output files in the selected folder are replaced on rerun; choose a new output folder to keep an earlier run. Schema **1.3** adds automatic progression to the persistent pitch simulation and includes the version in match IDs so regenerated data is distinct from old fixtures. The default `--scenario` is now `match`; `balanced` is a separate baseline test profile.

## One simulated match, then calculated metrics

The architecture is **pitch state → player action → resolved outcome → event evidence → metrics**. We do not sample a pass-difficulty score or a measured speed as an unrelated random number. These deterministic calculations live in `metrics.py`; the match process and actions live in `engine.py`; persistent positions and geometry live in `pitch.py`.

- All 22 players have persistent positions, roles, and seeded skill attributes. Between actions, they move toward formation/ball-related targets at a maximum 4.5 m/s. The carrier stays at the ball during the decision interval.
- A pass targets an actual teammate's position. Choice of teammate, kick effort, and execution error are seeded action inputs—the uncertainty of the simulated match.
- Defender proximity and passing-lane congestion are measured from the same kick-time player positions. The nearest defender produces a pressure event only when within 2.5 m.
- The kick creates ball samples. A defender who can reach the pass path in time intercepts it; otherwise the intended receiver must be able to reach the landing point. This resolves success/failure, actual ball endpoint, and the next possession.
- The ball remains at the last action endpoint until the next action. A completed pass transfers control to its recipient. Planning another batch of actions does not force a turnover.
- Shots are considered within 25 m of the opponent's goal line and within 18 m of the pitch centreline. Their result follows the goal-mouth position and goalkeeper reach, rather than an independent goal-probability draw. Goalkeepers retain goal-side positioning.
- Distance, speeds, difficulty, and accuracy aggregates are then calculated from those events and their evidence. Validators reconstruct context, action resolution, trajectories, and metrics to check consistency.

Every pass/shot contains a `pitch_snapshot` of all players at kick time. This makes the chain inspectable and supports a future pitch animation. It is a basic 2D simulation, not a professional physics engine: players are frozen during ball flight except for the receiver/interceptor (or saving keeper); fouls, offside, goalkeeper dives, ball height, and continuous off-ball trajectories are not modelled. Non-goal shots simplify to opponent recoveries rather than explicit goal kicks/corners/rebounds. Event and scoring distributions still need calibration against a documented target before claiming football realism.

The earlier version sampled defender proximity/lane counts independently. Version 1.2 replaces that design; do not use old schema 1.1 fixtures to demonstrate shared-state difficulty.

For a shorter fixture, add `--minutes-per-half 5`. Default duration is two 45-minute halves. This is a simplified continuous-play clock without stoppage time or a real-time half-time interval.

## Output files

| File | Purpose |
|---|---|
| `metadata.json` | Synthetic teams, 22 players, pitch dimensions, directions, seed, final score, limitations |
| `events.jsonl` | One event per line; the future ingestion input |
| `summary.json` | Team/player metrics, event-based ratings, possession, final score, and pooled distributions for compatibility |
| `evaluation-only.json` | Intended scenario window and scripted shot references; never provide this to insight detectors |

Events include period boundaries, restarts, passes, pressure, turnovers, recoveries, shots, and goals. Not every profile or seed must produce every type. Tackles, fouls, substitutions, tracking, and corrections are not implemented yet.

Only feed `events.jsonl` and the necessary roster/pitch metadata to analytics. The metadata match ID contains the scenario name for human traceability: detectors must treat IDs as opaque and must not read the seed, filename, scenario labels, or evaluation-only file to infer stories. Use neutral external IDs when building a blinded evaluation.

## Scenario design

- **match (default):** evolving behaviour for each team, with interval changes and temporary higher pressing after conceding.
- **balanced:** teammate selection favours progression and space; shots are considered in attacking positions.
- **high-press:** a five-minute window in each full-length half where two home defenders chase the away carrier. Failed passes, recoveries, and shots emerge from geometry; no fixed number of chances or forced narrative is guaranteed.
- **quiet-possession:** longer lateral/backward-biased passing chains in the scenario window, without shots in those chains.
- **chaotic:** shorter possessions and more frequent turnovers in the scenario window.

For shortened halves, the scenario window is compressed to fit. Outside the window all profiles use the baseline process. Measure actual output rather than assuming the profile label proves a particular insight.

## Replay

```powershell
py -3.13 -m simulator.replay --input data/generated/high-press --speed 60
```

At 60×, a nominal 90-minute match takes about 90 seconds to emit. Event timestamps stay in match time. Replay writes JSON lines to the terminal; it does not yet send HTTP requests, stream through a browser, or render overlays. To inspect without waiting:

```powershell
py -3.13 -m simulator.replay --input data/generated/high-press --no-delay
```

## Data contract

Coordinates are metres on a fixed 105 × 68 pitch. Home attacks positive x in period 1 and negative x in period 2. `period_time_ms` is elapsed time within that half. Pass and shot event times represent ball arrival/action completion; the first trajectory sample gives the kick time. Events expose the complete trajectory only at completion, so replay does not reveal future observations. Tied timestamps are ordered by `sequence`; they are intentional for related event records. `event_id` is unique within a match; consumers should deduplicate by `(match_id, event_id)`.

Completed passes name a recipient on the same team. Incomplete passes have no successful recipient but retain `intended_recipient_id`. `intended_end` is that teammate's position at kick time; `end` is the resolved arrival/interception point. `distance_m` is actual straight-line ball displacement; `intended_distance_m` describes the attempted pass. Pressure has the defending team as actor and refers to the attacking possession. Goal records reference a preceding scoring shot; count goals once rather than adding shot and goal records together.

No player running distance, xG, xT, historical records, or calibrated pass-completion probability is generated. Ball trajectories, speeds, and pass difficulty are now included as explicitly synthetic fields, as defined below.

## Pass difficulty: transparent 0–100 heuristic

`pass_difficulty` contains `score`, `rating`, model version, component values, and weights. It uses the **intended** pass and kick-time defender positions, before knowing the result. Otherwise an intercepted long pass could incorrectly become an easy short pass after the fact. A difficult pass can succeed; an easy pass can fail. The score is not a fitted completion probability. Outcome resolution uses actual ball/defender/receiver geometry from the same state.

```text
distance_component = min(intended_pass_distance_m / 60, 1)
pressure_component = max(0, 1 - nearest_defender_m / 5)
forwardness_component = max(0, attacking_direction * dx / intended_pass_distance_m)
lane_component = min(defenders_in_lane / 3, 1)

score = round(40*distance_component + 25*pressure_component
              + 20*forwardness_component + 15*lane_component)
```

Forwardness is zero for a zero-length pass. Attacking direction changes by team/half. Ratings: **easy <35**, **moderate 35–64**, **hard ≥65**. The thresholds, weights, and 60-metre distance scale are design choices, not established football standards.

Nearest-defender distance is the minimum distance from the carrier to an opponent in `pitch_snapshot`. Lane congestion counts opponents within 2 m of the intended pass segment, excluding points behind the passer or beyond the receiver. Both values and supporting defender IDs are stored in `difficulty_context`. The score saturates lane contribution at three defenders, while retaining the full measured count. These are simplified definitions, not claims of tactical model calibration.

## Ball speed and shot speed

Every pass/shot includes `ball_trajectory`: timestamped `x_m`, `y_m` samples, normally 50 ms apart, plus the exact arrival sample. It also includes `ball_speed` calculated from those samples:

- `average_mps` / `average_kmh`: total sampled path length divided by elapsed time.
- `peak_segment_mps`: highest speed across adjacent samples.
- `initial_segment_mps` / `initial_segment_kmh`: first adjacent-sample speed.
- `duration_ms`, `distance_m`, and `initial_segment_duration_ms`: inspectable evidence.

Formula: `m/s = distance_metres / elapsed_seconds`; `km/h = m/s × 3.6`.

Shots additionally expose `shot_speed.mps`, `.kmh`, and `.window_ms`, with method `initial_segment_average`. This is a near-kick sampled estimate, not an exact instantaneous launch speed. For flights shorter than 50 ms the window is shorter and is recorded explicitly. Whole-flight averages remain in `ball_speed`.

Kick effort is a seeded action choice in the range 0.2–1, stored in `kick`. Commanded mean pass speed is `min(24, 8 + 0.28*intended_distance_m + 3*effort)` m/s. Commanded mean shot speed is `20 + 12*effort + 2*shooting_skill` m/s. These are explicit simulation controls, not separately generated output metrics or researched professional benchmarks. Player skill affects pass execution error; pressure increases that error. Flight duration follows actual path length and the kick command, rounded up to whole milliseconds. Measured speeds are recomputed from samples rather than copied from the command.

Passes move uniformly on a straight 2D path. Shots use fraction `1.2*u - 0.2*u²` of the path at time fraction `u`, giving declining speed. There is no ball height, drag solver, bounce, curved flight, or camera inference. Pass interceptions consider a defender's closest projection onto the ball path and whether they can reach it at 4.5 m/s before the ball arrives; this is an approximation, not continuous collision physics.

Sample fragments (field values are illustrative):

```json
{
  "pass_difficulty": {"score": 57, "rating": "moderate", "model": "heuristic-v1", "is_probability": false},
  "ball_speed": {"source": "synthetic_trajectory", "average_mps": 10.0, "average_kmh": 36.0},
  "shot_speed": {"source": "synthetic_trajectory", "method": "initial_segment_average", "mps": 35.7, "kmh": 128.52, "window_ms": 50}
}
```

`pass_difficulty` belongs on passes and `shot_speed` on shots; the fragment lists fields together only for illustration. See actual JSONL for complete records.

## What has been checked

### Team statistics and possession

All applicable metrics are now also aggregated separately in `summary.teams.home` and `summary.teams.away`: goals, passes/accuracy, shot counts, saves, interceptions, recoveries, turnovers, pressure observations, possession sequences, and distance/difficulty/speed distributions. An empty distribution has null values rather than invented zero measurements.

Possession comes from elapsed event time, not event counts. Restart/recovery begins a team's phase; passes stay within that phase until a recorded loss. Shot flights are excluded from the kick onward; loose-ball intervals, restart gaps, and intervals without a known owner remain unassigned. Team possession percentages use only the two attributed team phases. Raw times and the unassigned portion are exposed alongside the percentages. This is a documented simulation convention, not a claim to match a provider's possession methodology.

Use the shared reducer for live snapshots or the current event prefix; do not show a final summary early. See `docs/UI-INTEGRATION.md` for field paths, exact timing rules, and code examples. To upgrade an existing summary without regenerating events:

```powershell
py -3.13 -m simulator.statistics --input data/generated/evolving-match
```

The command validates the existing events and updates only `summary.json`. It preserves older pooled fields for compatibility. Newly generated matches include the team fields automatically. Run all tests with:

```powershell
py -3.13 -m unittest discover -s simulator -p "test_*.py" -v
```

### Validation coverage

Player records are now included automatically for every roster ID in `summary.players`, with a versioned `summary.player_rating_model`. Goals, passes, receptions, shots, interceptions, recoveries, saves, pressure observations, and linked assists/key passes come from the event stream. Ratings use only those actions and role metadata, not latent player skill or unrelated random scores. See `docs/PLAYER-RATINGS.md` for the formula, eligibility, evidence, and UI fields. The existing statistics recalculation command adds these to older matches without changing events.

The tests cover reproducible seeds, all four profiles across multiple seeds, event ordering, valid players/teams, bounds, pass continuity, score consistency, and rejection of selected corruptions. Metric tests check a known 30 m / 3 s trajectory (10 m/s; 36 km/h), direction-normalised difficulty, pressure/distance/congestion effects, zero-distance trajectories, invalid timestamps, initial versus average shot speed, and rejection of altered metric values. Pitch tests move defenders while holding the attempt fixed: context/difficulty must change, and a blocked pass becomes an interception while the open version succeeds. Movement is bounded, and doubled traversal speed produces doubled measured speed. This checks causality and engineering invariants, not realism against professional match distributions.

## Next team tasks

1. Data owner: review output with a football-aware teammate and document plausible target distributions before tuning probabilities.
2. Backend owner: ingest these events, suppress duplicates, update pass totals, and calculate shots after high recoveries.
3. AI owner: take only computed evidence; write two audience variants and factual fallback text.
4. Interface owner: map fixed pitch coordinates to a pitch view and drive its clock from replay time.

Next generator extensions should be intentional: tackles with distinct success outcomes, fouls/restarts, roster substitutions, player tracking if running metrics are needed, and adversarial copies with duplicate/delayed/corrected events. Keep clean source fixtures separate from intentionally corrupted ingestion tests. Reserve unseen seeds for evaluation. Video auto-eventing remains out of scope.
