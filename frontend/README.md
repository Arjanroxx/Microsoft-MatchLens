# MatchLens Replay Studio

An interactive, buildless HTML/CSS/JavaScript frontend for the MatchLens simulator. No npm install, framework, Azure account, or AI key is needed.

## Schema 1.5 and Priority 1

The adapter/main screen now supports ball-out/restarts, holds/parries/rebounds, natural substitutions and added time. See [the full UI contract](../docs/RESTARTS-AND-CLOCK.md). Load `data/examples/restarts-match/metadata.json` and `events.jsonl` together for a complete demonstration. The original default fixture is preserved.

Use `clockAt(match,time)` for the displayed match clock/period, `match.duration` for actual seeking, and actual period offsets for samples. New team comparison rows include throw-ins, goal kicks, corners, clearances, held/parried saves and rebound shots. A non-kickoff restart remains neutral until release. Administrative time-loss/release/placement records stay out of the main feed; their evidence remains available. Dedicated restart/added-time/bench/rating panels are optional UI-owner presentation work.

## Run locally

From the repository root:

```bash
python -m http.server 8080
```

Open **http://localhost:8080/frontend/**. On Windows, `py -3.13 -m http.server 8080` works too. Serve over HTTP; opening index.html directly cannot load ES modules and sample data reliably.

## What works

- One shared clock for play/pause, seek, ±10 seconds, restart, next action and 1×–60× replay.
- Fixed-coordinate pitch; home/away player markers, shirt numbers, optional names and clickable player details.
- Ball interpolation through exact trajectory samples; smooth illustrative player motion between kick, arrival and recovery anchors; recent completed action trails and dashed intended paths after interceptions.
- Amber gradient possession halo that clears during flight and transfers on completed passes/recoveries. Smooth toggle, reduced-motion support, pitch gradients and phase-aware trail resets.
- Score and team statistics from completed events, rebuilt on seek. Goal events count once. No final score or final-summary leakage.
- Event feed with key-moment/pass filters, event-to-pitch navigation, geometry/speed evidence and raw source fields.
- Template-based “Catch me up” for the last 60 match seconds, with source event IDs. No LLM calls.
- Import metadata.json and events.jsonl together, processed in browser memory. No files are uploaded.
- Responsive layout, keyboard-accessible players, dialogs, Space play/pause, arrow-key seek and visible focus states.

The included sample is copied from `data/examples/short-match/` at commit c7424f66ee4ece6a85db85184cbd9586a6964a34. Neither `summary.json` nor `evaluation-only.json` is loaded.

## Use a newly generated match

```bash
python -m simulator.generate --seed 123 --minutes-per-half 5 --output data/generated/my-match
```

Click **Load a match**, and select **metadata.json and events.jsonl together** from that directory. You can also replace frontend/data/metadata.json and frontend/data/events.jsonl to change the default fixture. Imports are limited to 60 MB combined; full-length matches may need a streaming backend later.

## Architecture and integration

- `model.mjs`: parsing/normalisation boundary, deduplication, playback state and event-prefix statistics. Independent of the DOM and transport.
- `app.mjs`: clock, SVG renderer, UI interactions, local fixture/import adapter, evidence and recap templates.
- `styles.css`: responsive broadcast-style layout; lime home and lilac away identity.
- `index.html`: semantic controls, pitch and panels.
- `tests/`: timing, deduplication, score, event labels and application startup/interaction smoke tests.

For a backend, replace `load()` with a fetch to your match endpoints while retaining `prepare(metadata, events)`. Do not expose API keys to the browser. Current `prepare` expects a complete preloaded replay; true live streaming requires a delayed clock or kick/trajectory/completion observation messages, as documented in `docs/UI-INTEGRATION.md`.

The JS reducer follows `simulator/statistics.py`. Possession uses `team_phase_time_v1`: excludes shot flights and unassigned gaps; denominator is the sum of assigned home/away phase time. Schema 1.5 release events clear shot/clearance/parry possession immediately; legacy shots without a release record remain provisional until completion. Empty metrics display a dash. Pass speed is whole-flight mean; shot initial speed is separately labelled. Metric means are event-weighted.

To add Foundry, send computed evidence from a backend to the model; attach verified event references and an `as_of` clock to returned insights. Refuse future insights when replaying an earlier time. The current recap is a factual template, not an AI integration.

The pitch interpolates player positions between exact state anchors for presentation only. Kickoff resets for schema 1.3 mirror `PitchState.FORMATION` and engine restart handling; unsupported schemas wait for an observed snapshot. Arrival anchors update the actual receiver/interceptor or saving keeper; recovery anchors place the named recoverer at the recorded ball location. The carrier stays at the ball between actions, as in the engine. Disable **Smooth** to hold player states. No interpolation changes event order, timestamps, trajectories, outcomes or statistics. Position interpolation uses future anchors from a preloaded replay and is not measured tracking or a true-live renderer. Outcomes and carrier highlights remain withheld until their event time. Ball motion always interpolates recorded samples linearly, without easing or resampling the football physics.

## Verify

Node 18+ is required only for tests:

```bash
node --test frontend/tests/replay.test.mjs frontend/tests/startup.test.mjs frontend/tests/substitutions.test.mjs frontend/tests/restarts.test.mjs
node --check frontend/app.mjs
```

During development the JS statistics were compared against Python’s reference reducer at 294 action/clock boundaries, including completion-minus-one-millisecond, half-time and full time. Counts, possession times, means and percentages matched (within rounding tolerance). Browser visual QA was unavailable in the build environment.

## Design

Editable Canva UI concept: https://canva.link/v7vphmg7sg30of0

The functional application is implemented in HTML/CSS/JS. Canva is an editable visual concept accompanying that implementation. Fonts use Google Fonts with local system fallbacks. No external JavaScript/CDN dependencies.

## Smoother replay update

Schema 1.4 compatibility: `model.mjs` now understands starting lineups, substitution anchors, formation-slot inheritance, stoppage/resume possession, and rewinds through lineup changes. Metadata can contain 40 players; only 22 active markers are rendered. `lineupsAt(match,time)` exposes bench and substituted-off IDs. See `docs/SUBSTITUTIONS.md` for the frontend handoff. The included original frontend fixture remains schema 1.3; load `data/examples/substitutions-match/metadata.json` and `events.jsonl` together to exercise the new flow. Dedicated bench/substitution panels and Python-equivalent live player ratings remain frontend integration work.

Default replay speed is now 4×. The amber player highlight means established ball control; while the ball travels, no intended receiver is marked as the carrier. At a simulator kickoff, old phase trails are cleared and positions reset at the recorded restart timestamp. Goal and halftime resets are not blended early. The pitch glow follows the team in control or taking the current action.

Validation for this update: 6,881 sample assertions covering snapshot anchors, ball samples, carrier timing, recoveries, goal timing and unchanged event order; startup/interaction smoke checks executed in an isolated JavaScript runtime. Browser visual QA and hosted preview publication were unavailable because the build environment was offline. The existing hosted preview remains on the prior version until a build environment can publish this branch.
