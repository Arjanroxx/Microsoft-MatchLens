# MatchLens completion checklist and local runbook

This supersedes the Azure preparation plan for the local portfolio edition. Azure signup is no longer a prerequisite. Historical Foundry documents describe a possible future deployment, not an implemented cloud integration.

## Core completion checklist

- [x] Seeded two-half synthetic matches with connected movement, passing, shots, speed, difficulty, and xG.
- [x] Team and player statistics, possession, ratings, substitutions, and the existing P1–P3 realism features.
- [x] Virtual pitch/replay, timelines, player inspection, and authoritative statistics at the replay cutoff.
- [x] Ordered event ingestion with sequence checks, duplicate detection, and persistent restart recovery.
- [x] Immutable source-prefix snapshots; rewinding never grants the agents future match facts.
- [x] Three real model roles: Analyst → Story → Experience using Microsoft Agent Framework and Ollama.
- [x] Read-only evidence tool, bounded tool calls, request deadline, one inference worker, and snapshot/profile-aware cache.
- [x] Source-backed shots, goals, dismissals, substitutions, offsides, player context, passing milestones, and rhythm/pressure comparisons when enough evidence exists.
- [x] Casual/analyst presentations, English/Hindi, favourite team/player, and xG/passing/pressure focus.
- [x] Catch-up, current-half and full-to-cutoff recaps; automatic boundary recaps when Auto insights is enabled.
- [x] Machine-readable timed insight envelopes, evidence receipts, stale-result rejection, and frontend integration guide.
- [x] Explicit real/demo/fallback states, model/token/latency traces, local SQLite audit history, and failure recovery.
- [x] Backend/frontend regression tests and repeatable real-model evaluation command.
- [x] Pinned SDK dependencies, Windows setup/run helpers, and a GitHub Actions configuration.

Verification records are generated under `data/generated/`, which is ignored by Git. A checked feature means code is implemented; see the validation section and current evaluation output for actual checks. GitHub Actions itself is only confirmed after a push/run on GitHub.

See [LOCAL-VALIDATION.md](LOCAL-VALIDATION.md) for the completed checks and measured local-model response times. For exact dependency reproduction, install `requirements-ai-lock.txt` instead of `requirements-ai.txt`.

## Setup on a teammate's laptop

1. Clone the repository and open its root in a terminal.
2. Install Python 3.12+ including pip. Install Node 22+ if running frontend tests.
3. Install/open Ollama from its official website. It serves the local model API on port 11434.
4. Run the commands below; PowerShell activation is unnecessary.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ai.txt
ollama pull qwen3:1.7b
.\.venv\Scripts\python.exe -m backend.app.server --provider ollama --port 8082
```

Alternative helpers: `.\scripts\setup-local.ps1`, then `.\scripts\run-local.ps1`. If your Python launcher differs, pass `-Python` to setup. Model download needs internet once; inference afterwards is local. Memory and response speed depend on hardware. On the development laptop, real responses took seconds to tens of seconds; this is not a broadcast latency guarantee.

Open **http://127.0.0.1:8082/**. Click **Goal** or select a shot, then **Explain this moment**. Confirm the provider is Ollama and the result says **AI-selected · evidence-rendered**. Expand the trace to see three completed model stages and the evidence-tool lookup. Switch to Analyst or Hindi and request again. Use **Build recap** for an interval summary.

Auto insights is off by default. Enabling it requests at most one story per 30 seconds of simulated match time, with boundary recap detection near period-end events. Accelerated playback can outrun a laptop model; pause at a moment for a reliable demonstration. A pending result must still match the replay context and display window.

## Generate and replay your own match

```powershell
.\.venv\Scripts\python.exe -m simulator.generate --seed 42 --output data/generated/portfolio-match-42
.\.venv\Scripts\python.exe -m backend.app.server --input data/generated/portfolio-match-42 --provider ollama --port 8082
```

Use a new output directory for each match you want to retain. Reusing a generator output path overwrites its match files. Generated fixtures are separate from the SQLite journal. Local imports can register a second source with the backend automatically; registration is validated and held in memory, with at most four registered matches.

## Exercise the live ingestion path

Start a fresh live match journal (or deliberately reuse one to resume):

```powershell
.\.venv\Scripts\python.exe -m backend.app.server --input data/examples/xg-match --provider ollama --live --port 8083 --database data/generated/live-xg.sqlite3
```

In a second terminal:

```powershell
.\.venv\Scripts\python.exe -m backend.app.replay_client --input data/examples/xg-match --url http://127.0.0.1:8083 --speed 30
```

Open port 8083. The board receives source events and can follow the stream. For an immediate integration test, use `--no-delay`. GET `/api/live?after_sequence=0` returns the acknowledged sequence; resume with `--after-sequence N`. Replaying from zero is also safe: exact duplicates are acknowledged without recounting. Conflicting duplicates, gaps, and backward clocks are rejected.

Live state is restored from the journal on restart. Use a different database if you change metadata under an existing match ID. In-memory registered replays must be reimported after restart. Event envelope/reducer checks run as events arrive; full cross-event physical validation runs when the match closes. The ingestion API is for this trusted simulator, not arbitrary third-party feeds.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\.venv\Scripts\python.exe -m unittest simulator.test_ui_server -v
node --test frontend/tests/*.test.mjs
.\.venv\Scripts\python.exe -m backend.app.evaluate --provider demo
.\.venv\Scripts\python.exe -m backend.app.evaluate --provider ollama --output data/generated/agent-evaluation-real.json
```

The real evaluation covers a shot, a key moment in analyst mode, Hindi, and a halftime recap. It fails if a stage falls back, facts cross snapshots, or cited events exceed the cutoff. This is a small functional evaluation, not an accuracy benchmark over real football. Run the simulator's broader tests when changing its physics or statistical rules.

## Portfolio handoff

- [ ] Review the code and UI, then commit/push the local-agent edition.
- [ ] Confirm GitHub Actions passes on the pushed revision.
- [ ] Record a short demo showing replay → evidence tool → personalised insight → recap → rewind.
- [ ] Add the demo link and repository to the resume/portfolio.

Suggested truthful resume wording: “Built a synthetic football analytics platform with an event-driven simulator, player/team metrics and xG, a replay dashboard, and a three-role local AI workflow using Microsoft Agent Framework and Ollama, with source-linked explanations and English/Hindi personalisation.”

## Optional future work

Video recognition, cloud hosting, production authentication, calibrated real-world xG, additional reviewed languages, retrieval from real historical football data, multi-user inference scheduling, and Azure Foundry adapters remain extensions. They are not silently represented as implemented. The current HTTP server is a loopback development application; do not expose it directly to the public internet.
