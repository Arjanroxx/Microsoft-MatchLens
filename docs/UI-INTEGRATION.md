# MatchLens UI integration: complete Priorities 1, 2 and 3

Current generator/event schema: **1.7**. Ratings remain **matchlens-event-rating-v2**. This is the main handoff for the frontend teammate and their coding assistant. Everything below has a concrete implementation in this repository; extra competition features and production streaming remain separate work.

## 1. Run the complete development experience

Install Python 3.10+ (the project uses 3.13). There are no pip dependencies. Install Node 18+ only to run frontend tests. From the repository root in PowerShell:

```powershell
# Existing checked-in full match, including Priority 3:
py -3.13 -m simulator.ui_server --input data/examples/offside-match --port 8080
```

Open **http://127.0.0.1:8080/**. This serves Replay Studio and the authoritative statistics API from the same origin. Ctrl+C stops it. To create another match, use a second terminal:

```powershell
py -3.13 -m simulator.generate --seed 123 --output data/generated/match-123
py -3.13 -m simulator.ui_server --input data/generated/match-123 --port 8081
```

Output directories are overwritten when reused; use a different directory for each match you want to retain. Omit `--minutes-per-half` for normal 45-minute halves; `--minutes-per-half 5` makes a short demo with proportionally scaled substitution windows and lost-time allowances.

The original static mode still works: `py -3.13 -m http.server 8080` at repository root, then open `/frontend/` and import metadata.json plus events.jsonl. Static mode has team statistics, lineups, cards and offside evidence, but no authoritative live player-rating API. The static bundled sample is deliberately still a legacy fixture. The bridge uses the match passed to `--input` instead.

## 2. Inputs and the source of truth

| Input | Use |
|---|---|
| metadata.json | Match identity, all 40 squad players, team names, dimensions, attack directions, rule/model versions and clock mapping |
| events.jsonl | Ordered observations and decisions; one JSON object per line |
| summary.json | Final team/player statistics and ratings; final recap only |
| evaluation-only.json | Generator debugging; exclude from UI intelligence and AI evidence |

IDs are synthetic. Join `player_id` to `metadata.players`; never infer identity or active goalkeeper from a shirt number. Start with `is_starter`, then apply substitution/dismissal/goalkeeper_change events. Bench members are not on-pitch markers. A red card reduces team size and does not permit an ordinary replacement.

Never use `metadata.final_score`, final summary ratings, or evaluation policies as live facts. Metadata/events are complete preloaded replay inputs, so they contain future information. Outcomes enter the visible UI only at their event time. Stats and ratings come from an event prefix.

## 3. Reuse the implemented adapter

`frontend/model.mjs` exports these pure functions:

```javascript
import {
  prepare, boardAt, statistics, lineupsAt, disciplineAt,
  offsideAt, clockAt, eventTitle, actionTypes, periodOffset
} from './model.mjs';

const match = prepare(metadata, rawEvents);
const timeMs = 120000; // one shared playback clock
const board = boardAt(match, timeMs, {smooth: true});
const counters = statistics(match, timeMs);
const lineups = lineupsAt(match, timeMs);
const cards = disciplineAt(match, timeMs);
const offside = offsideAt(match, timeMs);
```

`board` supplies player positions, sampled ball position, active action, carrierId, phase, clock, lineups and discipline. `statistics` supplies team counters and possession; it is not a complete player-rating reducer. `eventTitle` understands every current event. `offsideAt` returns frozen evidence, described below. Keep these functions independent of React/Vue/the visual board and reuse their tests.

## 4. Timing, replay, and rendering

