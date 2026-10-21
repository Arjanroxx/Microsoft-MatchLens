# Match realism checklist

This is a connected, simplified football simulation. Adding event labels alone does not make it a complete match engine. Each new feature must change the underlying state, restart, eligible actors, statistics, and UI consistently.

Substitutions are the focus of this implementation. The remaining features below are **not implemented** unless checked. Priorities are engineering recommendations, not additional hackathon requirements.

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
- [x] Explicit simplified substitution breaks and resume events.

## Priority 1: coherent ball-out and restart model

- [ ] **Touchline exits and throw-ins:** detect actual line crossings instead of clamping the ball to the pitch; record last touch, restart team/location, and possession change.
- [ ] **Goal kicks and corners:** distinguish an unsuccessful shot/clearance crossing the goal line from a goalkeeper save. Current non-goal shots simplify to opponent recoveries.
- [ ] **Saved shots and rebounds:** save-to-hold, parry, rebound shot, and defender clearance should be different outcomes with consistent ball continuation.
- [ ] **Natural substitution opportunities:** attach changes to these real modelled stoppages; replace the synthetic substitution-break approximation.
- [ ] **Added time and clock:** log lost time, announce added time, finish each half after its added interval, and update every timestamp/renderer assumption. Current duration is two fixed halves, with no added time.

Acceptance: the next actor/restart follows the ball location and last touch, no ball teleportation in open play, and no live possession accrues while the ball is out.

## Priority 2: fouls, cards, free kicks, and penalties

- [ ] **Tackles and fouls:** distinguish clean ball wins from offences; attribute offender/victim, location, and stoppage.
- [ ] **Free kicks:** use the correct restart team/location; separate direct/indirect types and advantage decisions.
- [ ] **Penalties:** trigger from an applicable offence, not a random unrelated penalty label; use a separate kick sequence and keeper response.
- [ ] **Yellow cards:** record player identity, reason, and count without automatically changing the on-pitch lineup.
- [ ] **Second-yellow and direct-red dismissals:** remove the player, stop their minutes/rating, change active team size and positioning, and prevent replacing the dismissed player as an ordinary substitution.
- [ ] **Discipline in ratings:** version the rating model when adding card/foul penalties. Do not treat every foul as a booking or every team-conceded goal as individual fault.

Reference for future implementation: [IFAB Law 12](https://theifab.com/laws/latest/fouls-and-misconduct/). Rules and competition settings should be verified for the intended season when implementing.

Acceptance: a dismissal affects subsequent movement, pass targets, goalkeeping arrangements where relevant, statistics, and the board; there are no actions by a sent-off player.

## Priority 3: offside

- [ ] Evaluate attacking position at the teammate's relevant ball contact, using the ball and second-last opponent, not just the goalkeeper.
- [ ] Separate an offside position from an offence involving active participation.
- [ ] Handle restart exceptions and deliberate-play/deflection distinctions under the selected law version.
- [ ] Cancel invalid attacking outcomes, produce the appropriate restart, and preserve decision evidence.
- [ ] Show a replay line only from the source positions at the relevant contact time; label the limitations of our 2D point-player model.

Reference: [IFAB Law 11](https://theifab.com/laws/latest/offside/). Our point-player simulation cannot claim body-part-accurate VAR decisions.

Acceptance: an offside cannot be appended to a sequence while leaving the invalid goal/assist, possession, and rating credits intact.

## Priority 4: players, movement, and match rhythm

- [ ] Fatigue and stamina that evolve with actual time/activity; fresh substitutes should affect movement through explicit state, not an automatic performance bonus.
- [ ] Injury/medical absences and injury substitutions, with suitable limits and replacement eligibility.
- [ ] Continuous player tracking samples before claiming running speed, distance, sprints, or work rate.
- [ ] Better receiving movement, carries, dribbles, aerial balls, and headers; current players are mostly held fixed during ball flight.
- [ ] Distinguish clearances, blocked shots, duels, deflections, and loose balls.
- [ ] More realistic keeper positioning, catches/parries, reaction and reach rather than a simple distance test.
- [ ] Captain/keeper role reassignment for exceptional lineup changes.
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

Recommended next build: **ball-out/restarts → fouls/free kicks/discipline → added time → offside**, with source-grounded tests at each step. A connected smaller model is preferable to random cards, offsides, or penalties that do not affect the match.
