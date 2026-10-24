# Expected goals: simulator and UI handoff

Schema **1.9** adds an explainable estimate to every generated shot. Team and player statistics include running totals, including substitutes. This is an original **uncalibrated synthetic heuristic**, not an Opta/StatsBomb model or a probability fitted to historical football. Keep that qualification visible in the UI.

## Run and preview

From the repository root, with Python installed:

```powershell
py -3.13 -m simulator.generate --seed 42 --scenario match --output data/generated/xg-demo
py -3.13 -m simulator.ui_server --input data/generated/xg-demo --port 8081
```

Open http://127.0.0.1:8081/. The server must stay running. Choose a fresh output directory to retain earlier matches. For a small checked-in example use `--input data/examples/xg-match`; for the existing full movement demonstration use `--input data/examples/movement-match` (xG is derived from its original evidence).

Select **Teams** for the side-by-side statistics, a player for their running xG/creation statistics and existing live rating, or a completed shot for its estimate, input features and full calculation. Your teammate's referee-decision, substitution and goal overlays remain available through the existing jump buttons.

## Event contract

Every schema 1.9 `shot` has an `xg` object:

```json
{
  "value": 0.123456,
  "model": "matchlens-preshot-xg-v1",
  "calibrated": false,
  "counted": true,
  "features": {
    "distance_m": 18.2,
    "angle_radians": 0.38,
    "blocker_ids": ["away-04"],
    "nearest_defender_m": 2.1,
    "goalkeeper_id": "away-01",
    "keeper_in_cone": true,
    "keeper_off_line_m": 1.2,
    "situation": "open_play",
    "body_part_assumption": "foot"
  },
  "logit_contributions": {"intercept": -1.3},
  "method": "geometry_logistic_heuristic"
}
```

Illustrative numbers, abbreviated contributions. Actual output lists every contribution. `metadata.expected_goals_model` and canonical statistics' `expected_goals_model` publish the version, coefficients, selected penalty prior and limitations. `value` is a fraction, not a percentage. Display two or three decimals; retain six decimals for aggregation.

`start` and `pitch_snapshot.players` are the **pre-shot source evidence**. Coordinates use the fixed 105 × 68 metre pitch. Home attacks positive x in period 1 and negative x in period 2; away is the reverse. Distance is to the goal centre; angle is between the two posts. Outfield blockers are opponents inside the triangle between shooter and posts. Nearest-defender pressure uses outfield opponents, excluding the current goalkeeper. The goalkeeper's coverage and distance off the line also affect the estimate. Goalkeeper identity follows recorded role assignments after a dismissal.

## Calculation and limitations

For non-penalties, with distance D, goal angle A, outfield blockers B, nearest-defender distance N, and goalkeeper distance off the line K:

```text
pressure = max(0, 3 - N) / 3     (0 when no outfield defender is present)
z = -1.3 - 0.10D + 1.8A - 0.22B - 0.35pressure
    + 0.70 if the recorded goalkeeper is outside the shot triangle
    - 0.03 * min(K, 10) if the goalkeeper covers the triangle
    - 0.35 for a direct free kick
xG = clamp(sigmoid(z), 0.001, 0.95), rounded to six decimals
```

The conditional lines are additive terms, not replacements for z. A missing keeper does not receive an uncovered-keeper bonus. Penalties use an explicitly selected **0.76 prior**, irrespective of finisher/keeper identity; this is a modelling assumption, not a claimed calibrated penalty conversion rate. A penalty record still contains its geometry, but its method identifies that the prior determined its value.

The model deliberately excludes shot result, aim/end coordinates, shot/ball speed, kick effort, shooting skill and the shot's later trajectory. Those would leak post-shot information or individual finishing ability into this chosen pre-shot measure. Adding xG consumes no random numbers and does not determine shot outcomes or alter the existing match-rating formula. Headers, aerial height, first-touch technique, body-part distinctions, real tracking and trained probability calibration are not implemented.

The source model's selected coefficients should be replaced with a trained and held-out calibrated model before claiming real-world probabilities. General background on pre-shot inputs and the distinction from post-shot models: [Hudl/StatsBomb expected goals glossary](https://support.hudl.com/s/article/expected-goals?language=en_US&topic=Statsbomb_Global_Football_Data_Glossary). No coefficients have been copied from that source.

## Team and player statistics

Both `summary.teams[team_id]` and `summary.players[player_id]`, and the same structures from `/api/state?time_ms=...`, contain:

