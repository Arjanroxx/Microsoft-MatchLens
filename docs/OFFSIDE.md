# Priority 3: connected offside and evidence replay

Implemented in generator schema **1.7**. All five Priority 3 checklist items are implemented within the selected 2D point-player model. Use [UI-INTEGRATION.md](UI-INTEGRATION.md) as the complete P1-P3 frontend handoff, including a runnable statistics/rating bridge and a copyable Sol task.

## Rule grounding and exact scope

The rule reference is [IFAB Law 11](https://theifab.com/laws/latest/offside/). The ball-contact position and active involvement are separate. A point-player must be in the opponents' half and nearer the attacked goal than both the ball and second-last active opponent. Level and the halfway line are legal. The assessment uses the first teammate kick/touch, all active opponents, and the appropriate attack direction. It never assumes the goalkeeper is the last opponent. The 0.001m comparison tolerance is for numerical rounding, not an official VAR tolerance.

The original snapshot remains the evidence even if players move, a goalkeeper deliberately saves, or a defender reflexively deflects the ball. An opponent's deliberate controllable play resets the phase; its mere touch does not. Direct receipt from a throw-in, goal kick or corner is exempt. A later teammate kick creates a new assessment without inheriting that exemption. Other restarts are assessed normally.

The selected active-involvement model covers actual receipt/touch, gain from a parried save or deflection, and an explicit planar keeper-obstruction proxy. For obstruction the candidate must be between the ball and keeper, within 0.35m of their sight segment, and within 3m of the keeper. This is a declared geometric simplification, not evidence of a real player's visual field. A candidate elsewhere is passive and does not trigger a whistle. Independent challenges/gestures, attempted-but-missed touches affecting an opponent, body parts, aerial play, off-field defender rules and goalkeeper throws are not simulated. Existing fouls are adjudicated while the player controls the ball; a passive offside position does not itself override a foul. Offside involvement is resolved before an invalid receiving player can start a subsequent challenge or shot.

Opponent control is also a declared proxy: a reachable contact is deliberate when incoming speed is at most 18m/s, flight is at least 0.5s and there is at least 0.2s spare running reach. Otherwise it is a reflex deflection. These are uncalibrated simulator parameters, not IFAB numerical thresholds. A poor later pass/clearance does not retrospectively turn a deliberate play into a deflection. Deliberate saves are handled separately and never reset the original offside assessment for a rebound.

This extends the existing connected simulation; it does not append random offside labels or implement VAR reviews. Passing choices strongly prefer onside receivers without guaranteeing that every pass choice is legal. No match is forced to contain an offside or a goal.

## Implementation flow

1. Freeze the active players, ball and first contact timestamp when a teammate kicks.
2. Resolve the actual flight/contact geometry. Position alone awards no offence.
3. Before receipt grants control, adjudicate the selected active participant against that frozen frame.
4. For a controlled opponent play, reset; for reflex deflection or save, retain the original teammate source through the connected rebound flight.
5. Emit an `offside` decision with the original source and involvement. Stop play and award the opponent an indirect free kick at the involvement location, including when the attacker has returned to their own half.
6. Resolve the actual normal restart preparation, card administration if pending, eligible queued substitutions, added-time ledger and delivery using the existing state machine.

The goalkeeper holding a saved ball obtains genuine control; no invalid rebound recovery is generated. A parried save remains loose and is checked before any attacker recovery. Direct restart exemptions are attached to the original restart delivery, not a permanent possession flag.

## New and extended event contract

Every event retains schema_version, match_id, event_id, sequence, period, period_time_ms, match_time_ms, team_id, player_id and source. Times are observation/decision times unless explicitly described as contact times.

`offside` fields:

| Field | Meaning |
|---|---|
| team_id / player_id | Offending team / active participating player |
| source_event_id | Original teammate pass, restart delivery or shot; use this, not latest rebound snapshot |
| involvement | touch, interfere_opponent, gain_advantage_save, gain_advantage_deflection |
| location | Actual selected involvement location; IFK location, which can differ from contact-time attacker position |
| via_event_id | Parry/deflection record for rebound decisions, otherwise null |
| contact_period_time_ms | First teammate contact timestamp in source half |
| contact.model | law11-point-player-v1 |
| contact.ball | Ball at original teammate contact |
| contact.direction | +1 or -1 toward attacked goal |
| contact.second_last_opponent_id / _x_m | Second-last active opponent's identity and source x position |
| contact.line_x_m | Effective legal limit, taking the more advanced of ball/opponent toward goal |
| contact.candidates | Source-position candidates keyed by player ID, with x_m and positive margin_m; position alone is not a whistle |
| contact.restart_type / direct_receipt_exempt | Original direct-restart assessment |
| contact.numerical_tolerance_m | Explicit numerical comparison tolerance |
| positions_after | Actual active positions at decision time, distinct from source snapshot |
| restart | type indirect_free_kick, awarded opponent team_id, location, reason offside |

Get the full frozen source positions from `eventsById[source_event_id].pitch_snapshot.players`. The source pitch_snapshot timestamp is earlier than the completed action/decision event timestamp. The period-offset conversion gives absolute contact time.

`opponent_touch` fields: source_event_id, start (ball contact), player/team, positions_after and `control`: model, arrival_ms, reach_ms, speed_mps, classification (deliberate_play/deflection), resets_offside. The source action's interceptor_id is used only for a controlled interception; deflector_id denotes uncontrolled contact. Outcome reason intercepted describes the geometric contact, while the separate control object describes how that touch is interpreted.

`deflection` is a normal ball action with start, end, source_event_id, touch_event_id, pitch_snapshot, ball_trajectory, commanded_mean_speed_mps and calculated ball_speed. It is a short geometric continuation with no controlled possession. Boundary crossings use the actual deflector as last touch and the ordinary corner/goal-kick/throw-in model.

For an offside completed reception, the pass/restart delivery is adjudicated incomplete, recipient_id null, outcome_reason offside; intended recipient/target and observed path are retained. An off-target in-field pass can also be penalised when a candidate is actually first to reach it; no recovery is granted.

For the obstruction proxy, a shot observation carries valid_for_statistics false, outcome no_goal, outcome_reason offside, offside_offender_id, save_outcome null and observed_outcome_reason from the geometric shot resolver. Its samples and speeds remain raw evidence; it cannot award a valid shot, save, goal, assist, key pass or positive rating action. No goal/save follow-up is emitted. This is immediate adjudication at observation time, not a provisional goal then a later VAR cancellation.

A saved original shot remains valid when a later rebound involvement is offside: retain the original shot/save, emit the offside before recovery and do not create the invalid rebound shot. This distinction prevents deleting valid earlier actions while also preventing invalid new credits.

## Statistics and ratings

Both Python team/player reducers expose offsides (the offending player/team). No extra v2 rating penalty is invented. An offside pass is an incomplete attempt and affects the existing passing component. An offside recipient earns no passes_received, shot, goal, assist or key-pass credit. Invalid shot observations are skipped before action metrics, ratings and saved-shot credits. The actual decision is attributable evidence for the offender's descriptive count.

Possession clears on offside, opponent touch and uncontrolled deflection. The IFK preparation and loose/rebound flight are unassigned. Existing substitution selection still reads current prefix ratings and may use an offside stoppage as a natural opportunity. Clock and disciplinary administration remain connected.

## Frontend contract

Import `offsideAt` from frontend/model.mjs. It withholds evidence until the decision's match_time_ms, returns independent copies of the source positions/ball, and exposes effective lineX, secondLastOpponentX, offenderId, marginM, period and contactTimeMs. Default lifetime is 8 seconds; pass eventId and lifetimeMs Infinity for an explicitly selected historical decision.

Draw the frozen evidence separately from the live board. Highlight the offender, draw effective lineX, optionally show ball/second-last-opponent reference lines, and label it **Contact-time replay - 2D point-player model, not VAR**. Render source period/direction even if currently in the other half. Never draw a line against current positions or infer a whistle from contact.candidates alone.

The current Replay Studio evidence panel includes this frozen SVG diagram. Side-by-side stats include offsides. Player focus reads authoritative ratings/stints/offsides from /api/state when using simulator.ui_server. Existing recap templates exclude invalid shot observations.

## Verification and examples

```powershell
py -3.13 -m simulator.generate --seed 42 --output data/generated/priority-three-demo
py -3.13 -m simulator.ui_server --input data/generated/priority-three-demo --port 8080
py -3.13 -m unittest simulator.test_offside simulator.test_ui_server -v
node --test frontend/tests/offside.test.mjs
```

Use data/examples/offside-match for a checked-in full match; use the older P1/P2 fixtures to exercise additional natural outcomes. The tests cover both teams/directions, level/halfway/behind-ball cases, active opponents and non-keeper lines, direct receipt exceptions, passive position, geometric obstruction, saved/deflected rebound preservation, deliberate control reset, receiving/stat/rating exclusions, source-time evidence, own-half involvement location, corruption rejection, API rewind, and JS/Python agreement.

Full-suite multi-seed tests also retain lifecycle, ball continuity, added time, bookings, subs and legacy fixtures. The simulator remains uncalibrated: this implementation establishes consistency and explainability, not professional event distributions or body-part-accurate officiating.