- Fixed pitch coordinates are metres on a 105 x 68 plane; use metadata dimensions. Home attacks +x in period 1 and -x in period 2. The coordinate system itself never rotates at halftime.
- Draw at `x / length * width`, `y / width_m * height`. The current SVG flips y (`68 - y_m`). Use the same transform for players, ball, arrows and offside lines.
- Playback time is `event.match_time_ms`. Within-period trajectory timestamps convert with `periodOffset(metadata, event.period) + sample.period_time_ms`. Actual second-half offset includes first-half added time; do not assume it is 2,700,000 ms.
- Seek duration is `metadata.match_duration_ms`. Format the broadcast clock with `clockAt`, including the announced minimum and added time. Halftime is a period boundary, not an extra simulated 15-minute match-clock gap.
- Sort by time then sequence. Deduplicate `(match_id, event_id)`. Same-timestamp card/dismissal/role/restart ordering matters.
- Ball-action records are emitted at **completion**. Their `pitch_snapshot.period_time_ms` is the earlier contact timestamp; `ball_trajectory` samples animate the intervening flight. In a preloaded replay, schedule samples at sample time but withhold outcome, counters, receiver control and decision evidence until completion/decision time.
- `ball_release` clears control before shot/clearance/parry flight. Passes and restart deliveries do not grant the receiver control before receipt. A deflection is an uncontrolled touch, not a defender possession.
- `positions_after` gives an exact active-state anchor at recovery, restart, substitution, dismissal, opponent touch and offside decision. Do not resurrect absent players when smoothing.
- Smooth movement between snapshots is illustrative. Disable smoothing for exact held anchors; neither mode measures player speed or running distance. Ball speed comes from recorded ball samples.
- Seeking backwards must rebuild every visible panel from the same prefix, clear selections from the future, and discard stale asynchronous state responses.

True live transport is not implemented. Terminal `simulator.replay` sends the completed record after arrival; it cannot animate a past kick on time. Use a delayed shared playback clock or design separate release/sample/completion messages for a future real-time feed.

## 5. Feature-to-UI implementation matrix

| Priority / feature | Events and authoritative state | Required UI behaviour |
|---|---|---|
| P1 touchline / throw-in | ball_out.crossing, boundary, last_touch_player_id/team_id, restart; ball_placement, restart, resume, restart_delivery | Show actual first whole-ball exit, award team and touchline location; ball stays dead until release |
| P1 corners / goal kicks | Same boundary evidence; restart.reason corner_kick or goal_kick | Distinguish attacker miss from last defender/keeper touch; display correct end and awarded team |
| P1 saved shots / rebounds | shot.save_outcome; save, parry, loose_ball, recovery; shot.is_rebound/rebound_of_shot_event_id; clearance | One save credit per valid shot; animate parry as its own continuous path, then loose-ball recovery or boundary award |
| P1 substitutions | substitution player_off_id/on_id, formation_slot, position_group, window_id, selection; positions_after | Swap only at event time, preserve the role slot, show outgoing rating evidence and freeze their minutes/rating; incoming player starts a new stint |
| P1 added time | time_lost, added_time.minimum_added_ms, period_end lost_time_ledger, metadata actual durations/offsets | Broadcast 45+/90+ clock; distinguish announced minimum from actual allowance and use actual durations for seeking/minutes |
| P2 tackles / fouls | tackle controls, challenge_snapshot, decision; foul victim_id, location, restart | Describe clean win, miss or selected offence from contact evidence; do not invent foul labels from random counters |
| P2 direct / indirect free kicks | stoppage, placement, restart.reason, delivery or direct-FK shot | Use awarded team/location; indirect restart delivers to another player and cannot immediately become a scoring shot |
| P2 advantage | advantage pending/played/recalled, foul_event_id, continuation_event_id; carry | Pending is not success; show the final played/recalled decision; delayed caution belongs to original offence |
| P2 penalties | foul.restart.type penalty; restart; shot.set_piece_type penalty; save/goal | Separate award from taken/scored/missed counters; show spot/setup/keeper; finish an awarded penalty even when preparation passes the half's time limit |
| P2 cautions | card colour, reason, caution_number, foul_event_id, stoppage_event_id | Yellow badge with player still active; preserve original evidence for delayed booking |
| P2 dismissal / keeper | dismissal reason direct_red/second_yellow; positions_after; goalkeeper_change; match_abandoned | Remove player, reduce team count, freeze stint/rating, use current emergency keeper ID; show abandoned if fewer than seven |
| P2 rating components | API players[id].rating + player_rating_model | Display published tackle/foul/caution/dismissal/penalty-miss components alongside existing scoring/passing/creation/defence components |
| P3 contact position | offside source_event_id + contact + original pitch_snapshot | Evaluate/render original teammate-contact positions with ball and second-last active opponent, in correct attack direction |
| P3 active involvement | offside.involvement: touch, interfere_opponent, gain_advantage_save/deflection | Position alone gets no whistle; show the recorded selected involvement and decision time |
| P3 exceptions / opponent touches | restart_delivery.restart_type; opponent_touch.control; deflection; original shot/parry references | Direct throw-ins, goal kicks, corners exempt; next teammate touch starts a new assessment; controlled deliberate play resets, reflex deflection/save preserves source |
| P3 invalid attack / restart | incomplete offside pass, invalid shot, offside.restart, stoppage reason offside, IFK | No illegal goal/assist/key pass/shot/save/rating credit; display the IFK where involvement occurred, which can differ from original offside position |
| P3 evidence replay | offsideAt(...) | Draw a separate frozen contact-time board and line with point-player limitation label; never put a past line against current players |