| Field | Meaning |
|---|---|
| `xg` | Sum of valid completed shots' estimates, including penalties |
| `non_penalty_xg` | Same sum excluding penalties |
| `xg_per_shot` | xG divided by valid shot count; null with no shots |
| `goals_minus_xg` | Valid goals minus xG; descriptive, not a rating adjustment |
| `xg_assisted` | xG of shots directly created by the player's qualifying completed pass; team value sums its players |
| `shot_conversion_percentage` | Valid goals / valid shots × 100; null with no shots |
| `shot_accuracy_percentage` | Shots on target / valid shots × 100; null with no shots |
| `xg_coverage` | `shots_with_xg`, `shots_without_xg`, `complete` |
| `xg_model` | Version string |

Zero shots means zero total xG, npxG and xG assisted. Missing source evidence for any counted shot makes the corresponding total **null**, with explicit coverage counts; never display unknown totals as zero. Non-penalty coverage is independent of penalty coverage. A missing estimate on a qualifying created shot similarly makes its creator's and team's xG assisted unknown.

Creation credit reuses the existing rating engine's strict key-pass rule: the most recent completed pass in the same possession, team and half must reach the eventual shooter, originate from a different player and finish no more than **10 seconds before shot contact**. The shot consumes that candidate. Failed passes, stoppages, saves, offside, opponent touches, substitutions, dismissals and period changes invalidate the appropriate chain. A direct restart delivery is not classified as a key pass by this rule. xG assisted applies to non-scoring shots too; it is distinct from actual assists, expected assists for arbitrary passes and possession-chain credit.

All accumulators sum integer millionths of xG, avoiding rounding drift between event, player and team totals. Own goals are not currently generated. Do not invent keeper xG saved/PSxG, per-90 values or rating weights from these fields; these require separate definitions/models.

## Frontend implementation for a coding assistant

1. Keep one playback clock and a completed-event prefix. Do not use final `summary.json` values for live panels. Events become statistical observations at their emitted completion time, even though xG inputs are frozen at contact. Do not reveal a pending shot's result.
2. `frontend/xg.mjs` exports `shotXg(event, players)` and pure `expectedGoalsAt(match, time)`. The latter returns `{teams, players, shots}` with canonical snake-case metric names. `frontend/model.mjs`'s `statistics` merges these team metrics into the existing team object. Use `shotXg` for the individual shot evidence card. Python's source of truth is `simulator/xg.py`.
3. The browser helper recomputes from source rather than trusting arbitrary uploaded xG values. The schema 1.9 validator rejects event calculations that do not match their evidence. Python and JavaScript calculations have parity tests.
4. The local bridge returns authoritative player stats, current lineups, substitutions and ratings plus xG using the same prefix. Continue rejecting stale asynchronous responses by requested timestamp, match identity and selected player. Static-only hosting uses the pure browser reducer for xG; live player ratings still require the bridge.
5. Keep the **xG estimate · uncalibrated** label. For `null`, show an em dash and coverage explanation. The event evidence card reports exclusion from totals for invalid/offside attacks. A hypothetical estimate on an invalid shot is not statistical credit.
6. Render team xG/npxG/xG per shot/goals minus xG/xG assisted/shot accuracy/conversion side by side. Player focus shows the same relevant fields. An optional future shot map can use `expectedGoalsAt(...).shots` and original `event.start` coordinates, with circle area proportional to xG; use side/period direction consistently. A cumulative chart should step only at valid completed shots. Neither additional chart is required by the current UI.
7. Preserve team/player filters, substitutions, dismissal roles, natural stoppages, added-time clocks, the teammate's decision/pop-up components and P1–P3 behaviours. Schema 1.9 extends 1.8, so recorded motion remains the rendering source.

## Existing matches and checks

Schema 1.3–1.8 files stay usable: where source frames exist, both reducers derive estimates without modifying events. Recompute an old on-disk summary with `py -3.13 -m simulator.statistics --input data/generated/your-match`. Truly incomplete legacy evidence remains unknown. New generation writes the full event-level `xg` field automatically; no separate random metric generation or manual tagging is needed.

Fixtures: `data/examples/xg-match` is a small schema 1.9 match with canonical totals; earlier full-length fixtures still exercise penalties, invalid attacks and goalkeeper changes. Tests cover source determinism, no outcome/speed leakage, distance/angle/defender effects, attacking-direction symmetry, penalty exclusion from npxG, invalid shots, prefix/rewind behaviour, unknown coverage, tampering and browser/Python parity. Existing simulator, backend and UI suites remain part of verification.
