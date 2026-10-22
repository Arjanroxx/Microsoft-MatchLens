# More natural generated play: schema 1.8

This upgrade changes the simulation that produces the match, not just the animation. It preserves Priorities 1-3, event-derived metrics, ratings, substitutions and the original synthetic identities. The main frontend handoff remains [UI-INTEGRATION.md](UI-INTEGRATION.md).

## What changed and why

Previously the carrier waited stationary for 3-7 seconds while teammates headed toward fixed formation points. Players generally froze during a pass and then the receiver/interceptor appeared at the contact point. Passing selection mainly rewarded forward distance and receiver openness, even when a defender could intercept the lane. That combination caused rigid motion, strange exchanges and disconnected-looking arrivals.

New matches use:

- **Role-based support and cover:** defenders support behind the ball, midfielders provide different passing angles, wide players retain width, and forwards offer runs while trying to stay onside. One nearby defender presses; another covers instead of both chasing the same point. Teammate separation discourages clustering.
- **Steering with inertia:** free-running players accelerate/decelerate toward targets rather than immediately changing direction or travelling at maximum speed. The integrator advances in steps no longer than 200ms, with 2.5m/s² steering acceleration and a 4.5m/s free-running cap. Targets update at 500ms boundaries. These are selected synthetic parameters, not measured player attributes.
- **Controlled carrying:** ordinary decision intervals move the carrier and ball together, with a 2.4m/s carrier target-speed cap; under immediate pressure the carrier shields rather than being instructed to run straight through an opponent. Decisions occur sooner under pressure/quick play and more slowly in patient phases. These intervals still vary through seeded choices.
- **Receiving runs:** a pass can aim ahead of the receiver using their generated velocity. The resolver checks whether the actual receiver can reach the destination in the available flight time. It does not grant completion just because the ball reached an intended point.
- **Lane-aware choices:** each candidate has a distance, progression, space, lane-interception and previous-passer score. Closed lanes receive a strong penalty, short/medium connections are preferred, immediate return passes are less attractive, and an occasional risky option can still be chosen. Scores are not probabilities and successful passes are never guaranteed.
- **Defender reaction:** the new pass resolver allows 250ms before a defender can run toward an interception. Its movement/contact evidence remains connected to the pass geometry, rather than an independent success roll.
- **Flight movement:** support and defensive players keep moving while the ball travels. The selected receiver/interceptor follows a planned contact run. Saved-shot contact retains the existing planar keeper-reach approximation.
- **Recovery and setup runs:** loose-ball recoveries, restart takers, legal set-piece spacing and post-goal returns have explicit sampled repositioning paths. A post-goal return uses the preparation/celebration time already on the clock. A compressed short demo extends preparation if necessary to avoid a run exceeding the movement bound.
- **Shot decisions:** range and shooting angle constrain the available shot option; the choice varies with goal distance. Shot success still comes from the existing trajectory/goal-mouth/keeper model, not a prescribed scoreline.

Implementation: simulator/movement.py holds support targets, steering and passing options; simulator/pitch.py holds shared geometry/reach; simulator/simulation.py connects those decisions to events, possession, restarts and clock state. All metrics continue to be calculated from the resulting action evidence.

## New event/UI contract

All events retain normal identity, source, sequence, period and monotonic match_time_ms fields. Version 1.8 is explicit because changed decisions alter results for the same seed; older matches retain their original semantics.

### Controlled movement

A `movement` record has team_id, possession_id, carrier_id, start/end, pitch_snapshot, ball_trajectory, player_motion, positions_after and motion_model. It is emitted at completion of a decision interval. Every published carrier position follows the same generated ball path, apart from the existing small ball-edge/contact rounding allowance at a release boundary.

`player_motion` is an array:

```json
[
  {"period_time_ms": 1000, "players": {"home-07": {"x_m": 50, "y_m": 34}}},
  {"period_time_ms": 1500, "players": {"home-07": {"x_m": 50.3, "y_m": 33.9}}}
]
```

The example omits other active players for readability; real frames contain the entire active lineup. Controlled movement frames additionally include ball, with matching timestamped ball_trajectory samples. Normal pass/shot/clearance/parry/deflection/restart/advantage-carry actions also carry player_motion but the ball is described exclusively by their existing authoritative ball_trajectory. Always use ball_trajectory for drawing the ball.

`reposition` records describe selected straight recovery/setup runs. They have start=end (stationary ball), pitch_snapshot, player_motion, positions_after, ball_trajectory and a reason: loose_ball_recovery, restart_taker, restart_setup or return_for_kickoff. They grant no controlled possession. The following recovery/restart/resume event determines when control/play begins.

Expand samples with `periodOffset(metadata,period) + sample.period_time_ms`. Use the updated frontend/model.mjs: prepare builds visual frames from player_motion; boardAt interpolates between generated samples and supports controlled, flight and repositioning phases. Do not replace these with fixed formation anchors or hold players frozen throughout a pass. Every sample must use the active lineup for that time; dismissals/substitutions cannot be undone by interpolation.