Deep contracts and modelling details: [P1 restarts and clock](RESTARTS-AND-CLOCK.md), [P2 discipline and set pieces](DISCIPLINE-AND-SET-PIECES.md), [P3 offside](OFFSIDE.md), [substitutions](SUBSTITUTIONS.md), [ratings](PLAYER-RATINGS.md).

## 6. Metrics and side-by-side statistics

For passes, `intended_end`/`intended_recipient_id` describe intent; `end` is actual ball contact, and `recipient_id` is null on failure or offside. `distance_m` is actual distance; difficulty uses the intended path, defender proximity and lane congestion. Show `pass_difficulty.score` as a heuristic /100, never a probability. `interceptor_id` means controlled interception credit; `deflector_id` is an uncontrolled contact and earns no interception credit. The pass's geometric reason can still be intercepted; use the separate opponent_touch.control.classification for its interpretation.

`ball_speed.average_kmh` is whole-flight mean speed. `shot_speed.kmh` is the first sample interval average, labelled initial shot speed. The mean of these observations is event-weighted. Do not label either as measured broadcast tracking or claim running speeds from player snapshots.

Goals count only from `goal`, never both shot and goal. Every shot with `valid_for_statistics === false` is an invalid attacking observation: preserve its trajectory for evidence, exclude it from shot totals, on-target totals, shot-speed aggregate, saves, penalties-taken/missed, key passes, assists and rating credits. `observed_outcome_reason` preserves geometric observation, while adjudicated `outcome_reason` is offside. No goal event follows it. A valid original saved shot still counts when an offside rebound recipient is subsequently penalised; the invalid subsequent recovery/shot is never emitted.

Python API field names are canonical. JS `statistics(...).teams[team]` uses these display names:

| Python | JavaScript |
|---|---|
| goals; passes.attempted/completed/accuracy_percentage | goals; attempted/completed/accuracy |
| shots.total/on_target | shots/onTarget |
| possession.percentage/time_ms | possession/time |
| recoveries, turnovers, interceptions, saves, clearances, offsides | same names |
| pressure_events | pressure |
| throw_ins, goal_kicks, corners | throwIns, goalKicks, corners |
| saves_held/saves_parried/rebound_shots | savesHeld/savesParried/reboundShots |
| tackles.attempted/won/foul/missed | tackles/tacklesWon/tacklesFoul/tacklesMissed |
| fouls_committed/fouls_won | fouls/foulsWon |
| yellow_cards/red_cards/second_yellow_dismissals | yellowCards/redCards/secondYellowDismissals |
| free_kicks/direct_free_kicks/indirect_free_kicks | freeKicks/directFreeKicks/indirectFreeKicks |
| penalties_won/conceded/taken/scored/missed | penaltiesWon/penaltiesConceded/penaltiesTaken/penaltiesScored/penaltiesMissed |

Show unavailable values as a dash, not zero accuracy or zero possession. Possession is `team_phase_time_v1`: assigned home/away phase time over combined assigned time. Dead-ball gaps, shot/clearance/parry/deflection flights and loose gaps are unassigned. Pass/restart-delivery flights belong to the initiating phase until the turnover. This is an explicit event-state estimate, not touches or broadcaster possession. The API includes the denominator and unassigned time.

## 7. Live player ratings and lineup API: no rating port required

The new local bridge is implemented in `simulator/ui_server.py`:

