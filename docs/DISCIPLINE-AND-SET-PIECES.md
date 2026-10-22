# Priority 2: challenges, fouls, cards and set pieces

Schema **1.6** implements the six Priority 2 items on top of the 1.5 restart/added-time model. Read this alongside [UI-INTEGRATION.md](UI-INTEGRATION.md) and [RESTARTS-AND-CLOCK.md](RESTARTS-AND-CLOCK.md). The simulator still requires only Python's standard library; no install or cloud dependency was added.

## Run and preview

```powershell
py -3.13 -m simulator.generate --seed 6 --output data/generated/priority-two-demo
py -3.13 -m simulator.replay --input data/generated/priority-two-demo --speed 60
py -3.13 -m http.server 8080
```

Open `http://localhost:8080/frontend/` and load the generated `metadata.json` and `events.jsonl` together. The checked-in equivalent is `data/examples/discipline-match/`. This is a full-length match: seed 6 demonstrates a second-yellow dismissal, a penalty, free kicks and advantage. Generate seed **54** for a straight-red example and seed **0** for an indirect-free-kick example. Seeds demonstrate particular paths in this generator version; a generic match need not contain a red card or penalty. Short demos work with `--minutes-per-half 5`, but rare incidents are less likely.

Use a new output directory to keep earlier matches. A summary recalculation cannot invent fouls or dismissals in old event files. Schema 1.3–1.5 fixtures remain supported and keep rating model v1; regenerate events to get the 1.6 features.

## Connected challenge and referee model

Only an active opposing player within 2.5 m of the current carrier can attempt a challenge. A seeded decision selects whether to attempt it, its effort, timing error and standing-tackle/raised-boot technique. A bounded 0.25 s movement leads to the recorded challenge geometry. A raised boot remains at a non-contact distance where possible. These are synthetic action controls, not random metric or card labels.

`resolve_challenge` deterministically interprets the evidence:

| Outcome | Evidence and continuation |
|---|---|
| `won` | Timely challenge within ball reach; victim loses possession, challenger recovers the same ball |
| `missed` | No successful ball contact or modelled offence; current carrier retains play |
| `foul`, careless | Late contact; direct free kick or penalty, normally no card |
| `foul`, reckless | More forceful late contact, or reckless dangerous raised boot; yellow |
| `foul`, excessive | Very high-effort, very late contact; direct red for serious foul play |
| `foul`, dangerous | Nearby raised boot without contact; indirect free kick, no automatic card |

The thresholds are original heuristics and exposed in source/evidence, not professional refereeing calibration. The selected offence model does not cover every Law 12 offence; see scope below.

### Events and links

`tackle` fields: `player_id` (challenger), `team_id`, `victim_id`, `location`, `outcome` (`won/foul/missed`), `controls`, `decision`, and `challenge_snapshot.players/period_time_ms`. This snapshot is contact evidence, not a ball-flight action snapshot; do not animate a tackle as a kick or invent shot speed from it.

`foul` fields: offending `player_id/team_id`, `victim_id`, `location`, `tackle_event_id`, `decision` (`offence`, `severity`, `card`) and the awarded `restart`. The victim's team is resolved from metadata. The offence location and the eventual restart location can differ for penalties and attacking indirect free kicks inside the goal area.

```text
challenge → tackle (won) → turnover → recovery
          → tackle (missed) → continue current possession
          → tackle (foul) → foul → whistle/stoppage → sanction → restart
                                → advantage pending → played carry, or recalled whistle
```

Restart classification uses the actual offence and defending end in that half. A direct-contact offence in the offender's penalty area awards a penalty; the same offence elsewhere awards a direct free kick. A non-contact dangerous-play offence awards an **indirect** free kick even inside the penalty area. Penalty-area lines are included. An attacking indirect free kick inside the opponents' goal area is relocated to the nearest parallel goal-area line.

## Advantage and delayed bookings

The referee can consider advantage on a direct, non-penalty offence when an attacking continuation is plausible. Serious-foul-play red cards and an impending second yellow stop play immediately in this model.

1. Emit `advantage` with `outcome: pending` and `foul_event_id`.
2. Give nearby defenders a short reaction, then assess the actual forward lane.
3. If continuation is safe, emit a bounded `carry` with a measured trajectory at 4 m/s, then `advantage` with `outcome: played` and `continuation_event_id`.
4. If the lane is closed, emit `outcome: recalled` and restart from the **original offence location**. No speculative failed pass/goal was committed, so there are no phantom statistics to undo.

