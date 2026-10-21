# Priority 1: ball-out, restarts, saves and added time

Schema **1.5** implements all five Priority 1 checklist items. This is the detailed frontend/backend handoff; [UI-INTEGRATION.md](UI-INTEGRATION.md) remains the main UI report. No new dependencies are required. Fouls, cards and offside remain future work.

## Try the complete demonstration

```powershell
py -3.13 -m simulator.generate --seed 51 --minutes-per-half 5 --output data/generated/priority-one-demo
py -3.13 -m simulator.replay --input data/generated/priority-one-demo --speed 60
py -3.13 -m http.server 8080
```

Open `http://localhost:8080/frontend/`, choose **Load a match**, and select the generated `metadata.json` and `events.jsonl` together. A checked-in copy is also available at `data/examples/restarts-match/`. Seed 51 with five-minute halves exercises throw-ins, goal kicks, corners, held and parried saves, a rebound shot, a goal, clearances, substitutions and added time. Short-demo substitution timings and stoppage policies scale; travel still uses actual pitch metres and the movement cap, so short demos are not exact accelerated copies of full matches.

For an ordinary full match:

```powershell
py -3.13 -m simulator.generate --seed 42 --output data/generated/priority-one-full-001
```

Use a new output directory to preserve earlier matches. Older matches cannot acquire ball-outs or added time by recalculating their summaries: regenerate events. Existing schema 1.3/1.4 fixtures remain supported and unchanged.

## The connected model

The engine maintains one ball position, a current controller or loose/dead state, active lineups and one ordered clock. Actions choose a kick, resolve geometry, then calculate metrics from the resulting trajectory. New event types do not generate unrelated speed values, goals, saves or restart awards.

### Whole-ball boundary and last touch

Ball coordinates use `raw_point`, which permits going outside the field. Player coordinates remain bounded. The ball has a configured planar radius of **0.11 m**. A centre beyond a line is insufficient until the whole ball crosses; first crossings occur at centre x = −0.11/105.11 or y = −0.11/68.11 m. Numerical contact at that threshold is treated as crossing. A diagonal segment uses its first boundary; simultaneous corner crossings use the touchline as a deterministic tie convention.

The trajectory terminates at that first crossing. A pass first intercepted inside the field remains live: it is not labelled out merely because the original aim was outside. `ball_out` records the crossing, source action, last-touch team/player and the awarded restart.

| Crossing | Last touch | Award |
|---|---|---|
| Touchline | Either team | Throw-in to the other team, at the exit's x coordinate on that touchline |
| Goal line, no goal | Attacking team | Goal kick to defenders, at the chosen goal-area location |
| Goal line, no goal | Defending team, including keeper parry | Corner to attackers, from the nearest corner on that end |

Defending ends change by half; fixed pitch coordinates do not flip. Restart goal-kick location is `(5.5,34)` or `(99.5,34)`. Corners use the corner point as a simplified location within the corner-area model. Throw-ins use the touchline point; body/feet/hand technique is not simulated.

### Save, hold, parry, rebound and clearance

Shot aiming is unbounded. A shot is on target only when its whole planar ball fits the goal mouth at the goal line. Keeper contact is tested **before** the goal-line crossing, at the keeper's x plane. Reach depends on travel time, a reaction allowance, running reach and contact radius. Low-speed central contacts can be held; faster or stretching contacts are parried. The thresholds are original, uncalibrated simulation heuristics.

```text
shot (outcome_reason: saved, save_outcome: hold)
  → save (outcome: hold, linked shot_event_id)
  → recovery (reason: keeper_hold, keeper is controller)

shot (outcome_reason: saved, save_outcome: parry)
  → save (outcome: parry)
  → ball_release → parry (own continuous trajectory from contact)
  → ball_out → corner/throw-in, OR
  → loose_ball → recovery by nearest eligible outfielder
      → attacker: can take a linked rebound shot in shooting range
      → defender: next action clears the ball
```

A parry is not controlled keeper possession. Its direction/distance are calculated from the original shot's contact and speed; it does not become an unrelated opponent recovery. A rebound shot contains `is_rebound: true` and `rebound_of_shot_event_id`. The goalkeeper is excluded from the immediate rebound race to avoid automatically re-catching every parry; a future keeper recovery model may extend this. A clearance is a real kick away from danger with its own trajectory and first-exit decision. Off-target shots award the appropriate restart, never a save.

