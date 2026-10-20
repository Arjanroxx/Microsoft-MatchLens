# Virtual board handoff

The frontend can be developed entirely from the generated data. No video detection or recognition is required to start.

## Inputs

Use `data/examples/short-match/` as a checked-in fixture, or generate a new match using the root README. Load `metadata.json` and parse `events.jsonl` one line at a time. `summary.json` is useful for a final recap, but do not show its final score during live playback: calculate the current score from goal events instead.

`evaluation-only.json` describes simulator behaviour for debugging. Do not use it to manufacture detected tactical narratives or feed it to the AI. Analytical observations should come from actual match events and geometry.

## Clock and pitch

- Pitch coordinates are metres on a fixed 105 × 68 pitch; read dimensions from metadata.
- Convert to board pixels: `x / length_m * width_px`, `y / width_m * height_px`. Flip y if the board uses a bottom-left origin and the browser uses top-left.
- Home attacks positive x in period 1 and negative x in period 2; the physical coordinate system itself does not change at half-time.
- Use `sequence` to break timestamp ties. Deduplicate using `(match_id, event_id)`.
- Continuous playback time is `(period - 1) * period_duration_ms + period_time_ms`.
- Pause, seek, and replay speed must use one shared playback clock.

## Player and ball rendering

Each pass and shot includes:

- `pitch_snapshot.period_time_ms`: kick timestamp within the half.
- `pitch_snapshot.players`: all player IDs mapped to `x_m` and `y_m` at kick time.
- `ball_trajectory`: samples with `period_time_ms`, `x_m`, and `y_m`.
- `start` and `end`: actual ball origin and destination.

Join player IDs to names, teams, shirts, and roles from `metadata.players`. Draw home and away markers in different colours. Ignore roles/skills for display unless useful to the user.

Player positions are snapshots, not full movement tracks. You may interpolate between snapshots for a smooth illustration, but that animation is not an additional measured data source. Ball animation can interpolate directly between trajectory samples.

Pass/shot event timestamps represent **completion/arrival**. For a preloaded synthetic replay, expand each action into a kick-time snapshot, trajectory samples, and a completion-time outcome. Schedule all of those by their own timestamps. Do not reveal success, a goal, or completed-action metrics before completion.

Terminal replay currently emits the full action only at completion. A future true streaming renderer should use either a delayed shared playback clock or an expanded observation stream. It cannot animate the past kick on time using a message that only arrived after the ball landed.

On seeking, rebuild the score and latest visible state up to the target time and clear expired arrows/cards.

## Pass graphics and metrics

- `intended_recipient_id` and `intended_end`: the attempted recipient and target.
- `recipient_id`: successful recipient, or null on failure.
- `end`: actual destination, including interceptions.
- `distance_m`: actual distance; `intended_distance_m`: intended pass distance.
- `pass_difficulty.score` / `.rating`: 0–100 heuristic and easy/moderate/hard label.
- `difficulty_context`: defender proximity, lane congestion, and supporting defender IDs.
- `ball_speed.average_kmh`: whole-flight mean ball speed.

Use a solid line for actual travel and an optional dashed continuation for the intended destination on an intercepted pass. Explain difficulty using intended geometry, not the shortened intercepted distance. Calculate pass accuracy as completed/attempted, with an unavailable value when there are no attempts.

## Shots and score

`shot_speed.kmh` describes the first sampled interval after the kick; `ball_speed.average_kmh` is the entire flight average. Label these accurately. On goal events, use their running `score`. A scoring shot is followed by a separate goal event: do not count both as two goals.

## Suggested first screen

1. Pitch with team/player markers and ball.
2. Play/pause, seek, speed, clock, and current score.
3. Completed pass arrows and shot trails.
4. Event list linked to the pitch time.
5. Selected-player details and difficulty/speed cards.

Keep the data-reader boundary separate from the renderer. A future backend or video adapter should be able to supply normalised observations/events without replacing the board.

## Side-by-side team statistics

`summary.json` now includes `teams.home` and `teams.away` with the same structure. Use these for the two columns; the older top-level pooled `synthetic_metrics` remains for backwards compatibility and is not the team comparison source.

