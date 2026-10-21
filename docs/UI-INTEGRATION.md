# Virtual board handoff

**Current schema: 1.6.** Priority 2 now adds tackles/fouls, advantage, direct/indirect free kicks, penalties, bookings and dismissals. Read [DISCIPLINE-AND-SET-PIECES.md](DISCIPLINE-AND-SET-PIECES.md) for the full UI contract, rating v2, reduced lineups, emergency keeper identity and demo commands. Priority 1 remains implemented end to end: ball-out/last-touch awards, throw-ins/goal kicks/corners, holds/parries/rebounds/clearances, natural substitution opportunities and added time. Read [RESTARTS-AND-CLOCK.md](RESTARTS-AND-CLOCK.md) for the full event contract, clock migration, statistics mapping, demo and frontend acceptance checklist. The existing `model.mjs` and main screen already support the new timeline, ball actions and team counters.

Player data extension: `summary.players` provides all squad records and role-aware heuristic ratings. Schema 1.4–1.6 has 40 roster players; at most 22 are on the pitch, with fewer after dismissals. See [PLAYER-RATINGS.md](PLAYER-RATINGS.md) and [SUBSTITUTIONS.md](SUBSTITUTIONS.md) for participation, live ratings, lineup changes, and UI fields. The shared Python reducer includes these fields; the current frontend JavaScript reducer needs a deliberate port or backend connection before displaying live ratings.

The frontend can be developed entirely from the generated data. No video detection or recognition is required to start.

## Inputs

Use `data/examples/restarts-match/` as the current checked-in fixture (the older `short-match/` remains available for compatibility), or generate a new match using the root README. Load `metadata.json` and parse `events.jsonl` one line at a time. `summary.json` is useful for a final recap, but do not show its final score during live playback: calculate the current score from goal events instead.

`evaluation-only.json` describes simulator behaviour for debugging. Do not use it to manufacture detected tactical narratives or feed it to the AI. Analytical observations should come from actual match events and geometry.

## Clock and pitch

- Pitch coordinates are metres on a fixed 105 × 68 pitch; read dimensions from metadata.
- Convert to board pixels: `x / length_m * width_px`, `y / width_m * height_px`. Flip y if the board uses a bottom-left origin and the browser uses top-left.
- Home attacks positive x in period 1 and negative x in period 2; the physical coordinate system itself does not change at half-time.
- Use `sequence` to break timestamp ties. Deduplicate using `(match_id, event_id)`.
- Schema 1.5/1.6 playback time is `event.match_time_ms`; trajectory samples use `metadata.period_offsets_ms[String(period)] + sample.period_time_ms`. Seek duration is `metadata.match_duration_ms`. The old `(period - 1) * period_duration_ms + period_time_ms` applies only to legacy 1.3/1.4 files. Format the broadcast clock separately with `clockAt`: nominal 45/90 plus added time.
- Pause, seek, and replay speed must use one shared playback clock.

## Player and ball rendering

Each pass, shot, clearance, parry, restart delivery and advantage carry includes:

- `pitch_snapshot.period_time_ms`: kick timestamp within the half.
- `pitch_snapshot.players`: all player IDs mapped to `x_m` and `y_m` at kick time.
- `ball_trajectory`: samples with `period_time_ms`, `x_m`, and `y_m`.
- `start` and `end`: actual ball origin and destination.

Join player IDs to names, teams, shirts, and roles from `metadata.players`. Draw home and away markers in different colours. Ignore roles/skills for display unless useful to the user.

Player positions are snapshots, not full movement tracks. You may interpolate between snapshots for a smooth illustration, but that animation is not an additional measured data source. Ball animation can interpolate directly between trajectory samples.

Ball-action event timestamps represent **completion/arrival**. For a preloaded synthetic replay, expand each action into a kick-time snapshot, trajectory samples, and a completion-time outcome. Schedule all of those by their own timestamps. Do not reveal success, a goal, or completed-action metrics before completion.

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
| Whole-flight ball speed across passes/shots | `metrics.ball_average_speed_kmh.mean` |
| Restarts taken | `throw_ins`, `goal_kicks`, `corners` |
| Clearances and rebounds | `clearances`, `rebound_shots` |
| Save breakdown | `saves_held`, `saves_parried` (already included in `saves`) |
| Tackles | `tackles.attempted`, `.won`, `.foul`, `.missed` |
| Fouls / cards | `fouls_committed`, `fouls_won`, `yellow_cards`, `red_cards`, `second_yellow_dismissals` |
| Free kicks | `free_kicks`, `direct_free_kicks`, `indirect_free_kicks` |
| Penalties | `penalties_won`, `penalties_conceded`, `penalties_taken`, `penalties_scored`, `penalties_missed` |
| Defensive actions | `saves`, `interceptions`, `recoveries`, `turnovers`, `pressure_events` |
| Possession sequences | `possessions` |

Each metric distribution includes `count`, `min`, `mean`, and `max`. No observations means count zero and null values: display a dash, not zero speed or 0% accuracy. Means of speed metrics are event-weighted means of per-action speeds, not time-weighted motion averages. `pressure_events` counts recorded pressure observations, not distinct pressing episodes. Interceptions are credited to the defending team; saves to the opponent of the shooter. Count a goal event once, not once again for its scoring shot.

### Possession definition

This project uses `team_phase_time_v1`, a defined event-based convention rather than a claim of official broadcast methodology:

- A live restart/resume or recovery starts a team's possession phase. A non-kickoff `restart` with `ball_in_play:false` leaves it unassigned until `resume` at release.
- Pass flights, including unsuccessful attempts until the turnover timestamp, belong to that passing team's phase.
- Turnovers end that phase; any wait until the next recovery is unassigned.
- Shot, clearance and parry flights are unassigned from the kick timestamp; the preceding preparation interval belongs to the attacking team.
- Goal-to-kickoff gaps and time outside known possession phases remain unassigned.
- Period boundaries stop possession. Added time belongs to the actual elapsed match clock; the halftime break itself adds no playing time.
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

Schema 1.5/1.6 emits `ball_release` at the release of shots/clearances/parries, clearing possession immediately while their full action/trajectory arrives at completion. An `added_time` announcement during flight does not resolve it. Legacy streams without release records reclassify shot flight only at arrival; their intermediate estimates are provisional. True live ball animation still needs observations at source time or a delayed playback clock.

Existing matches can have these additive summary fields recalculated without changing their event files:

```powershell
py -3.13 -m simulator.statistics --input data/generated/evolving-match
```


## Discipline and lineup migration (1.6)

Use `dismissal` to remove markers and `goalkeeper_change` to assign the current keeper. A yellow card alone does not change headcount. `lineupsAt` now exposes `sentOff` and `goalkeepers`; `disciplineAt` exposes each player's shown cautions/dismissals/current role from the event prefix. Rewind rebuilds them, without reading final counts. The main screen includes yellow badges and the new team counters. Player records use `sent_off` with a frozen rating/stint; team minutes subtract the time lost to each dismissal. Never assume 11 active players or hardcode keeper IDs. See the Priority 2 guide for complete fields, direct/indirect/penalty rendering, bounded advantage, v2 rating changes and the UI-owner acceptance list.