One `shot` record earns at most one shot/save credit. `save` and `parry` describe the follow-up and do **not** add a second save. A goal still comes from its linked scoring `shot` followed by one `goal` event. Previous-pass assist chains are broken by saves/loose-ball recoveries; a rebound goal does not inherit the original shot's creator as an invented assist.

### Natural substitution opportunities

The manager queues plans around nominal minutes 60–64 and 66–69, then executes them at the next generated **ball-out or goal-celebration stoppage**. It never stops open play solely for a substitution. A quiet period may delay a planned change beyond minute 70; it is not forced into the requested band by fabricating a stoppage. Half-time changes use the actual period interval, even when half one has added time.

The existing lowest-current-rating, outfield-only, same-position-group and five-player/three-opportunity rules remain. Each event includes `stoppage_event_id` and the original live selection evidence. Multiple replacements in a team batch share a `window_id`. Changes never occur during a flight or between a scoring shot and its goal. Replacement markers inherit formation slots; current lineups survive subsequent restart setups.

### Restart execution and placement

```text
flight ends out / goal occurs
  → ball_out (for boundary exits)
  → stoppage (reason: ball_out / goal_celebration)
  → optional substitutions and time_lost records
  → ball_placement (explicit from/to while the ball is dead)
  → restart (reason: throw_in / goal_kick / corner_kick / kickoff)
  → resume (non-kickoff restarts, at release)
  → restart_delivery (trajectory to receiver or interceptor)
  → completed reception or turnover/recovery
```

The ball remains at the crossing until an explicit dead-ball placement. Open-play actions always start at the preceding endpoint. The taker moves to the restart position with bounded movement; setup time is represented. Opponents are kept at least 2 m away at a throw-in, 9.15 m at a corner/kickoff, and outside the penalty area at a goal kick. Kickoffs arrange players in their own half, with the designated taker at centre. Restart delivery attempts resolve against actual defender geometry; they are not guaranteed completions.

`restart` has `positions_after`, `stoppage_event_id`, `source_event_id`, and `ball_in_play`. Non-kickoff restarts set `ball_in_play: false`; `resume` at delivery release makes play live. `restart_delivery` is a separate distribution, not an ordinary pass attempt, so throw-ins do not inflate pass accuracy. It carries `restart_type`, `restart_event_id`, `intended_recipient_id`, `intended_end`, `recipient_id`, `interceptor_id`, `outcome`, `outcome_reason`, trajectory and calculated ball speed.

If time expires while a restart is pending, the half can end with the ball dead and no restart taken. Do not invent a restart just to match a count of awards. Thus awarded `ball_out` restarts and taken restart counters may differ at a whistle.

## Clock contract: update this before consuming 1.5

`period_duration_ms` now means **regulation time per half**, not a maximum timestamp or offset of half two. Every event includes `match_time_ms` for a monotonic replay timeline excluding the real-world halftime break.

| Field | Meaning |
|---|---|
| `event.period_time_ms` | Elapsed milliseconds within that half, including added time; can exceed regulation |
| `event.match_time_ms` | Monotonic replay time; preferred ordering/scheduling timestamp |
| `metadata.period_offsets_ms["1"/"2"]` | Actual replay offset where that half starts |
| `metadata.period_actual_durations_ms["1"/"2"]` | Actual whistle time within each half |
| `metadata.match_duration_ms` | Total replay duration, including both added intervals |
| `pitch_snapshot.period_time_ms`, trajectory times | Still half-local; add the actual period offset |

**Remove** the old `(period - 1) * period_duration_ms + period_time_ms` calculation for 1.5. Half two starts after half one's actual whistle, not at nominal minute 45. First-half added time does not reverse attacking direction. Use sequence to resolve ties between first-half end and second-half start at the same replay time. Event labels should retain their own period when formatting a boundary event.

The displayed match clock resets its nominal base for half two. For a full match, show `45+02:10`, then `45:00` at half-two kickoff, then `90+03:20`. The seek bar uses monotonic replay time; it must not jump backwards with the displayed clock. For five-minute halves the labels are `5+…`, second-half base `5:00`, and `10+…`.

Frontend helpers already provided:

```javascript
import {prepare,boardAt,clockAt,statistics,lineupsAt,periodOffset} from './model.mjs';
const match = prepare(metadata, events);
const replayEnd = match.duration; // actual duration, not 2 * regulation
const board = boardAt(match, playbackMs);
const clock = clockAt(match, playbackMs);
// clock.period, clock.periodTimeMs, clock.display, clock.inAddedTime,
// clock.announcedMinimumMs (null before announcement), clock.fullTime
const liveTeams = statistics(match, playbackMs);
// Action sample replay time:
const sampleTime = periodOffset(metadata, action.period) + sample.period_time_ms;
```

`clockAt(match,event.t,event.period)` formats an individual event at a timestamp shared across the interval. `boardAt` returns the clock, active lineup, positions, ball, carrier and phase. Only 22 active markers are drawn. It animates all five action types: pass, shot, clearance, parry and restart delivery. Phase/carrier stays neutral through administrative records in a stoppage. `positions_after` anchors include period starts, recoveries, restarts and substitutions. Substitution/kickoff membership resets are not interpolated early. Ball-out endpoints can sit 0.11 m beyond the pitch edge: do not clamp data back inside; allow a small SVG gutter if you want the entire ball marker visible.

## Added-time ledger and whistle

`time_lost` records contain `reason`, `start_ms`, `end_ms`, `duration_ms` (half-local), and `source_event_id`. The ledger accounts for in-play substitutions, goal celebrations, excess restart preparation, and extra restart positioning. Ordinary restart preparation up to a transparent allowance is **not all added back**. Each team substitution batch adds a nominal 20 s in full matches; celebration/setup intervals follow emitted state transitions. Short-demo policy delays scale.

At regulation end, `added_time` announces `minimum_added_ms`, `lost_time_ms`, `rounding_quantum_ms` and supporting `evidence_event_ids`. The minimum is the ledger total rounded up to a minute, or a proportionally scaled quantum for short demos (at least 1 s). Additional qualifying losses posted after announcement extend the actual whistle; the announced minimum never shrinks. A flight already started can finish, so the whistle may slightly exceed the target. If a loss spans regulation, its completed log is posted afterward and recovered as a further allowance.

`period_end` includes `regulation_duration_ms`, `minimum_added_ms`, `actual_added_ms`, `lost_time_ms` and `lost_time_ledger`. The model is an auditable timing policy, not a claim that real referees mechanically reimburse this exact formula. A foul/penalty extension and misconduct/countdown penalties are not implemented.

An `added_time` announcement can occur during a flight. It does not interrupt the trajectory, transfer control or resolve the action. `ball_release` for shots/clearances/parries marks the kick and clears possession immediately, so a streaming reducer does not attribute the flight to the previous controller while awaiting completion.

## Statistics and player ratings

New keys below **both** `summary.teams.<team>` and `summary.players.<id>`:

| Python summary key | JS team adapter key | Count definition |
|---|---|---|
| `throw_ins` | `throwIns` | Throw-in restarts taken |
| `goal_kicks` | `goalKicks` | Goal-kick restarts taken |
| `corners` | `corners` | Corner restarts taken |
| `clearances` | `clearances` | Resolved clearance kicks |
| `saves_held` | `savesHeld` | Saved shots held by keeper |
| `saves_parried` | `savesParried` | Saved shots parried by keeper |
| `rebound_shots` | `reboundShots` | Linked subsequent shots from a parried rebound |

`saves` remains the total; for newly generated 1.5 matches it equals `saves_held + saves_parried`. The ordinary pass/shot metric distributions still cover passes/shots only; clearance/parry/restart speeds are available on their event records and are not silently mixed into passing metrics. Interceptions of restart deliveries also credit the named defender/team, without counting a restart delivery as an ordinary pass. New counters are descriptive; rating weights remain the documented v1 model, without invented clearance/restart bonuses. Save credit continues to come from the saved shot once.

The main UI already displays the new side-by-side counters and meaningful event labels. Dedicated restart cards/arrows, an added-minimum badge and a detailed lost-time panel can use the fields above. Bench/player-rating panels remain the UI owner's work; JS has no duplicate player-rating implementation. Obtain those from the shared Python reducer/backend.

Player stint timestamps and exact `minutes_played_ms` now use **monotonic match time including added time**. An outgoing player remains frozen; on-pitch players continue accruing minutes/rating evidence past nominal minute 90 until the actual final whistle. Do not finalise ratings or cap minutes merely at `2 * period_duration_ms`. Without dismissals, each team's player minutes sum to 11 × actual elapsed replay time.