| Display row | Field below each `teams.<team>` |
|---|---|
| Team name / goals | `name`, `goals` |
| Possession | `possession.percentage` |
| Possession time | `possession.time_seconds` |
| Pass attempts / completions / failures | `passes.attempted`, `passes.completed`, `passes.incomplete` |
| Pass accuracy | `passes.accuracy_percentage` |
| Actual / intended pass distance | `metrics.pass_distance_m.mean`, `metrics.intended_pass_distance_m.mean` |
| Pass difficulty | `metrics.pass_difficulty_score.mean` |
| Pass ball speed | `metrics.pass_average_ball_speed_kmh.mean` |
| Fastest pass segment | `metrics.pass_peak_segment_ball_speed_kmh.max` |
| Shots / on target / off target | `shots.total`, `shots.on_target`, `shots.off_target` |
| Shot initial speed / fastest initial shot | `metrics.shot_initial_segment_speed_kmh.mean` / `.max` |
| Whole-flight shot speed | `metrics.shot_average_ball_speed_kmh.mean` |
| Peak shot segment speed | `metrics.shot_peak_segment_speed_kmh.max` |
| Whole-flight ball speed across actions | `metrics.ball_average_speed_kmh.mean` |
| Defensive actions | `saves`, `interceptions`, `recoveries`, `turnovers`, `pressure_events` |
| Possession sequences | `possessions` |

Each metric distribution includes `count`, `min`, `mean`, and `max`. No observations means count zero and null values: display a dash, not zero speed or 0% accuracy. Means of speed metrics are event-weighted means of per-action speeds, not time-weighted motion averages. `pressure_events` counts recorded pressure observations, not distinct pressing episodes. Interceptions are credited to the defending team; saves to the opponent of the shooter. Count a goal event once, not once again for its scoring shot.

### Possession definition

This project uses `team_phase_time_v1`, a defined event-based convention rather than a claim of official broadcast methodology:

- A restart or recovery starts a team's possession phase.
- Pass flights, including unsuccessful attempts until the turnover timestamp, belong to that passing team's phase.
- Turnovers end that phase; any wait until the next recovery is unassigned.
- Shot flight is unassigned from the kick timestamp; the preceding preparation interval belongs to the attacking team.
- Goal-to-kickoff gaps and time outside known possession phases remain unassigned.
- Period boundaries stop possession. Half-time adds no playing time.
- Team percentage = team phase milliseconds / (home + away phase milliseconds). The denominator excludes unassigned time; available team shares sum to 100.

The top-level `possession` object reports `controlled_time_ms`, `elapsed_time_ms`, and `unassigned_time_ms` / `unassigned_time_percentage`. `controlled_time_ms` is the sum of the two attributed team phases, including pass flights; it is not continuous ball-contact time. Each team's `elapsed_time_percentage` uses the entire elapsed clock instead, so those two values may sum to less than 100. Do not mix these two denominator conventions in a comparison.

### Live snapshots without future results

Do not use the final summary as live match statistics. The backend can share the deterministic reducer:

```python
from simulator.statistics import MatchStatistics, calculate_statistics

reducer = MatchStatistics(metadata)
for event in incoming_events:
    reducer.update(event)
live = reducer.snapshot(as_of=(current_period, current_period_time_ms))

# For preloaded replay, rebuild a prefix after a seek:
live = calculate_statistics(metadata, events, as_of=(current_period, current_period_time_ms))
```

Only process events through the current playback time. The reducer ignores duplicate IDs and does not use metadata's final score. Snapshots can extend the last known possession to the current clock without mutating stored totals. To rewind or apply a correction, rebuild from the appropriate event prefix; do not feed backwards events into an existing reducer.

Since action records arrive at completion, the exact shot release becomes known when its shot record arrives. Possession for that flight is then reclassified as unassigned. Until resolution, a streaming snapshot extends the last known owner provisionally. The UI can label the value live/estimated rather than implying continuous contact measurement.

Existing matches can have these additive summary fields recalculated without changing their event files:

```powershell
py -3.13 -m simulator.statistics --input data/generated/evolving-match
```