This is a bounded single-carry advantage model, not a full multi-action referee evaluator. The carrier keeps possession during a carry. It is not a pass attempt, shot or measured player tracking feed.

A reckless offence whose advantage succeeds remains in a pending booking queue. Its yellow card is issued at the next natural stoppage, before substitutions; any remaining caution is dealt with at the period-ending whistle. A player awaiting that booking is excluded from another modelled challenge until it is shown. This avoids ambiguous unshown-caution sequences in the simplified engine. Do not show `decision.card` as an already-shown card: wait for the actual `card` event.

## Cards and dismissals

`card` contains `card: yellow/red`, `reason`, `foul_event_id`, `stoppage_event_id`, and `caution_number` for yellows. A yellow alone does **not** remove a marker. A straight red is followed by a `dismissal`. A second caution is a second yellow followed by a `dismissal` with reason `second_yellow`; do not count it as two dismissals.

`dismissal` contains the sent-off `player_id/team_id`, `reason: direct_red/second_yellow`, source foul/stoppage IDs, and `positions_after` **excluding that player**.

- The player is removed from active pitch positions and formation slots immediately.
- Later movement, pass targeting, snapshots and action eligibility use the reduced lineup.
- Ordinary substitutions cannot replace the sent-off player, and unused substitutes cannot restore eleven players.
- The departing player's stint ends, `squad_status` becomes `sent_off`, and rating/statistics freeze.
- Current lineups persist through goals, half-time and restart setups. A missing kickoff taker is replaced by an active outfielder; original shirt numbers do not imply active roles.

Card administration consumes an explicit scaled delay and records `time_lost` with reason `disciplinary_administration`; it is included in the existing added-time ledger. Possession stays unassigned during this dead interval.

### Goalkeeper dismissal

The engine designates an **already active outfielder** as emergency goalkeeper, choosing the nearest to the defending goal. It emits `goalkeeper_change` with that player's ID, `previous_goalkeeper_id`, `formation_slot: 1`, reason and `positions_after`. No extra player enters; the team remains a player down.

Use this assignment for subsequent saves, goals conceded, goal kicks, positioning and keeper labels. Do not hardcode `<team>-01` or search metadata's original GK role after a dismissal. Original role metadata is preserved; player snapshots expose `current_role` and `has_kept_goal`. Ordinary substitutions also exclude the current emergency keeper. The engine does not automatically substitute an outfielder for a bench keeper; that managerial option is future work.

If a team falls below seven active players, emit `match_abandoned`, stop football actions, and finish that match's data with `metadata.match_status: abandoned`. Do not invent a forfeiture score. The current on-field score is retained; competition-specific decisions are outside this simulation. A completed match has `match_status: completed`.

## Free kicks and penalties

New `restart.reason` values are `direct_free_kick`, `indirect_free_kick`, and `penalty`. These use the same stoppage/placement/resume contract and actual-clock fields as 1.5.

| Restart | Execution |
|---|---|
| Direct free kick | At the offence location; may be delivered to a teammate or taken as a shot when within shooting range |
| Indirect free kick | Delivered to another player first; cannot become a direct set-piece shot |
| Penalty | From the appropriate spot (x=11 or 94, y=34), with a separate setup, release and linked shot |

Free-kick opponents are moved at least 9.15 m away, with the goal-line/between-posts exception for the defending keeper. At a defensive free kick inside the team's penalty area, opponents are placed outside that area. Penalty setup places the keeper on the goal line; all other players except the taker are outside the penalty area, behind the spot and at least 9.15 m away. These are planar position constraints, not a model of foot/arm technique or encroachment sanctions.

Set-piece shots retain the ordinary `type: shot`, speed evidence and keeper geometry, with:

```text
set_piece_type: penalty / direct_free_kick
restart_event_id: originating restart
goalkeeper_id: currently assigned active keeper
```

Trace `shot → restart → source_event_id → foul → tackle` for the explanation. A penalty cannot appear without an applicable offence. A scoring set-piece shot still creates one linked `goal`; count the goal once. An unsuccessful penalty counts as missed whether saved or off target. Keeper saves still receive only one credit from the shot.