| GET path | Response |
|---|---|
| /api/metadata or /data/metadata.json | Preloaded match metadata |
| /api/events or /data/events.jsonl | Preloaded NDJSON events |
| /api/state?time_ms=120000 | Canonical Python state computed only through that playback time |

State response has `match_id`, `schema_version`, `as_of_match_time_ms`, `through_sequence`, `period`, `period_time_ms`, `teams`, `players`, `lineups`, `substitutions`, `player_rating_model` and `possession`. Player keys include counters, `minutes_played_ms`, `minutes_played`, `entered_at_ms`, `left_at_ms`, `squad_status`, `current_role`, `rating` and evidence. Lineups are grouped by team with `on_pitch`, `bench`, `substituted_off`, `sent_off` and `goalkeeper_id`.

```javascript
const requestedTime = Math.floor(playbackTimeMs);
const response = await fetch(`/api/state?time_ms=${requestedTime}`);
if (!response.ok) throw new Error('Could not load match state');
const state = await response.json();
// Before rendering, verify same match, same requested clock and latest request.
if (state.match_id === match.metadata.match_id &&
    state.as_of_match_time_ms === Math.floor(playbackTimeMs)) {
  const player = state.players[selectedPlayerId];
  // player.rating.value === null -> NR
  // player.rating.provisional -> evolving vs finalised
  // player.rating.components and evidence_event_ids -> explanation drawer
}
```

Use an AbortController/request counter to ignore an old response after seeking or switching matches/players. Request at completed-event/seek boundaries or a modest UI interval; do not send a network call every animation frame. Request both team and player data together for consistent panels. The bridge replays the prefix independently for each request, so rewinding is supported. It validates the input once at startup; regenerate/restart the bridge to load a different match.

The current studio player inspector uses this endpoint when available. Static file import still works, but a bridge running another match must not supply its ratings: check match_id. This server binds to 127.0.0.1 and is for local development; hosted streaming, authentication, caching, cloud deployment and AI remain future integration work. If your UI uses another dev server, configure a same-origin proxy for `/api` and `/data`; CORS is deliberately not enabled here.

Ratings are deterministic event heuristics, not official ratings. Render null as NR. Outgoing/dismissed ratings and minutes freeze; the substitute's record evolves from entry. Offsides are descriptive counters without an extra v2 rating penalty; failed offside passes still affect the passer's completion-based component. Do not silently invent a third rating model.

## 8. Offside evidence integration

```javascript
const frozen = offsideAt(match, playbackTimeMs, {
  eventId: selectedOffsideEventId, lifetimeMs: Infinity
});
if (frozen) {
  // Draw frozen.positions and frozen.ball on a separate replay board.
  // Draw effective legal limit at frozen.lineX; optional defender reference at
  // frozen.secondLastOpponentX. Highlight frozen.offenderId.
  // Display frozen.contactTimeMs, marginM and frozen.label.
}
```

Default lifetime is 8 seconds; a selected historical decision can use Infinity. The helper returns null before the decision, even if all future data is preloaded. Use the source period/direction. The effective line is the more advanced of ball and second-last opponent toward the attacked goal; a ball-ahead situation therefore cannot use the defender line alone. The opponent is not necessarily the keeper. `contact.candidates` describes positions, not all offences; only an emitted offside decision is a whistle.

The existing event evidence panel now includes a frozen SVG replay diagram and raw decision fields. It does not stop or overwrite the main live board with historical positions. No real body-part or VAR accuracy is claimed.

## 9. Suggested teammate implementation order

1. Pull this code and run the bridge against offside-match. Read this guide and the three detailed contracts.
2. Reuse model.mjs to wire one shared clock, board, pause/seek/speed and event feed. Preserve exact event IDs and tie ordering.
3. Add scoreboard and all team comparison counters from section 6; read live player/lineup/ratings from the state endpoint.
4. Add P1 restart/last-touch, parry/rebound, substitution and added-time graphics.
5. Add P2 foul/advantage/free-kick/penalty/booking graphics and reduced lineups/emergency keeper/abandoned state.
6. Add P3 offside decision card and separate frozen-source evidence board. Respect invalid observations and direct-receipt exceptions.
7. Add event/player focus and evidence drawers; maintain the same prefix for every panel and recap. Language changes may change text, not IDs or metric values.
8. Run all automated tests and manually exercise the acceptance cases below. Preserve legacy fixtures and rating versions.

