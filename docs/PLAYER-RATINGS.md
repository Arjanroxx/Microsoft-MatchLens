# Player statistics and match ratings

Every generated `summary.json` now includes **all roster players**, keyed by player ID in `players`, plus a versioned `player_rating_model` specification. Team fields remain compatible. Neither counters nor ratings are independent random outputs.

## Run or upgrade

```powershell
# New match: player records and ratings are automatic.
py -3.13 -m simulator.generate --seed 42 --output data/generated/player-match-001

# Existing match: update summary only, preserve events and metadata.
py -3.13 -m simulator.statistics --input data/generated/evolving-match
```

## Player fields

| Field below `players.<player_id>` | Definition |
|---|---|
| `name`, `team_id`, `shirt_number`, `role` | Roster identity |
| `minutes_played`, `minutes_basis` | Elapsed playing time; assumes all 22 roster players start and there are no substitutions/dismissals |
| `passes.attempted/completed/incomplete` | Actions attributed to this passer |
| `passes.accuracy_percentage` | Completed / attempted; null with no attempts |
| `passes.hard_completed` | Completed attempts with heuristic difficulty ≥65 |
| `passes_received` | Successful receptions from other players' pass events |
| `goals`, `assists`, `key_passes` | Linked attacking contributions, defined below |
| `shots.total/on_target/off_target` | Own shots; on target includes goals and saved shots |
| `interceptions`, `recoveries`, `turnovers`, `pressure_events` | Attributable event counts; pressure is an observation count, not unique pressing episodes |
| `saves`, `goals_conceded` | Goalkeeper contributions/context inferred only when the opposing roster has exactly one goalkeeper |
| `metrics` | The same distance, difficulty, and ball/shot speed distributions as team statistics, attributed to each action's player |
| `involvement_events` | Count of unique attributable event IDs, including receptions and contributions inferred from other players' actions |
| `rating` | Score, eligibility, component breakdown, evidence, model version and provisional flag |

An interception is credited to `interceptor_id`, not the failed passer. A save is credited to the defending keeper. A scoring shot and its goal event produce one shot and one goal; the goal is not counted twice. Rating does not use latent passing/shooting skill attributes from metadata.

## Key passes and assists

A completed pass is a key pass when the **next recorded pass-to-shot link** satisfies all of:

1. Same possession, team, and period.
2. The recipient takes the shot; passer and shooter are different players.
3. The shot is released within 10 seconds after pass completion.
4. No intervening pass replaces it, and no turnover/restart/recovery invalidates the link.

The key pass becomes an assist only when a subsequent goal explicitly references that shot's event ID. A saved/missed shot earns no assist. These are our documented synthetic-match definitions, not an official provider's assist rules. Own goals, deflections, and rebounds are outside the current simulation.

Key-pass/assist evidence contains the source pass and shot/goal event IDs. Future goals are never used in an earlier playback snapshot.

## Rating: `matchlens-event-rating-v1`

This is an original **uncalibrated event-based heuristic**, on a 1–10 scale. It is not an official or commercial match-rating product and does not measure all aspects of football performance.

Start at **6.0**, add the components below, clamp to 1–10, then round to one decimal. `rating.components` contains the actual contributions used. `rating.unclamped_value` exposes the sum before clamping; `rating.evidence_event_ids` lets the backend reconstruct it from actions.

| Component | Calculation | Bound |
|---|---|---|
| Scoring | Goals × role weight (GK 1.3, DF 1.2, MF 1.0, FW 0.9) | +3.0 |
| Assists | Assists × role weight (GK .65, DF .8, MF .85, FW .75) | +1.8 |
| Creation | Non-assist key passes × .06 | +.6 |
| Passing | `1.2 × (completed − .75 × attempted) / max(attempted, 5)` | −.7 to +.3 |
| Hard passing | Hard completed passes × .025 | +.35 |
| Defence | `(.07 × interceptions + .03 × recoveries) × role multiplier` | +1.4 |
| Saves | Saves × .15 | +2.0 |
| Goals conceded | Keeper-only context debit: −.12 per conceded goal | −1.2 |
| Shooting | Non-goal shots on target × .05 | +.4 |
| Misses | Off-target shots × −.03 | −.3 |

Defence multipliers: GK .4, DF 1.2, MF 1.0, FW .7. Unknown role metadata uses MF weights as a fallback. All weights and caps are published in `player_rating_model` and defined in `simulator/ratings.py`.

The choices are deliberately inspectable and adjustable. In particular, a goalkeeper conceding a goal is **not proof of goalkeeper fault**. Passing's .75 reference is a heuristic anchor, not a researched league benchmark. Interceptions and recoveries may describe related aspects of the same sequence; both contributions and the defence cap are explicit.

### Eligibility and live ratings

- Require at least five unique attributable events, **or** a goal, assist, save, or keeper goal conceded.
- Otherwise `rating.value` is null and status is `insufficient_evidence`; render **NR** rather than a fabricated 6.0.
- `rating.provisional` is true until elapsed playing time reaches the match's defined duration. Even a final rating remains limited to the recorded event coverage.
- All roster players receive records, including quiet or unrated players.
- Ordinary received passes, raw speed, pressure observations, and team wins do not directly add rating points. This avoids rewarding activity volume or fast kicks without outcomes.
- Off-ball movement, running distance/speed, positioning, fouls, tackles, and errors leading to goals are not assessed because the present event model does not establish them sufficiently.

## UI/backend integration

Read player rows/cards from `summary.players`; group by `team_id`. Sort rated players by `rating.value`, placing NR rows separately. A reasonable card shows name/role, rating, goals/assists, passing accuracy, and top component contributions, with an expandable evidence list. Display the model label and heuristic qualification.

The Python `MatchStatistics` reducer automatically includes `players` and `player_rating_model` in live snapshots. For preloaded replay, `calculate_statistics(metadata, events, as_of=(period, time_ms))` returns only evidence available by that time. Rebuild after seeking backwards or applying corrected events. Do not display final-summary ratings before those events occur.

The existing frontend's JavaScript reducer does not yet implement player ratings. The frontend owner can port the published formula/definitions or consume shared Python snapshots from a backend. This change provides the data and integration contract; it does not change the teammate's board interface or the existing AI evidence whitelist.