Hide movement/reposition records from the primary football-event feed. They do not create passes, receptions, shots, saves, turnovers or rating evidence. Existing team/player action counts and ratings remain canonical in simulator/statistics.py and /api/state. Possession continues during controlled movement, but not during a loose-ball recovery or dead-ball setup. The main scoreboard and counters must still use only completed events.

### Lead-pass evidence

For an ordinary pass, receiver_start is the receiver's original position and receiver_velocity_mps is [vx,vy]. Lead time is min(0.6, original distance / 16 * 0.45), and intended_end is the pitch-bounded original position plus velocity times lead time. Kick error is applied to that target before reach/interception testing. Intended target and receiver starting position therefore need not match.

The pass also includes decision_model lane-aware-lead-pass-v1, defender_reaction_ms 250 and passing_options with player_id, target, score and predicted_interceptor_id. Those predictions inform weighted choices; outcome/interceptor_id/deflector_id and actual paths remain the observed resolution. The planner estimates its nominal speed; actual kick effort can change the final command and outcome.

Offside still uses the teammate-contact pitch_snapshot, not the lead destination or arrival frame. Offside original contact evidence must remain frozen across later movement, saves and deflections. A moving receiver gets neither a halo nor passing/shot credit before legal arrival. Rating model remains v2; movement volume does not manufacture a better rating.

## Run the new demo

```powershell
py -3.13 -m simulator.ui_server --input data/examples/movement-match --port 8080
```

Open http://127.0.0.1:8080/. This checked-in full match uses seed 0 and includes goals, movement, receiving runs, recovery/setup paths and the existing rule events. The server's player-rating API works unchanged. Keep Smooth enabled to interpolate between the generated samples; disabling Smooth intentionally shows held 500ms anchors.

To make another match:

```powershell
py -3.13 -m simulator.generate --seed 123 --output data/generated/natural-match-123
py -3.13 -m simulator.ui_server --input data/generated/natural-match-123 --port 8081
```

Existing files do not gain motion by recalculating summary.json. Regenerate into a new directory, then restart the server with that directory. A new model/version changes the result of the same seed. All older fixtures remain unchanged. The normal static frontend sample remains a legacy example; importing the new files or using the bridge is necessary to see this upgrade.

## Development evaluation

The following full 45-minute-half runs were checked after choosing the motion/decision parameters. Seeds 101-104 were additional inspection cases; seed 42 is retained for comparison with the older reference. These are generated outcomes, not target values, professional benchmarks or a statistically representative calibration study.

| Seed | Score | Pass attempts | Completion | Valid shots | Mean intended pass m | Offsides |
|---:|---|---:|---:|---:|---:|---:|
| 42 | 0-0 | 1283 | 73.19% | 16 | 20.4 | 12 |
| 101 | 2-1 | 1417 | 71.7% | 20 | 20.27 | 5 |
| 102 | 0-0 | 1254 | 77.83% | 15 | 20.31 | 15 |
| 103 | 0-1 | 1457 | 74.74% | 26 | 19.78 | 11 |
| 104 | 0-2 | 1428 | 77.45% | 25 | 20.07 | 7 |

The checked-in older schema 1.7 seed-42 reference had 616 passes, about 66% completion and 18 shots. The new seed-42 result has more connections and improved completion, but a different scoreline; do not treat individual changed totals as proof of professional realism. Pass volume and offside frequency still require external calibration. There is no forced minimum number of goals, shots, cards or offsides. A generated 0-0 is allowed.

Tests cover acceleration/reach bounds, continued support movement, carrying, lead targets, dangerous-lane penalties, reaction delay, event-derived counts, no movement rating inflation, malformed samples, post-goal setup, pre-arrival possession, recorded-frame rendering, Python/JavaScript agreement and legacy compatibility. Existing multi-profile/multi-seed validation also checks ball continuity, clocks, active actors, restarts, fouls/cards, subs and offside.

## Practical limits and next refinements

This is an improved synthetic 2D simulation, not a complete football game or measured tracking feed. Planned receiver/interceptor and restart runs are simplified straight paths and do not use the same steering-acceleration model as free support movement. The keeper still has a selected contact-reach allowance. Player avoidance discourages clustering but is not a full collision/duel model. Pass interception and shot outcomes retain selected geometric prediction rather than full 3D physics.

Player motion is sampled at 2Hz; interpolation is necessary for smooth display and does not create camera observations. Full matches are larger (roughly 30MB for the checked-in replay); current preloaded replay is appropriate for development, while a hosted live product needs observation streaming and efficient indexing. Match-level statistics still need calibration against a reviewed football dataset before claiming Premier League realism. Fatigue, injuries, aerial balls, headers, full dribble duels and richer goalkeeper decisions remain future work rather than disconnected labels added to this update.

Teammate task: read this document and the complete UI-INTEGRATION.md, reuse the updated model.mjs, load movement-match, preserve generated player_motion and lead targets, hide movement/reposition from the event feed, retain all P1-P3 decisions and ratings, and run frontend/tests/movement.test.mjs alongside the existing tests.
