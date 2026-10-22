# Substitutions, participation, and evolving ratings

The complete current handoff and authoritative live rating API are in [UI-INTEGRATION.md](UI-INTEGRATION.md); schema 1.7 also permits changes at natural offside stoppages.

Schema **1.4** introduced a matchday squad and automatic substitutions to the existing connected simulation. It does not add a tactical configuration system. Offside is implemented in schema 1.7; remaining gaps are on the [realism checklist](MATCH-REALISM-CHECKLIST.md). Bookings and dismissals are now implemented in schema 1.6.

Schema **1.5** now uses natural ball-out/goal stoppages and includes added time. The former synthetic-break description below is retained only as a legacy-format note. See [RESTARTS-AND-CLOCK.md](RESTARTS-AND-CLOCK.md) for current execution, event fields and clock semantics.

## What happens in a match

- Each team has **11 starters and nine named substitutes** (40 player records in metadata). `is_starter` distinguishes the initial lineup from the bench.
- Most changes occur around the **60th–70th minute**: two players around minutes 60–64, then one around 66–69, queued for the next natural ball-out or goal stoppage (so a change can be delayed beyond minute 70). Short matches scale these times proportionally.
- A seeded 20% policy chance per team adds one half-time change. That percentage is our simulation choice, not an empirical claim about managers.
- Automatic changes exclude the goalkeeper. A replacement must have the same `position_group`: GK, full-back (FB), centre-back (CB), wide midfield (WM), central midfield (CM), winger (W), or striker (ST).
- Among starters with suitable unused bench cover, choose the lowest **current** rated outfield player. NR means unknown, not zero, so rated candidates are considered first. Ties use stable player IDs.
- An incoming player is not automatically substituted again by this simple policy. There are no injury substitutions yet.
- Preserve the outgoing player's formation slot. Player IDs never become formation indices; substitutes can wear shirts above 11.
- Maximum five substitutions per team, no return substitutions, maximum three in-play opportunities. A batch shares one `window_id`; half-time changes do not use an in-play opportunity. We use this selected competition configuration based on [IFAB Law 3](https://theifab.com/laws/latest/the-players/); not every competition uses identical limits.

## Legacy 1.4 event sequence and simplification

```text
completed action / period boundary
  → stoppage (reason: substitution_break)
  → substitution [one or more players, same window_id]
  → resume
  → next football action
```

A substitution never interrupts an in-flight ball or appears between a scoring shot and its linked goal record. In-play breaks consume 20 simulated clock seconds in a full match; short fixtures scale that duration. Half-time changes consume no playing-clock interval. Stoppage time is unassigned in possession statistics. In legacy 1.4, added time was not implemented.

These are explicit **synthetic referee-authorised substitution breaks**, not a full reproduction of natural stoppages and restart laws. The legacy 1.4 engine did not yet provide the throw-ins, corners, fouls, and goal kicks that would normally offer those opportunities. A player taking over the ball at a modelled resume is a control-state continuation, not a claim about a particular legal real-world restart. Replacements inherit the position at the break; walking off/on is not tracked.

## Selection uses live evidence

The engine feeds every resolved event into the same `PlayerStatistics` reducer used by reports. When a substitution is due, it evaluates a snapshot of only the events already emitted. It does not read end-of-match ratings.

The event's `selection` object contains the rating model, the departing player's rating at exit, eligible candidate ratings for that batch, and `evidence_up_to_sequence`. NR fallbacks are allowed only if there is no better rated compatible option. Incoming players are selected from unused compatible bench players, not given a pre-generated match rating.

## Player lifecycle

| State | Minutes and rating |
|---|---|
| `on_bench` | Zero minutes, no match actions, NR. |
| `on_pitch` | Minutes and event-based rating evolve with the playback clock/events. |
| `substituted_off` | Minutes stop at exit, statistics and rating stop changing; rating is finalised for that appearance. |
| `full_time` | Player still active at the final whistle; rating finalised. |
| `unused_substitute` | Remains zero minutes and NR after full time. |

Fields in `summary.players.<id>`:

- `is_starter`, `position_group`, `squad_status`.
- `entered_at_ms`, `left_at_ms`: absolute **monotonic match-clock** milliseconds (including added time in 1.5); null for unknown/not-applicable endpoints.
- `minutes_played_ms`: exact stint time, suitable for reconciliation; `minutes_played` is rounded for display.
- `rating.provisional` and `rating.finalised_at_ms`.

An outgoing player's existing counters are retained. Incoming players earn their own passes, goals, assists, saves, distributions, and rating using the same formula. Administrative substitution/resume records do not earn rating evidence or points. No per-90 extrapolation is used to artificially inflate a short cameo.

Without dismissals, team-player minutes sum to 11 × actual elapsed match time including added time. That invariant will deliberately change when dismissals or temporary absences are introduced.

## Frontend integration contract

### Initial setup

Do **not** draw every entry in `metadata.players`: metadata now contains the bench. Draw only players with `is_starter: true` at kickoff, with legacy files treating an absent flag as a starter.

### New event fields

`substitution` contains:

```text
team_id, period, period_time_ms, sequence
player_off_id, player_on_id
window_id, halftime
stoppage_event_id        # 1.5: originating natural stoppage
formation_slot, position_group
positions_after          # exactly 22 active positions after this swap
selection               # decision-time rating evidence
```

Use sequence to order multiple changes at the same timestamp. They are a single visual batch at a given playback time. Do not inspect future substitutions to hide a player early.

- Remove `player_off_id` from active markers; insert `player_on_id` with a new identity.
- Use `positions_after` immediately at that timestamp; do not interpolate toward a new lineup before the change.
- Display an off/on event card, names/shirts, minute, and optional rating-at-exit explanation.
- Preserve the outgoing player's card/history under the substituted group.
- Do not reset statistics for players who remain on the field.
- During `stoppage`, clear carrier highlighting and stop attributing possession. `resume` restores the specified controller, if any.
- For half-time and goal kickoffs, reset positions using the **current formation-slot map**, not the original starting IDs or shirt numbers.

The shared Python snapshot now includes `lineups.home/away` (`on_pitch`, `bench`, `substituted_off`) and `substitutions` history. `teams.<team>.substitutions` counts replacements, not opportunities; group history by `window_id` and exclude `halftime` to count in-play windows.

The existing JavaScript adapter now exposes `lineupsAt(match, time)` and returns it from `boardAt`. Kickoff and substitution anchors are compatible with schema 1.4. Board rendering already consumes active positions. A dedicated bench list, substitution panel, and live rating cards remain frontend-owner integration work. The JavaScript reducer still does not implement the Python rating model; use backend snapshots or a verified port. Never use final-summary ratings during an earlier replay.

### Rewind and import

Rebuild lineups, participation, and ratings from the event prefix when seeking backwards. A substitute disappears from the pitch before their entrance; an outgoing player reappears when rewinding to before exit. Keep stable IDs for history, selected-player panels, and assists.

New roster size is 40, but every normal action snapshot has **22 active players**, not 40. Existing 1.3/1.4 files remain supported. In 1.5 use `match_time_ms`, actual period offsets and the final whistle; nominal duration no longer finalises ratings. Recalculating an old summary will not invent a bench or substitution events; regenerate a new match for this feature.

## Generate a demonstration

```powershell
py -3.13 -m simulator.generate --seed 42 --output data/generated/substitutions-match-001
py -3.13 -m simulator.replay --input data/generated/substitutions-match-001 --speed 60
```

For a short checked-in example with a half-time substitution and later changes, load `data/examples/substitutions-match/metadata.json` and `events.jsonl` together in Replay Studio. It uses two five-minute halves and scaled substitution times.


## Schema 1.6 dismissals

Natural foul stoppages also offer substitution opportunities. Cards/dismissals are resolved before the manager chooses changes; a sent-off player cannot be replaced, and an emergency outfield keeper cannot be selected as an ordinary substitution. Team size stays reduced after every subsequent restart. Preserve `sent_off` history separately from the bench and `substituted_off`; see [DISCIPLINE-AND-SET-PIECES.md](DISCIPLINE-AND-SET-PIECES.md).
