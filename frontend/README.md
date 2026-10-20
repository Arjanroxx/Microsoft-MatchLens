# MatchLens Replay Studio

An interactive, buildless HTML/CSS/JavaScript frontend for the MatchLens simulator. No npm install, framework, Azure account, or AI key is needed.

## Run locally

From the repository root:

```bash
python -m http.server 8080
```

Open **http://localhost:8080/frontend/**. On Windows, `py -3.13 -m http.server 8080` works too. Serve over HTTP; opening index.html directly cannot load ES modules and sample data reliably.

## What works

- One shared clock for play/pause, seek, ±10 seconds, restart, next action and 1×–60× replay.
- Fixed-coordinate pitch; home/away player markers, shirt numbers, optional names and clickable player details.
- Ball interpolation between trajectory samples, kick-time player snapshots, recent completed action trails, dashed intended paths after interceptions.
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

The JS reducer follows `simulator/statistics.py`. Possession uses `team_phase_time_v1`: excludes shot flights and unassigned gaps; denominator is the sum of assigned home/away phase time. While a shot is unresolved it provisionally extends the last known possession, consistent with the Python reducer. Empty metrics display a dash. Pass speed is whole-flight mean; shot initial speed is separately labelled. Metric means are event-weighted.

To add Foundry, send computed evidence from a backend to the model; attach verified event references and an `as_of` clock to returned insights. Refuse future insights when replaying an earlier time. The current recap is a factual template, not an AI integration.

The pitch keeps kick-time player snapshots rather than inventing full movement tracks; it updates the receiver/interceptor on completion. Player movement between kicks is intentionally not interpolated. Ball movement is sampled-data interpolation. The simulator is a simplified uncalibrated 2D model, not professional tracking.

## Verify

Node 18+ is required only for tests:

```bash
node --test frontend/tests/replay.test.mjs frontend/tests/startup.test.mjs
node --check frontend/app.mjs
```

During development the JS statistics were compared against Python’s reference reducer at 294 action/clock boundaries, including completion-minus-one-millisecond, half-time and full time. Counts, possession times, means and percentages matched (within rounding tolerance). Browser visual QA was unavailable in the build environment.

## Design

Editable Canva UI concept: https://canva.link/v7vphmg7sg30of0

The functional application is implemented in HTML/CSS/JS. Canva is an editable visual concept accompanying that implementation. Fonts use Google Fonts with local system fallbacks. No external JavaScript/CDN dependencies.