## 10. Acceptance checklist for the finished frontend

- [ ] Load legacy 1.3/1.4, P1 1.5, P2 1.6 and P3 1.7 matches without breaking clocks or identity.
- [ ] A receiver has no possession halo before receipt. No pass completion or goal appears early.
- [ ] Ball paths remain connected across saves, parries, deflections and boundary exits; placement is explicitly dead-ball relocation.
- [ ] Throw-in/corner/goal-kick award agrees with last touch and attacked/defended end.
- [ ] Dead-ball intervals increase neither team's controlled time.
- [ ] Added time, second-half seeking and player minutes include actual allowance.
- [ ] Substitutions occur at recorded natural opportunities, preserve slots, and show independent incoming/outgoing ratings.
- [ ] A single yellow retains the player; second yellow/direct red removes them from every subsequent board/reset. Emergency keeper is the current identity.
- [ ] Advantage recalled/played and delayed cautions link to original foul; penalty award and scored/missed attempts are separate.
- [ ] Passive offside position alone never produces a decision. Direct exempt restart receipt remains legal.
- [ ] Offside receipt has no completion/received credit. An invalid shot has no shot/save/goal/assist/key-pass credit; the valid earlier saved shot is retained for rebound offside.
- [ ] Offside evidence uses original contact positions, including the ball and second-last opponent; it cannot appear before decision time or use current positions.
- [ ] Both attack directions and ball-defined offside line render correctly.
- [ ] Seek across a substitution, dismissal, goal and offside in both directions; all panels, ratings and decisions follow the selected prefix.
- [ ] API errors, NR, empty metrics, unused bench and abandoned matches have clear states. Stale responses cannot overwrite the current match/time.
- [ ] Narratives cite source event IDs, never use evaluation-only policies/final summaries as live evidence, and do not claim measured player tracking or VAR.

Automated verification from repository root:

```powershell
py -3.13 -m unittest discover -s simulator -p "test_*.py" -v
py -3.13 -m unittest discover -s backend/tests -p "test_*.py" -v
node --test frontend/tests/*.test.mjs
```

Fixtures: offside-match (P3/current); discipline-match (P2 bookings/dismissal/advantage/penalty); restarts-match (P1 corners, goal kicks, parries/rebounds); substitutions-match and short-match (legacy). Focused controlled tests cover rare branches that a normal seed need not contain. Do not force a goal/card/offside into every generated match just to fill a panel.

## 11. Copy this task to your teammate's Sol chat

```text
Build the frontend integration for all three implemented realism priorities in this repository. Read docs/UI-INTEGRATION.md first, then docs/RESTARTS-AND-CLOCK.md, docs/DISCIPLINE-AND-SET-PIECES.md, docs/OFFSIDE.md, docs/SUBSTITUTIONS.md and docs/PLAYER-RATINGS.md. Inspect frontend/model.mjs, frontend/app.mjs, simulator/ui_server.py and their tests before editing.

Use the actual schema 1.7 events and pure adapter functions. Run python -m simulator.ui_server --input data/examples/offside-match --port 8080 for a same-origin replay plus /api/state?time_ms=... for authoritative team/player stats, live ratings, stints and lineups. Keep one playback clock and reject stale API responses. Preserve legacy matches. Do not use final summary values or evaluation-only.json for live panels and do not invent an HTTP contract or rating formula.

Implement every row of the priority feature matrix and acceptance checklist, including all P1 restarts/rebounds/added time/substitutions; all P2 fouls/advantage/free kicks/penalties/cards/dismissals/emergency keeper; and all P3 source-contact offside, involvement, exceptions, deliberate-play versus deflection/save, invalid attack credit handling, IFK and a separately labelled frozen evidence board. Reuse existing implementations and tests, adapting layout to our UI. Keep point-player/illustrative-motion limitations visible. Run simulator, backend and frontend tests and report which UI acceptance checks you exercised. Complete the work rather than only returning a design plan.
```
