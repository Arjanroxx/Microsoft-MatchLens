# Microsoft × Premier League Hackathon: Four-Person Project Guide

Prepared: 20 October 2026. Planning timezone: Asia/Kolkata (IST).

Stack audit updated: 20 October 2026, against Microsoft's official rules and resource playlists. See Section 3A for complete technology coverage and recommended implementation choices.

## 1. Idea

Build **MatchLens**, a live football companion that turns synthetic match events into evidence-backed explanations, synchronised overlays, and personalised recaps.

The central demonstration: **one passage of play becomes a simple explanation for a casual fan, a tactical explanation for an analyst, and a relevant player story for someone following their favourite player. Every factual claim has inspectable evidence.**

Use Python/FastAPI for event processing and deterministic analytics, React/TypeScript for the viewing experience, a Microsoft Foundry model deployment for narration, and Docker Compose for reproducible local development. Deploy to Azure Container Apps (ACA) when the local application is reliable. Use DuckDB for analytical queries over event snapshots; keep live state updates in straightforward Python code.

Deliver one complete five-stage pipeline before attempting computer vision or extensive infrastructure.

## 2. Sources, confidence, and urgent logistics

This report consolidates the earlier project guide with the user-supplied Gemini analysis of the video [Build AI-powered soccer insights apps with AKS and ACA](https://www.youtube.com/watch?v=EQ187ohgCbo). The video itself and its transcript were not independently accessible during this work. Video timestamps and implementation details below are therefore **reported by the supplied analysis**, not independently verified observations.

The [official Microsoft Reactor series page](https://developer.microsoft.com/en-us/reactor/series/S-1709/) confirms the synthetic-event, explainable-match-intelligence theme and lists Brian Benz's session on 14 October 2026. The subsequent stack audit also located Microsoft's [official rules](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md) and [resource playlists](https://github.com/microsoft/insidethegamehackathon/blob/main/RESOURCE%20PLAYLISTS.md). These take precedence over the supplied video analysis.

### Check immediately

| Item | Reported in the supplied video analysis | Action |
|---|---|---|
| Registration | Official rules now checked: 20 October 2026, noon Pacific | **21 October 2026, 00:30 IST.** Register through the official portal before this time. |
| Hackathon period | Official rules now checked: 6–27 October 2026; closes 11:59 PM Pacific | Submission closes **28 October 2026, 12:29 PM IST**. |
| Prizes | Up to $50,000 total; six winning projects | Verify eligibility and prize terms. |
| Azure credits | No event-specific free credits | Plan for paid usage unless organisers or your account confirm otherwise. |
| Registration portal | [Link supplied by the analysis](https://aka.ms/AA13ltgi) | Shortlink destination could not be independently checked here. |
| Reference application | [Football Results Dashboard link supplied by the analysis](https://aka.ms/football-results-dashboard) | Inspect the repository, licence, and instructions before reusing code. |

Do not treat suggestions in a presentation as exemptions from competition rules. In particular, publicly available historical data is not automatically an acceptable replacement for required synthetic events.

Deadline conversions use Pacific daylight time applicable on these October dates. Source: [official rules, Section 1](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md).

## 3. What the video analysis changes in the plan

The reported reference application answers questions over historical football results. Your challenge needs event-level, live match intelligence. Reuse its engineering patterns, then extend the data and audience experience.

| Reported lesson | How MatchLens should apply it |
|---|---|
| Plan → Compute → Narrate → Verify, approximately 12:41–14:27 | Use deterministic tools and evidence packets; validate narrative claims before rendering. |
| Grounding receipts, approximately 39:15–40:30 | Show source event IDs, metric definitions, checked claims, latency, and generation status. |
| Explicit out-of-scope behaviour, approximately 28:57–29:13 | Reject questions requiring unavailable historical, tracking, or tactical data. |
| OpenTelemetry trace inspector, approximately 29:34 | Provide a simple technical drawer showing processing stages and durations. |
| Shared containers across Compose, ACA, and AKS | Package consistently; actually deploy only the environment you need. |
| Local-first development, approximately 57:50–57:56 | Rehearse locally and minimise cloud runtime and model calls. |
| Detailed specification before generation, approximately 43:46–44:51 | Write a concise shared specification and contracts before using coding assistants. |
| Historical entity reconciliation, approximately 27:07–27:37 | Use stable player/team IDs, roster metadata, and explicit aliases. |

The analysis names particular runtime and coding-assistant models. Those names, access claims, context sizes, and capabilities were not independently verified. Choose from models actually available in your account, based on measured latency, quality, schema support, and cost. You do not need the presenter's exact models.

Likewise, reported reference-app limits—six tool calls, 1,200 output tokens, and a 45-second answer timeout—are descriptive examples. A live overlay needs much tighter timing than a historical analytics answer.

## 3A. Complete stack audit: organiser technologies, video stack, and our choices

### What the audit found

The earlier guide described a workable core architecture, but it did not explicitly map every organiser-named technology. In particular, Agent Framework, Azure MCP, Copilot Agent Mode, GitHub SDK/CLI, and a concrete Fabric integration needed coverage.

The rules evaluate technology fit and highlight Microsoft Foundry, Agent Framework, Azure MCP, GitHub Copilot Agent Mode, Fabric, GitHub SDK, GitHub CLI, Azure Apps and AI Services, and Azure databases. They do not explicitly require every listed product in every entry. Agentic design is a scored criterion. [Official rules, Section 6](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md).

The following implementation decisions are **our recommendations**, not additional organiser mandates. “Covered” means specified in this plan; it does not mean a service has been provisioned or integrated.

### Organiser technology coverage

| Technology | Recommended MatchLens role | Implementation decision and proof |
|---|---|---|
| GitHub | Source repository, issues, review, release | Use throughout development; document setup and architecture. |
| GitHub Copilot Agent Mode | Assist implementation of bounded issues | Use where account access permits; retain reviewed changes and test results. Development tooling, not runtime narration. |
| Microsoft Foundry | Model deployment and AI lifecycle | Use for narration; record deployment configuration, evaluation results, and failure behaviour. |
| Foundry Agents | Managed agent alternative | Consider if managed execution is useful; avoid duplicating a local agent runtime without a reason. Included in organiser learning resources. |
| Microsoft Agent Framework | Coordinate evidence tools and narration workflow | Recommended bounded workflow: collect evidence → narrate → deterministic verify → publish/fallback. Framework installation/version must follow current documentation. |
| Azure MCP | Assist authorised Azure resource discovery and operational setup | Optional development integration; keep read-only initially. Do not confuse Azure management tools with football analytics tools. |
| Microsoft Fabric | Secondary analytical history and replay evaluation | Recommended broader-stack extension: archive synthetic events/accepted insights to a Lakehouse; compare detector results across replay seeds. Keep it outside the critical live path initially. |
| GitHub SDK | Optional programmatic repository integration | Useful only for a concrete feature such as exporting a reproducible evaluation issue. Omit if ordinary GitHub/CLI workflows suffice; record rationale. |
| GitHub CLI | Repository and pull-request workflow | Recommended laptop tool; use for repository access, review, and release operations. |
| Azure Apps / Azure Container Apps | Host the containerised application | Recommended deployment; demonstrate health checks, recovery, and measured latency. |
| Azure AI Services | Additional language/audio capability where valuable | Choose Azure AI Translator or Speech if implementing that feature. Describe exactly which service is used; model-generated multilingual text alone is not a separate Translator integration. |
| Azure databases | Durable match/evidence records | Optional Azure Database for PostgreSQL path when shared persistence is needed. Keep DuckDB for local analytics; do not claim DuckDB is an Azure database service. |
| AKS | Alternative hosting for Kubernetes-specific needs | Document as an alternative; deploy only if cluster control materially benefits the project. |
| Azure Functions | Alternative event-triggered processing | Possible archival or recap trigger; unnecessary if the backend already handles the workload reliably. |
| Azure Logic Apps | Optional downstream automation | Possible editorial approval/recap delivery workflow; avoid adding external publishing to the core demo. |
| A2A / another supported orchestration approach | Optional interoperability between specialised agents | Consider only for a purposeful multi-agent design; ordinary sequential function calls should not be labelled multi-agent collaboration. |

The last cloud/orchestration options are also relevant to category selection; inspect the full category descriptions before choosing a prize target. [Official rules, Section 4.2](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md).

Official [resource playlists](https://github.com/microsoft/insidethegamehackathon/blob/main/RESOURCE%20PLAYLISTS.md) cover Copilot, Foundry, Foundry Agents, agentic workflows, and data. Assign Copilot to all developers, Foundry/agents/workflows to the AI lead, and data to the statistics lead.

### Full reference-video stack coverage

This inventory comes from the supplied Gemini analysis; its reported implementation remains unverified against the video itself.

| Reported component | MatchLens treatment |
|---|---|
| Python | Backend, generator, deterministic tools. |
| DuckDB | Local analytical snapshots and evaluation queries. |
| Azure Blob Storage | Optional dataset snapshots and replay artefacts. |
| Microsoft Foundry and hosted model | Narration with schema constraints and evidence validation. |
| GitHub Copilot and named coding models | Use available licensed assistants; exact reported models are not prerequisites. |
| Docker Compose | Reproducible local services. |
| ACA and AKS | ACA deployment; AKS documented alternative. |
| Bicep | Recommended repeatable Azure infrastructure definition after a successful manual prototype. |
| Kubernetes YAML | Only for an actual AKS deployment. |
| PowerShell/Bash | Setup and deployment scripts; PowerShell is enough for the Windows baseline. |
| OpenTelemetry | Trace ingestion, detection, generation, verification, scheduling. |
| Application Insights and Log Analytics | Optional Azure trace/log destination with retention and cost limits. |
| Microsoft Entra ID and managed identities | Prefer supported service authentication; confirm each resource's permissions. |
| Federated workload identity | AKS-specific identity option if choosing that deployment. |
| User-assigned managed identity | ACA identity option if a reusable identity is useful. |
| NSGs and IP allow-listing | Deployment-specific network controls; ensure authorised judging access remains possible. |

React, TypeScript, FastAPI, Vite, NumPy, Pydantic, pytest, HTTPX, and SSE/WebSockets are our implementation choices. They were not established as mandatory organiser technologies by this audit.

### A practical implementation sequence

**Baseline:** GitHub + Copilot-assisted development + Python/FastAPI + DuckDB + React + Docker Compose + Foundry inference + ACA. Include evidence validation and basic traces.

**Recommended competition-oriented extension:** add a bounded Agent Framework workflow, Bicep, managed identity, and Application Insights. Add a small useful Fabric history/evaluation path if capacity and time permit. This makes agentic design and Microsoft integration visible without turning every component into a separate agent.

**Broader ecosystem demonstration:** add one well-scoped Azure AI language/audio service and durable Azure database persistence only when the user journey benefits. Use Azure MCP and GitHub CLI as development tools and explain that distinction. GitHub SDK, AKS, Functions, Logic Apps, and A2A remain alternatives or targeted extensions.

Do not claim the project “uses the entire Microsoft stack” unless each claimed integration actually runs. Maintain `docs/technology-evidence.md` with technology, role, owner, setup, evidence/test, and status (planned/working/deferred). Service logos and unused imports are not integration evidence.

### Additional access and setup checklist

- GitHub account, repository permissions, Copilot access if using it, and optionally GitHub CLI: `winget install --exact --id GitHub.cli`.
- Foundry deployment and an approved authentication method; verify from the backend.
- Agent Framework package/runtime chosen from current official documentation; first test a single tool-enabled workflow.
- Azure MCP only from its official distribution, with deliberately scoped credentials; do not install an arbitrary similarly named package.
- Fabric workspace and suitable capacity/access; browser service access is distinct from installing Python packages.
- Translator/Speech resource only for the feature you selected; check region, limits, credentials, and supported languages.
- Azure database only if selected; agree schema, authentication, migration, and recovery ownership.
- Bicep tooling through the Azure CLI/VS Code when writing infrastructure; no local Kubernetes requirement for ACA.

This is a planning audit, not a test of these services. Consult current official product documentation before adding new dependencies or provisioning resources.

## 4. Product scope and user journey

The interface should have three areas:

1. **Match view:** synthetic pitch animation or permitted, correctly aligned video; score; clock; timed overlay cards.
2. **Viewer preferences:** casual/analyst mode, language, favourite club, favourite player, insight frequency.
3. **Evidence and recap:** key moments, supporting metrics, definitions, and automatic half-time/full-time summaries.

Example journey:

1. A synthetic event stream records three attacking-third recoveries in five match minutes.
2. Two recoveries are followed by shots within ten seconds.
3. A detector produces a structured evidence packet.
4. A casual viewer sees: “Their pressure is turning possession wins into shooting opportunities.”
5. An analyst sees the counts, time window, comparison where available, and event references.
6. A viewer following a particular player sees that player's contribution when supported by evidence.
7. The key moment later appears in the personalised recap.

### Scope priority

| Essential first version | Stretch features |
|---|---|
| Synthetic event replay, validation, and live statistics | Automatic video event extraction |
| Three explainable pattern detectors | Video-based player identification |
| Casual and analyst experiences | Calibrated speed from tracking/video |
| Favourite club and player filtering | Speech narration |
| Two reviewed languages | More languages and concurrent matches |
| Timed, machine-readable overlays | Advanced tactical or predictive models |
| Evidence receipts and automatic recap | Natural-language analytical Q&A |
| Local deployment and failure fallback | Complex cloud scaling |

Confirm whether speed or auto-eventing is mandatory in the actual rubric before classifying it as stretch work.

## 5. Team responsibilities

Assign according to strengths; the user need not personally own integration.

| Owner | Responsibilities | First deliverable | Final responsibility |
|---|---|---|---|
| Product/integration lead | Scope, contracts, integration, deployment | Shared spec and application skeleton | Acceptance checks, submission, pitch |
| Data/statistics lead | Synthetic generator, ingestion, state, metrics | Replayable events and correct counters | Detectors, data quality, evaluation |
| AI/explainability lead | Evidence contracts, narration, multilingual output | One grounded insight in two modes | Verification, fallback, recap |
| Interface/rendering lead | Match screen, preferences, overlays | Sample insight displayed on screen | Synchronisation, accessibility, polish |

Use one repository, short branches, and frequent small merges. Agree contracts before splitting implementation. Integrate a visible end-to-end increment every few hours. Every task needs an observable completion condition.

Reserve roughly the final quarter of your time for reliability, documentation, and demonstration. Four disconnected components are not a working product.

## 6. Before coding: confirm rules and write a specification

Record the official submission deadline/timezone, judging weights, permitted team size, required Microsoft services, dataset rules, rendering-partner requirements, IP/licensing rules, required deliverables, and whether pre-event scaffolding is allowed.

Write `docs/spec.md` covering:

- Product promise and three example audience experiences.
- Minimum scope and explicit stretch features.
- Service boundaries and API contracts.
- Event, evidence, insight, and overlay schemas.
- Metric definitions, detector thresholds, and missing-data policy.
- AI tools, validation, timeouts, and fallback.
- Playback synchronisation and late-arrival policy.
- Tests, acceptance criteria, deployment, and demo script.

A useful specification need not be 500 lines. Spend enough time to eliminate ambiguity, then validate the design with one working event-to-screen path. Use coding assistants for bounded tasks with explicit tests; review generated calculations, authentication, dependencies, and infrastructure. Check the reference repository's licence before copying code and preserve required notices.

## 7. Laptop prerequisites

Recommended setup: Windows, approximately 16 GB RAM, sufficient disk space for dependencies and optional container images, reliable internet for hosted inference. A dedicated GPU is unnecessary for the synthetic-event MVP.

| Tool | Purpose | Requirement |
|---|---|---|
| VS Code | Development and debugging | Essential |
| Git and shared GitHub repository | Collaboration and versioning | Essential |
| Python 3.13 | Backend, simulation, analytics | Essential |
| Node.js 24, latest available patch | Frontend tooling | Essential; agree one major version |
| Edge/Chrome | Viewer and browser debugging | Essential |
| Azure CLI | Authentication/deployment | For cloud deployment |
| Docker Desktop with Compose | Repeatable multi-service local run | Recommended after the first local path works |
| GitHub Copilot, including Agent Mode | Implementation assistance and organiser stack alignment | Recommended; needs account access |
| GitHub CLI | Repository/review/release workflow | Recommended; see Section 3A |
| Microsoft Agent Framework | Bounded runtime workflow | Recommended extension; see Section 3A |
| OBS Studio | Demo recording/browser overlays | Optional |
| API client | Manual endpoint checks | Optional; FastAPI provides API documentation |

Node 24 is an LTS line; use an agreed compatible runtime across the team. See the [Node release schedule](https://github.com/nodejs/Release) and [Vite setup requirements](https://vite.dev/guide/).

### Windows installation

Run only for tools you need; these are setup instructions, not installations performed by this report.

```powershell
winget install --exact --id Microsoft.VisualStudioCode
winget install --exact --id Git.Git
winget install --exact --id Python.Python.3.13
winget install --exact --id OpenJS.NodeJS.LTS
winget install --exact --id Microsoft.AzureCLI
```

The Node LTS package follows the current LTS channel. Check that the resulting major version matches the team's choice. Close and reopen terminals after installation.

```powershell
git --version
py -3.13 --version
node --version
npm --version
az version
```

For Docker Desktop, follow its current Windows prerequisites, including supported virtualisation/WSL configuration and applicable licence terms. Do not spend the first several hours troubleshooting containers if native Python and Node already let you build the first pipeline.

Official installation references: [Python downloads](https://www.python.org/downloads/), [Azure CLI on Windows](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows?view=azure-cli-latest), [Docker Desktop Windows installation](https://docs.docker.com/desktop/setup/install/windows-install/).

## 8. Repository and local setup

```text
matchlens/
  backend/
    app/
      main.py
      ingestion.py
      state.py
      metrics.py
      detectors.py
      tools.py
      narratives.py
      verification.py
      recaps.py
    tests/
    requirements.txt
    Dockerfile
  frontend/
    Dockerfile
  simulator/
  shared/
    event.schema.json
    evidence.schema.json
    insight.schema.json
    overlay.schema.json
  data/
    scenarios/
  docs/
    spec.md
    architecture.md
    metric-definitions.md
    data-and-attribution.md
    demo-script.md
  infra/
  compose.yaml
  .env.example
  .gitignore
  README.md
```

From the repository root:

```powershell
mkdir backend
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install "fastapi[standard]" pydantic numpy duckdb openai python-dotenv pytest httpx
.\.venv\Scripts\python.exe -m pip freeze > requirements.txt
```

From the root in another terminal:

```powershell
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm run dev
```

Commit the dependency lockfile and Python dependency file. Add `.env`, `.venv/`, `node_modules/`, `dist/`, `__pycache__/`, and `.pytest_cache/` to `.gitignore`.

Only install packages for features being implemented. Add OpenTelemetry dependencies after the core flow works. See [FastAPI first steps](https://fastapi.tiangolo.com/tutorial/first-steps/).

## 9. Azure access, deployment, and cost

Prove model access early:

1. Confirm the correct subscription and permissions.
2. Create or select a Microsoft Foundry project and available model deployment.
3. Send one realistic evidence packet from the backend.
4. Verify structured output support, latency, limits, and cost.
5. Retain a deterministic fallback if hosted inference is unavailable.

Use the current supported SDK/API instructions for your deployed endpoint. Avoid copying an old preview SDK merely because a tutorial uses it. Store deployment names and credentials in backend configuration; never in browser code or Git.

### Local and cloud topology

Use three logical workloads inspired by the reported reference app:

- **web:** browser application; optionally served by the API in the simplest deployment.
- **insights:** event API, match state, metrics, detectors, AI orchestration, verification.
- **simulator/ingest:** prepare a reproducible synthetic dataset, then replay it into ingestion.

The reference ingest is reportedly a one-off historical curation job. Your simulator is different: it emits timed live events. Separate dataset generation from replay even if they share one code package.

After creating the Compose file and Dockerfiles, document a single command such as `docker compose up --build`. Initially use one backend process and one replica because in-memory state is process-local. Multiple workers or replicas need shared state, consistent event distribution, and recovery logic.

Choose **ACA** for a straightforward containerised hackathon deployment. Use **AKS** only if Kubernetes control is part of your actual project or the team already has the expertise. Do not build two deployment paths merely to reproduce the presentation. See [ACA overview](https://learn.microsoft.com/en-us/azure/container-apps/overview).

Cloud additions should solve a real need: Blob Storage for datasets, Application Insights for traces, and managed identity for supported service authentication. Section 3A provides explicit coverage of all organiser-named technologies and a staged integration plan. Prioritise a bounded agent workflow and meaningful Microsoft integrations; add Fabric and database persistence with a defined purpose. Event Hubs remains an optional scaling choice rather than part of the minimum local design.

Set a team spending limit and Azure budget alerts. Alerts are not a hard spending cap. Limit model calls and output size, cache equivalent narratives, run locally where possible, and stop unneeded resources after submission. Label estimated model cost as an estimate based on your deployment's actual pricing; it does not represent the whole Azure bill.

## 10. Five-stage pipeline and trust boundary

```text
Generate/replay synthetic events
  → Validate, deduplicate, order
  → Update match state and deterministic statistics
  → Detect meaningful patterns
  → Build evidence packet
  → Generate audience-specific narrative
  → Verify claims and schema
  → Schedule/render overlay
  → Store accepted key moments for recap
```

Viewer preferences affect story selection, detail, language, and frequency. They must not alter underlying match facts.

The guiding rule: **code computes the facts; AI explains those facts.**

Use SSE or WebSockets to deliver live updates. SSE suits primarily server-to-viewer updates, with ordinary HTTP requests for preferences. Test streaming through the actual deployed ingress, including buffering, heartbeat, timeout, and reconnect behaviour. See [SSE explanation](https://learn.microsoft.com/en-us/azure/application-gateway/for-containers/server-sent-events).

## 11. Event schema and ingestion

Agree this contract before independent implementation. Example:

```json
{
  "schema_version": "1.0",
  "match_id": "demo-001",
  "event_id": "evt-0128",
  "sequence": 128,
  "period": 1,
  "period_time_ms": 923000,
  "type": "pass",
  "team_id": "home",
  "player_id": "home-08",
  "recipient_id": "home-11",
  "possession_id": "pos-043",
  "start": {"x_m": 42.0, "y_m": 30.0},
  "end": {"x_m": 65.0, "y_m": 18.0},
  "outcome": "complete",
  "pressure": {"under_pressure": true, "nearest_defender_m": 1.7},
  "source": "synthetic"
}
```

Define pitch dimensions, origin, units, attacking directions by period, timestamp semantics, stoppage time, required fields per event, missing values, correction events, and the match/video clock mapping. Separate roster metadata from events and join using stable IDs.

Initially support passes, shots, tackles, recoveries, turnovers, pressure events, goals, and period boundaries. Add tracking samples only when implementing metrics that require them.

Ingestion must validate schemas, suppress duplicates, order events, apply a documented late-arrival policy, log rejections, and allow deterministic replay. Corrections should supersede earlier events and trigger recalculation of affected statistics and insights.

Do not confuse server receipt time with match event time. Keep both for diagnostics.

## 12. Synthetic data with realistic continuity

Generate connected possessions rather than independent random actions:

```text
Restart → Build-up → Progression → Final-third action
                                      ↓
                             Shot / Turnover / Foul
                                      ↓
                               Next possession
```

Preserve possession ownership, plausible locations, valid recipients, ball continuity, available players, score consistency, and appropriate restarts. Define what happens to possession during loose-ball situations.

Use fixed seeds and include scenarios for:

- Slow possession without progression.
- Repeated high recoveries leading to shots.
- Frequent turnovers and shorter possessions.
- Favourite-player involvement.
- A quiet interval that should produce no insight.
- Goals, substitutions, half-time, and direction changes.
- Duplicate, delayed, malformed, and corrected events.

Reserve unseen seeds for evaluation. Do not let the detector read the generator's scenario label; it must infer the pattern from events. Separately validate data plausibility and detector correctness to avoid circular evaluation.

Prefer clearly synthetic clubs/players unless authorised real identities are useful. A licensed public dataset does not automatically satisfy a synthetic-data requirement. Publish a Data & Attribution page describing generation, seeds, assumptions, provenance, and licences.

The reference app reportedly excludes raw external CSVs from Git. That is a project choice, not a universal licence rule. Commit only data you have rights and permission to distribute; small original synthetic fixtures may be appropriate. Never commit credentials.

Use a synthetic pitch animation if you lack correctly aligned, permitted footage. Unrelated real footage with invented events is not a credible synchronised demonstration.

## 13. Metrics: definitions and limitations

Implementation update: schema 1.3 uses persistent player positions, actual teammate pass targets, geometry-based pass resolution, and kick-time snapshots. The default match varies each team's behaviour at intervals and temporarily increases pressing after conceding. Pass difficulty is derived from intended pass geometry and defender positions; ball and shot speeds are calculated from the resulting trajectories. See `simulator/README.md` for formulas, timing, assumptions, and run commands. These remain simplified synthetic observations and an uncalibrated heuristic. Continuous player tracking and video auto-eventing remain unimplemented.

| Metric | Implementation | Important limit |
|---|---|---|
| Pass accuracy | Completed ÷ attempted passes | Handle zero attempts and define exclusions. |
| Pass distance | Euclidean distance in pitch metres | Requires consistent coordinates. |
| Progressive passes | Documented forward-progress threshold | Normalise attacking direction. |
| Final-third entries | Defined boundary-crossing actions or possessions | Prevent accidental repeated counting. |
| High recoveries | Possession regained in a defined attacking zone | Publish the zone definition. |
| Shots after recovery | Shot within a defined interval after recovery | Sequence is not proof of causation. |
| Player involvement | Listed action types in a time window | It is not all off-ball activity. |
| Possession share | Time attributed to each team | Event counts alone do not establish time share. |
| Pass difficulty | Transparent weighted heuristic | Not a calibrated completion probability. |
| Speed/distance travelled | Suitable time-stamped tracking | Sparse action locations are insufficient. |

For a first pass-difficulty score, combine documented weights for distance, pressure, and direction; show the definition. Calibrating against outcomes from your own generator alone does not establish real-world predictive validity.

Ball speed requires displacement and elapsed time over suitable observations. Pass endpoints alone do not establish shot launch speed. Player tagging from known synthetic player IDs is feasible; identifying people in video is a separate problem. Display unavailable when required evidence is absent.

Do not label a heuristic as professional xG or xT. If you add such models, document training/reference data, assumptions, evaluation, and synthetic-domain limitations.

## 14. Three initial pattern detectors

These are proposed configurable hackathon heuristics, not established tactical models.

| Detector | Example rule | Defensible explanation |
|---|---|---|
| Pressure creating opportunities | At least three attacking-third recoveries in five minutes; at least two followed by shots within ten seconds | Pressure is producing possession wins followed by shooting opportunities. |
| Possession without progression | High measured possession share, few final-third entries, few shots over a defined interval | The team is keeping the ball but generating limited attacking progress. |
| More unsettled rhythm | Turnovers/minute increase and possessions shorten against the preceding comparable window | Neither side is retaining possession for long. |

Add minimum sample sizes, comparable time windows, cooldowns, and duplicate suppression. Avoid treating a restart-heavy period as equivalent to continuous open play without acknowledging context.

“The coach instructed a higher press” or “the substitution caused the change” requires evidence beyond these event patterns. State observations and qualify interpretations.

## 15. Evidence receipts and deterministic tools

Store each evidence item with an ID, metric/value/unit, team/player scope, event-time window, source event IDs, calculation version, and input-quality flags.

Expose narrow, read-only functions such as:

```text
get_match_state(match_id, as_of_sequence)
get_team_window_stats(match_id, team_id, start_ms, end_ms)
get_player_window_stats(match_id, player_id, start_ms, end_ms)
get_insight_evidence(insight_id)
get_key_moments(match_id, limit)
```

Validate arguments, cap time windows/results, use parameterised queries, and execute against a consistent match snapshot. Do not give an LLM unrestricted SQL or mutation permissions.

DuckDB is useful for deterministic analytical queries over snapshots and recap history. Serialise writes or use a clear ingestion/query ownership model; do not assume that putting a database in memory solves concurrency or recovery. Consult [DuckDB documentation](https://duckdb.org/docs/stable/).

For automatic live overlays, a detector already knows the relevant evidence: skip a model-based planning round. Reserve tool selection for optional Q&A. This reduces latency and failure points.

An evidence drawer should show:

1. What changed.
2. Why it might matter.
3. Counts, definitions, comparison window, and event references.
4. Data quality and caveats.
5. Generation/fallback status.

Distinguish input quality, detector strength, and narrative verification. A model's self-reported confidence is not an accuracy measurement.

## 16. Narrate, verify, and fail gracefully

Supply a compact evidence packet, score/clock, relevant entities, audience preferences, language, and length constraints. Request structured fields such as `headline`, `explanation`, `evidence_ids`, `caveat`, `language`, and `audience_mode`.

Suggested instruction:

> Explain only supplied evidence. Preserve names and values. Do not invent historical records, injuries, tactical instructions, or player intent. Qualify interpretations. Use the requested language and audience style. Return the required schema.

Structured output constrains shape, not factual truth. See [Microsoft structured output documentation](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs).

Verify:

- Every cited evidence ID exists in the supplied snapshot.
- Entities and values match the cited evidence.
- Numeric claims preserve their scope, unit, denominator, time window, and relationship.
- No unsupported historical or causal assertion was introduced.
- Text fits the display limits and is still timely.

Checking that a number appears somewhere in the tool output is insufficient. “Three shots” and “three recoveries” are different claims. For stronger numerical guarantees, generate factual sentences from validated templates or structured claim slots; let the model provide carefully bounded explanation around them. Qualitative claim checking still needs explicit rules and reviewed examples.

On timeout, refusal, invalid output, or stale evidence, use factual fallback text: “Three high recoveries in five minutes; two were followed by shots.” Run inference asynchronously so it cannot block ingestion.

Proposed starting limits: one narrative call per accepted insight; at most one retry if still timely; roughly 150–250 output tokens; a short configurable deadline based on measured latency. Optional Q&A can have a separate longer deadline and small tool-call budget. Handle provider rate limits and cancellation.

Out-of-scope example: “This match stream does not contain season or career history, so I cannot establish a career record.” Never let the model fill missing data from general knowledge.

## 17. Meaningful personalisation and multilingual output

| Preference | Behaviour |
|---|---|
| Casual | Fewer statistics, ordinary language, short explanations. |
| Analyst | Definitions, comparison windows, quantitative detail, evidence access. |
| Favourite club | Prioritise relevant stories without changing facts or hiding decisive opponent events. |
| Favourite player | Prioritise that player's supported contributions. |
| Language | Appropriate wording, terminology, formatting, and text layout. |
| Frequency | Adjust overlay density and cooldowns. |

Same evidence, different output:

- Casual: “Northbridge are winning the ball close to goal and quickly turning those chances into shots.”
- Analyst: “Three attacking-third recoveries in five minutes produced two shots within ten seconds, consistent with more effective high pressure.”
- Player: “Patel made two of those three high recoveries”—only if the evidence supports this.

If the player has been quiet, do not invent involvement. Avoid turning every routine touch into a milestone.

Cache by evidence version, language, audience profile, and relevant selection preferences. Generate shared variants rather than one model call per viewer. Begin with two languages your team can review. Test names, numerals, football terms, wrapping, and equivalent meaning; support right-to-left layout if using a language that needs it.

## 18. Machine-readable, synchronised overlays

```json
{
  "overlay_id": "ov-042",
  "match_id": "demo-001",
  "insight_id": "ins-042",
  "revision": 1,
  "period": 1,
  "display_from_period_ms": 923000,
  "display_until_period_ms": 931000,
  "template": "insight_card",
  "priority": 70,
  "language": "en",
  "audience_mode": "casual",
  "headline": "Pressure creating chances",
  "body": "Three high recoveries have led to two shots.",
  "evidence_ids": ["ev-101", "ev-102"]
}
```

Adapt the contract to the rendering partner's actual specification. Add scheduling priority, maximum simultaneous cards, expiration, cancellation, correction, duplicate suppression, safe screen areas, and text limits.

Use media playback time, not server receipt time. Define the mapping between event period/time and media time. Pause, seek, buffering, delayed streams, and replay speed must affect scheduling. Clear stale overlays after seeking and rebuild from the appropriate match snapshot.

The data source may run ahead of delayed video: evaluate narratives against evidence available at the viewer's intended playback point, rather than revealing future events. Discard late AI output that has expired. If retaining longer retrospective context, label it clearly.

For a fully synthetic animation, control the replay clock and schedule events and graphics from it. Do not claim production broadcast synchronisation from a browser-only demonstration.

## 19. Recaps and optional Q&A

Store accepted key moments throughout the match. At half-time/full-time:

1. Rank significant moments.
2. Remove repeated versions of the same pattern.
3. Include major events and relevant quieter phases.
4. Add final deterministic statistics.
5. Apply audience/language preferences.
6. Generate and verify chronology, names, score, and figures.

Deliver a headline, approximately 100–150 words, and three key moments; add a player-focused paragraph where useful. Rebuild after authoritative corrections.

Milestones must have a reference set. “Most passes in this ten-minute window” can be supported; “a career record” cannot without career data.

Optional Q&A should use the same evidence tools, scope checks, and bounded orchestration. It must not replace the proactive live experience. State whether answers use the viewer's playback snapshot or the latest match state.

## 20. Observability and security

Adapt the reference app's reported receipts and trace view into a compact “How this was produced” drawer. Track:

- Correlation ID, event sequence/snapshot, and insight ID.
- Ingest, state update, detection, model, verification, and scheduling durations.
- Model deployment identifier, token usage when available, and estimated model cost.
- Verified claim count with a precise definition of what was checked.
- Timeout, fallback, invalid-output, and stale-insight counts.

Use OpenTelemetry when useful, export locally during development, and optionally send traces to Application Insights. Do not expose credentials, raw sensitive prompts, or unrestricted internal logs to viewers. See [OpenTelemetry Python documentation](https://opentelemetry.io/docs/languages/python/).

Keep keys server-side, exclude secrets from Git, restrict simulator/admin endpoints, and use managed identity where supported in Azure. Bound free-text inputs and treat them as untrusted data. A hackathon needs proportionate controls; it does not need all the reference application's reported network infrastructure.

## 21. Delivery schedule

Assume 48 focused build hours; distribute across evenings if needed. Align the final plan to the verified deadline.

| Hours | Work | Completion condition |
|---|---|---|
| 0–3 | Rules, roles, specification, model access, contracts | Shared demo story and successful model request. |
| 3–8 | Generator, API, interface skeleton | One event updates a visible statistic. |
| 8–15 | State, metrics, detectors | Reproducible scenario creates correct evidence. |
| 15–22 | Narration, verification, fallback | Validated insight appears automatically. |
| 22–28 | Audience modes, player/club preferences, two languages | Same evidence produces visibly different experiences. |
| 28–34 | Overlay scheduling, receipts, recap, Compose | Connected replay and recap work locally. |
| 34–40 | ACA deployment and failure checks | Demo works on intended machine and URL. |
| 40–44 | Usability, accessibility, documentation | No major evidence or interface gaps. |
| 44–48 | Rehearsal, recording, submission | Complete package and backup recording. |

For a 24-hour build, cut optional Q&A, advanced telemetry UI, extra detectors, and vision. Keep the five-stage path, two genuinely different audience modes, evidence, timed rendering, and recap.

Do not add features once the final reliability window begins unless they fix a blocking requirement.

## 22. Testing and measurable acceptance criteria

| Test | Expected result |
|---|---|
| Duplicate event | Counters update once. |
| Delayed/corrected event | Documented policy applies and affected evidence is revised. |
| Zero attempts or missing tracking | No arithmetic error; unavailable metrics remain unavailable. |
| Direction change at half-time | Progressive actions and attacking zones remain correct. |
| Quiet passage | No invented story. |
| Model timeout/rate limit/invalid response | Ingestion continues; factual fallback or suppression applies. |
| Unsupported question | Clear explanation of missing data. |
| Pause, seek, speed change, buffering | Overlays follow playback without stale cards. |
| Disconnect/reconnect | Snapshot and sequence recovery avoid duplicate state. |
| Goal during a lower-priority insight | Appropriate priority and replacement behaviour. |
| Different audience/language | Facts remain consistent; presentation changes appropriately. |
| Recap | Score, chronology, entities, and numbers match evidence. |

Measure event receipt to statistic update, detection to validated narrative, and scheduled display versus media time. Suggested initial local targets: statistics under 250 ms; factual fallback under one second; AI explanations under three seconds where deployment permits. These are targets, not established performance.

Report median and p95, sample size, machine/deployment, and load. Separate synthetic match time from wall-clock processing time. Evaluate detectors on hand-reviewed fixtures and unseen seeds; review narrative claims and translations. State “zero unsupported numerical claims in N reviewed outputs” only after measuring that set, not as a universal guarantee.

## 23. Computer vision: separate stretch track

Only start after the event-driven product works, ideally with a teammate who already has relevant experience:

1. Obtain permitted footage.
2. Detect players and ball.
3. Track across frames.
4. Calibrate camera/image coordinates to pitch coordinates.
5. Associate teams and, where supportable, player identities.
6. Infer candidate passes, shots, and speeds.
7. Convert candidates to the same event schema with provenance and quality flags.
8. Evaluate against labelled examples.

A track ID is not a player identity. Detection does not automatically establish passes. Camera movement, cuts, perspective, and occlusion complicate speed and distance. Keep the adapter isolated so errors cannot break the synthetic-event demo. Label simulated, observed, and inferred metrics distinctly.

## 24. Submission demonstration: under two minutes

The official submission video must be under two minutes; replace the earlier five-minute plan. Aim for 1:50–1:55. [Official rules, Section 4.4](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md).

| Time | Demonstration |
|---|---|
| 0:00–0:10 | Problem and product promise. |
| 0:10–0:35 | Synthetic replay produces a meaningful timed insight. |
| 0:35–0:55 | Inspect evidence and show the agent/tool workflow. |
| 0:55–1:20 | Switch casual ↔ analyst, then favourite player/language. |
| 1:20–1:40 | Show recap and concise Microsoft stack diagram. |
| 1:40–1:55 | Measured performance, fallback, and product value. |

Keep any longer walkthrough separate from the submission video. Rehearse a fixed seed, disclose its synthetic nature, and retain an unseen seed. Keep a local runnable version and a recording; distinguish live inference from cached/precomputed content if using a backup.

Prepare answers about what AI does, deterministic calculations, evidence validation, timing, audience differences, data realism, missing-data behaviour, cloud cost, and production scaling. Claims about what judges value must come from the actual rubric, not assumptions in a third-party analysis.

## 25. Submission checklist

- Repository and clear README with exact setup/run instructions.
- Dependency files, `.env.example`, Compose configuration, and deployment instructions.
- Architecture diagram and event/evidence/insight/overlay schemas.
- Metric and detector definitions, thresholds, and limitations.
- Synthetic generation method, seeds, data provenance, and licence notices.
- Tests, reviewed evaluation results, and measured latency.
- Public GitHub repository and publicly accessible video URL; video under two minutes.
- Working judging access through the judging period, ending 10 November 2026; English submission materials or translations. [Official rules, Sections 4.4, 4.8–4.9](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md).
- `docs/technology-evidence.md` identifying working, planned, and deferred integrations.
- Known limitations and failure behaviour.
- Explicit challenge mapping:

| Requirement | MatchLens evidence |
|---|---|
| Ingest | Validated, ordered, reproducible synthetic stream. |
| Interpret | Match state, metrics, and detectors. |
| Explain | Evidence packets, grounded narratives, verification, caveats. |
| Render | Scheduled overlay contract and visible match experience. |
| Personalise | Modes, club/player selection, language, frequency. |
| Narrative/recap | Automated summaries from accepted key moments. |
| Data innovation | Reproducible football-realistic scenarios and documented assumptions. |

## 26. First team session: concrete outcomes

Before ending the first session, complete these in order:

1. Confirm registration and submission deadlines in the official portal.
2. Agree MatchLens scope, assign owners, and create the repository.
3. Prove model access and establish a spending limit.
4. Write the shared spec and event/evidence contracts.
5. Make one synthetic pass update a statistic on screen.
6. Make one detector produce an evidence packet.
7. Turn that packet into a short validated explanation with fallback.

Build one excellent, explainable moment through all five stages before expanding.

## Reference links

- [Microsoft's official hackathon rules](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md) — primary source for the stack audit, dates, judging, and submission requirements.
- [Microsoft's official learning resource playlists](https://github.com/microsoft/insidethegamehackathon/blob/main/RESOURCE%20PLAYLISTS.md)

- [Official Microsoft Reactor series](https://developer.microsoft.com/en-us/reactor/series/S-1709/)
- [Referenced YouTube session](https://www.youtube.com/watch?v=EQ187ohgCbo) — analysed through the supplied Gemini report; not independently viewed.
- [Reported reference-app shortlink](https://aka.ms/football-results-dashboard) — destination not verified here.
- [Reported registration shortlink](https://aka.ms/AA13ltgi) — destination and deadline not verified here.
- [Microsoft structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs)
- [Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/overview)
- [Azure CLI installation](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows?view=azure-cli-latest)
- [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/first-steps/)
- [Vite guide](https://vite.dev/guide/)
- [Node release schedule](https://github.com/nodejs/Release)
- [DuckDB documentation](https://duckdb.org/docs/stable/)
- [Docker Desktop on Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
