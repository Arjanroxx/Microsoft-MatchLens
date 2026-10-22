# Match realism checklist

This is a connected, simplified football simulation. Adding event labels alone does not make it a complete match engine. Each new feature must change the underlying state, restart, eligible actors, statistics, and UI consistently.

Schema 1.7 implements substitutions and all five items of Priority 3, alongside Priorities 1 and 2, within the documented selected 2D rule models. Features below are **not implemented** unless checked. See [the implementation and UI handoff](RESTARTS-AND-CLOCK.md) for the exact scope and remaining 2D limitations. Priorities are engineering recommendations, not additional hackathon requirements.

## Implemented foundations

- [x] Two halves, direction changes, kickoff and final score.
- [x] Persistent active player positions and connected ball paths.
- [x] Pass completion/interception linked to geometry and possession.
- [x] Shot outcomes tied to goal-mouth position and simplified keeper reach.
- [x] Team/player event statistics and time-based possession.
- [x] Transparent, evolving player ratings from observed actions.
- [x] Bench, position-compatible substitutions, current-rating selection, active lineup and stint minutes.
- [x] Mostly 60–70 minute changes; occasional half-time changes; configurable limits represented in metadata.
- [x] Interval behaviour changes and temporary pressure response after conceding.
- [x] Natural ball-out/goal stoppages, explicit restart placement/delivery, and resume events.

## Priority 1: coherent ball-out and restart model — implemented in 1.5

- [x] **Touchline exits and throw-ins:** actual whole-ball first crossing, last touch, restart team/location and possession transition.
- [x] **Goal kicks and corners:** goal-line decisions use the defending end and last toucher; misses and keeper parries have distinct continuations.
- [x] **Saved shots and rebounds:** geometry-derived save-to-hold/parry, continuous parry paths, linked rebound shots and defender clearances.
- [x] **Natural substitution opportunities:** queued plans execute at ball-out/goal stoppages or halftime; no synthetic substitution-only break.
- [x] **Added time and clock:** explicit qualifying lost-time ledger, minimum announcement, further allowance, actual half durations, monotonic replay timestamps, renderer/statistics/stint updates.

Acceptance is tested: the next actor/restart follows ball location and last touch, only explicit dead-ball placement relocates the ball, and no live possession accrues while out. The remaining simplifications (2D technique, motion heuristics, no illegal-restart sanctions) are stated in [RESTARTS-AND-CLOCK.md](RESTARTS-AND-CLOCK.md).

## Priority 2: fouls, cards, free kicks, and penalties — implemented in 1.6

- [x] **Tackles and fouls:** reachable, evidence-backed clean wins/misses/contact or dangerous-play offences, offender/victim/location and proper continuation.
- [x] **Free kicks:** correct team/location, direct and indirect distinction, bounded advantage with played/recalled outcomes and delayed cautions.
- [x] **Penalties:** applicable direct-contact offence in the defending penalty area, separate setup/release/shot/keeper response and end-of-half completion.
- [x] **Yellow cards:** attributable offence/reason and caution count; no automatic lineup removal for a single yellow.
- [x] **Second-yellow and direct-red dismissals:** remove the player, freeze minutes/ratings, reduce active team size, preserve subsequent snapshots/restarts, and prevent ordinary replacement. Emergency keeper assignment is supported.
- [x] **Discipline in ratings:** schema 1.6 uses rating v2 with published tackle/foul/card/penalty components; legacy matches retain v1. Goals conceded are not debited to every defender.

Acceptance is tested: sent-off players cannot act or remain in later snapshots; the lineup, keeper, substitutes, team/player statistics and board follow the event stream. Fewer than seven players terminates the match without inventing a forfeiture score. See [DISCIPLINE-AND-SET-PIECES.md](DISCIPLINE-AND-SET-PIECES.md) for the exact event/UI contract and selected-offence scope; handball, DOGSO/SPA and other unmodelled sanctions are explicitly outside this simplified engine.

Rule grounding: [IFAB Law 12](https://theifab.com/laws/latest/fouls-and-misconduct/), with Laws 3/13/14 linked in the implementation guide.

## Priority 3: offside — implemented in 1.7

- [x] Evaluate attacking position at the teammate's relevant ball contact, using the ball and second-last opponent, not just the goalkeeper.
- [x] Separate an offside position from an offence involving active participation.
- [x] Handle restart exceptions and deliberate-play/deflection distinctions under the selected law version.
- [x] Cancel invalid attacking outcomes, produce the appropriate restart, and preserve decision evidence.
- [x] Show a replay line only from the source positions at the relevant contact time; label the limitations of our 2D point-player model.

Reference: [IFAB Law 11](https://theifab.com/laws/latest/offside/). Our point-player simulation cannot claim body-part-accurate VAR decisions.

Acceptance: an offside cannot be appended to a sequence while leaving the invalid goal/assist, possession, and rating credits intact.

See [OFFSIDE.md](OFFSIDE.md) for the exact selected involvement/control proxies and limitations, and [UI-INTEGRATION.md](UI-INTEGRATION.md) for the complete P1-P3 teammate handoff and runnable live-rating API. Independent attempted challenges, gestures and body-part officiating are outside this point-player model.

## Priority 4: players, movement, and match rhythm

- [ ] Fatigue and stamina that evolve with actual time/activity; fresh substitutes should affect movement through explicit state, not an automatic performance bonus.
- [ ] Injury/medical absences and injury substitutions, with suitable limits and replacement eligibility.
- [ ] Continuous player tracking samples before claiming running speed, distance, sprints, or work rate.
- [ ] Better receiving movement, carries, dribbles, aerial balls, and headers; current players are mostly held fixed during ball flight.
- [ ] Distinguish clearances, blocked shots, duels, deflections, and loose balls.
- [ ] More realistic keeper positioning, catches/parries, reaction and reach rather than a simple distance test.
- [x] Emergency keeper role reassignment after goalkeeper dismissal (captain and injury-related role changes remain future work).
- [ ] Score/time-dependent risk changes without scripting a successful comeback.

## Priority 5: calibration and explainability

- [ ] Define plausible target distributions for goals, shots, pass completion, possessions, ball speeds, stoppages, cards, and substitutions.
- [ ] Evaluate many held-out seeds; fix pathological matches without forcing every match to have the same totals.
- [ ] Calibrate difficulty and rating weights against reviewed scenarios. They currently remain original heuristics.
- [ ] Version event schemas and migrations whenever new outcomes change past counts.
- [ ] Preserve evidence/corrections so goal cancellations and referee revisions rebuild team/player statistics, ratings, and recaps.
- [ ] Keep intended action, observed outcome, and interpretation separate; analytics must infer stories from events rather than simulator labels.

## Optional competition features

- [ ] Extra time and penalty shoot-outs only if the selected competition requires them; a league match can finish level.
- [ ] VAR/review corrections only with an explicit review/evidence model and state rollback.
- [ ] Special concussion or temporary-absence protocols only after choosing applicable competition rules.

Recommended next build: **movement/calibration**, with source-grounded tests at each step. A connected smaller model is preferable to random cards, offsides, or penalties that do not affect the match.