Possession remains the explicitly defined phase-time convention: ordinary pass/restart-delivery flight belongs to the initiating phase; shot/clearance/parry flights, loose-ball recoveries, ball-out gaps and dead setup are unassigned. `restart` with `ball_in_play:false` does not start possession; release/resume does. Added time is elapsed clock time and participates in the same accounting. `home + away + unassigned = actual elapsed time`.

For Python, continue calling `calculate_statistics(metadata,events,as_of=(period,period_time_ms))`. Live `MatchStatistics.update` uses each event's monotonic timestamp, and `period_start` supplies the new period mapping even when final durations are not yet available. Replay seek must rebuild a prefix, not reuse a reducer that already consumed future events. `summary.json`, final duration and actual added intervals are final-file information, not live knowledge to reveal early.

## Frontend integration acceptance list

- [ ] Import metadata and events together; branch clock compatibility by schema.
- [ ] Use actual duration for seeking and actual offsets for ball samples; format the broadcast clock separately.
- [ ] Keep first-half direction through its added interval; use `sequence` across interval ties.
- [ ] Render all five trajectory action kinds and their exact endpoints; no future outcome labels before arrival.
- [ ] Clear carrier at `ball_release`/stoppage; distinguish hold control from parry/loose ball.
- [ ] Show restart team/type/location and last touch from `ball_out`, not a guessed opposite team.
- [ ] Treat placement as dead-ball relocation; never draw it as a live kick/speed measurement.
- [ ] Update active lineups from substitutions at their event sequence; preserve departing history on rewind.
- [ ] Show team-specific counters; avoid duplicate goals/saves and ordinary-pass credit for throw-ins.
- [ ] Keep live ratings provisional through added time; finalise only at exit/actual final whistle.
- [ ] Show announced minimum only after `added_time`; explain further allowance from the ledger if desired.
- [ ] Hide `time_lost`, release and placement admin noise from the main event feed while retaining raw evidence.
- [ ] Rebuild score, possession, lineups and any open restart card when seeking backwards.

These unchecked boxes are the frontend owner's handoff checklist, not unimplemented generator features. The bundled adapter/main screen already covers timing, trajectories, counters and lineups; custom panels depend on the teammate's design.

## Validation and rule references

Automated checks cover whole-ball boundaries, first crossings, direction/last-touch awards, geometry-supported save/delivery outcomes, exact speed recalculation, no open-play ball relocation, no out-of-play possession, natural substitution linkage, player-minute reconciliation, added-time ledger/offsets, legacy compatibility, and corruption rejection. JS tests compare final counters/possession with the Python fixture and check animation, clock, event visibility and rewinds.

Verified for this update: **57 simulator + 16 backend + 21 frontend tests passed**. The simulator suite includes all five profiles across 12 full-match seeds. An additional 362 replay checkpoints compared Python/JavaScript possession and main counters. The actual app entrypoint passed a DOM smoke check using the 1.5 fixture (startup, first-half added time, final score/counters and rewind), and terminal replay plus both backend narrative modes consumed the new fixture successfully. These are automated/state checks; no browser visual-layout inspection is claimed.

```powershell
py -3.13 -m unittest discover -s simulator -p "test_*.py" -v
py -3.13 -m unittest discover -s backend/tests -p "test_*.py" -v
node --test frontend/tests/replay.test.mjs frontend/tests/substitutions.test.mjs frontend/tests/restarts.test.mjs frontend/tests/startup.test.mjs
```

Rule grounding checked against IFAB's 2026/27 pages: [ball in/out](https://www.theifab.com/laws/latest/the-ball-in-and-out-of-play/), [throw-in](https://theifab.com/laws/latest/the-throw-in/), [goal kick](https://theifab.com/laws/latest/the-goal-kick/), [corner](https://theifab.com/laws/latest/the-corner-kick/) and [duration/allowance](https://www.theifab.com/laws/latest/the-duration-of-the-match/). Those support the restart/clock distinctions; the numerical motion, hold/parry thresholds and lost-time policy are our simulation choices.

Still outside this model: aerial/hand technique and illegal-restart retakes, ball spin/height/woodwork, own goals, fouls/cards/penalties, offside, referee countdown sanctions, calibrated full goalkeeper behaviour and continuous player tracking. These limitations do not create disconnected synthetic labels; they define the scope of the implemented connected 2D engine.