An awarded penalty is completed even if setup crosses the half's target whistle time. In an end-of-half extension, a goal ends the half without another kickoff; a saved/missed kick is completed without permitting an outfield rebound attempt after time. Ordinary in-time saves may produce the same held/parried/rebound sequences as other shots. There is no penalty shoot-out.

## Statistics contract

The following fields exist separately below **both** `summary.teams.<team>` and `summary.players.<id>`. Final summary values are not live playback values: use the shared event-prefix reducer.

| Python key | JS team adapter key | Meaning |
|---|---|---|
| `tackles.attempted` / `.won` | `tackles` / `tacklesWon` | Attempted and cleanly won challenges |
| `tackles.foul` / `.missed` | `tacklesFoul` / `tacklesMissed` | Failed challenge categories; attempted = won + foul + missed |
| `fouls_committed` / `fouls_won` | `fouls` / `foulsWon` | Attribution to offender and victim |
| `yellow_cards` / `red_cards` | `yellowCards` / `redCards` | Shown cautions / dismissals; second yellow gives 2 yellows + 1 dismissal |
| `second_yellow_dismissals` | `secondYellowDismissals` | Subset of red-card/dismissal count |
| `free_kicks` | `freeKicks` | Direct + indirect free kicks taken |
| `direct_free_kicks` / `indirect_free_kicks` | `directFreeKicks` / `indirectFreeKicks` | Restart breakdown |
| `penalties_won` / `penalties_conceded` | `penaltiesWon` / `penaltiesConceded` | Applicable penalty offences, attributed at the foul |
| `penalties_taken` / `penalties_scored` / `penalties_missed` | `penaltiesTaken` / `penaltiesScored` / `penaltiesMissed` | Completed penalty-shot outcomes |

Free-kick delivery is a `restart_delivery`, separate from ordinary pass accuracy. A direct free-kick shot belongs in shot totals, as does a penalty. A free-kick award may remain untaken at a whistle, so taken restart counts need not equal foul counts. Advantage-played fouls do not create a free kick. Shots from unrelated later play are not retroactively marked as set pieces.

`summary.lineups.<team>` adds `sent_off` and `goalkeeper_id`. `substituted_off` excludes dismissed players. Player snapshots retain their original records, with frozen exact exit times for sent-off players. Before abandonment, active players show `on_pitch`; after abandonment they show `match_ended` and finalised ratings.

### Player-minute reconciliation

Do not assume player minutes always sum to 11 × elapsed time after dismissals. Without temporary absences:

```text
team_player_minutes_ms = 11 * actual_elapsed_ms
                        - sum(actual_elapsed_ms - dismissal.match_time_ms)
```

Use dismissals already in the current event prefix and include actual added time. Substitutions preserve team headcount and do not add another deficit. A sent-off substitute who had entered still keeps only their own entrance-to-dismissal stint.

## Rating model v2

New 1.6 matches use `matchlens-event-rating-v2`. Legacy 1.3–1.5 files continue to use v1; recalculating their summaries does not reinterpret historical scores with discipline weights.

- Clean tackles add 0.06 to the existing role-weighted defence component, under its existing cap.
- Fouls subtract 0.02 each, capped at −0.40.
- Yellows subtract 0.20 each, capped at −0.40.
- A dismissal adds a separate −0.80 debit. Thus a second yellow includes two caution debits and one dismissal debit; the displayed red `card` record does not add a second dismissal penalty.
- Missed penalties subtract 0.20 each, capped at −0.60.
- The existing baseline, 1–10 bounds, action components, evidence references and NR eligibility remain; a dismissal also supplies enough decisive evidence for a rating.

These are explicit original weights, not a calibrated commercial rating. A foul is not automatically a card. Team-conceded goals do not penalise every defender: keeper-conceded goals remain contextual debits for the actual assigned keeper. Emergency keepers retain their original outfield role weights while receiving their observed save/keeper-conceded components; prior history is not rewritten as if they had kept goal all match.

## Frontend integration

The bundled adapter/main screen already supports the new restart labels, team counters, card markers, sent-off removal and clock behaviour. Custom discipline/formation/penalty panels can use this contract:

```javascript
import {prepare, boardAt, statistics, lineupsAt, disciplineAt} from './model.mjs';
const match = prepare(metadata, events);
const board = boardAt(match, playbackMs);
const teams = statistics(match, playbackMs).teams;
const lineups = lineupsAt(match, playbackMs);
const discipline = disciplineAt(match, playbackMs);
// lineups.onPitch, lineups.bench, lineups.substitutedOff, lineups.sentOff,
// lineups.goalkeepers.home / away
// discipline[playerId]: yellowCards, redCards, sentOff, dismissalReason,
//                       fouls, role (including emergency GK)
```

Render `board.positions` instead of assuming 22 markers. A yellow badge appears only after the `card` event. Remove a player at `dismissal`, preserve their historical card/stats panel, and never move them into the unused bench group. Use `goalkeeper_change` for the new keeper label and formation slot. Rewinding before dismissal restores that player; rewinding before the caution clears its badge. Do not read final red counts or final roles to style earlier playback.

`carry` is a sixth ball-action kind. It has the same source snapshot, trajectory and measured speed contract, but retains the carrier highlight during movement. It does not generate passing/shot statistics. A `tackle` uses `challenge_snapshot`, not `pitch_snapshot`, so generic renderers do not treat it as an extra ball flight.

Recommended UI-owner checklist:

- [ ] Show foul offender, victim, severity, original location, awarded restart and source IDs.
- [ ] Separate pending/played/recalled advantage from a foul whistle; wait for actual card events before showing bookings.
- [ ] Display two yellows and one dismissal for a second yellow, without double counting the red.
- [ ] Permit fewer than 11 markers per team; maintain dismissed history separately from substitutions/bench.
- [ ] Update keeper identity from the event prefix and retain it across restarts/half-time.
- [ ] Explain penalty provenance and show setup/shot/keeper outcome; never count shot + goal as two goals.
- [ ] Keep tackle, foul, restart and penalty counters separate in side-by-side panels.
- [ ] Read player ratings from Python/backend snapshots and display model v2/components; do not use final ratings early.
- [ ] Reconcile player minutes using the dismissal deficit and actual added-time clock.
- [ ] Handle `match_abandoned` as a terminated match with a retained score, not a full-time result/forfeit decision.
- [ ] Rebuild all these states when seeking backwards; use sequence for tied-time cards/dismissals/keeper changes.

These boxes are presentation handoff tasks, not missing simulator mechanics. The teammate can design specialised panels independently of the event engine.

## Verification and selected rule scope

Tests cover clean/missed/illegal challenges, both defending ends and penalty-area boundaries, direct/indirect distinction, no-card careless fouls, shown cautions, second-yellow and direct-red removal, delayed bookings/advantage recall, penalty setup and end-time completion, emergency keeper assignment and substitution exclusion, fewer-than-seven abandonment, player-minute/counter reconciliation, legacy v1 ratings, and corrupted evidence rejection. Natural seeds exercise the ordinary generation paths; controlled, evidence-backed test states cover rare keeper-dismissal and abandonment cases.

Verification for this update: **73 simulator + 16 backend + 27 frontend tests passed**. The simulator regression includes all five profiles across 12 full-match seeds. Another 727 replay checkpoints matched Python/JavaScript main counters, possession and active/dismissed lineups. The actual app entrypoint passed a DOM smoke check for startup, the 21-player post-dismissal state, card counters and rewind to 22 players. Terminal replay and the backend evidence/narrative reader also consumed the new fixture. These are automated/state checks; no browser visual-layout inspection is claimed.

Rules checked against IFAB 2026/27: [Law 12](https://theifab.com/laws/latest/fouls-and-misconduct/), [Law 13](https://theifab.com/laws/latest/free-kicks/), [Law 14](https://theifab.com/laws/latest/the-penalty-kick/) and [Law 3](https://theifab.com/laws/latest/the-players/). Those ground restart, caution/dismissal, keeper and minimum-player distinctions. The numerical challenge policy and rating weights are our own simulation choices.

The model covers the selected contact/dangerous-play offences above. Handball, DOGSO/SPA tactical sanctions, dissent, persistent infringement, bench/staff misconduct, injuries, full advantage sequences, encroachment/retakes, wall technique, illegal keeper handling, video review are not generated. Schema 1.7 adds selected point-player offside; see [OFFSIDE.md](OFFSIDE.md). It remains an uncalibrated planar simulation rather than a complete referee or professional tracking engine.
