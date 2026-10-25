# MatchLens: Foundry workflow and Azure readiness plan

Prepared 24 October 2026. This is a proposed implementation plan, not a claim that the cloud pipeline is already implemented. No Azure resources have been provisioned and no credentials or dependencies have been installed by preparing this document. Existing UI review changes remain uncommitted.

## 1. The architecture decision

Use Microsoft Foundry for model-backed interpretation, explanation and audience adaptation, coordinated by a bounded Microsoft Agent Framework workflow. Keep ingestion, arithmetic, event ordering, verification and overlay timing in ordinary deterministic application code, exposed to the workflow as tools where useful.

An agent can request a five-minute comparison; the Python tool calculates the numbers. An agent should not decide whether a pass counts, reconstruct possession percentages from prose, or change the source events. Foundry integration does not require replacing the working statistics engine with model arithmetic.

The [official rules, sections 4.1 and 6](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md) describe the five-stage experience and evaluate Microsoft platform use and agentic design. They do not say that every non-rendering operation must execute inside a language model. If organizers have separately specified a deployment requirement, map that explicitly before provisioning. The architecture below keeps Foundry central while preserving reliable tools.

## 2. Is $100 enough?

Likely yes for a bounded text-first hackathon build, provided an eligible model deployment and useful quota are available. It is not a guarantee of a particular model, throughput, hosted-agent capacity or total bill.

The [Azure education FAQ](https://learn.microsoft.com/en-us/azure/education-hub/faq) states that Azure for Students supplies $100 for 12 months, and that credits cannot be applied to Azure Marketplace offers. Check the actual subscription and deployment billing path; a model appearing in a catalogue does not establish eligibility. Model limits also depend on the actual deployment and subscription: [Foundry quota reference](https://learn.microsoft.com/en-us/azure/foundry/openai/quotas-limits). In particular, do not plan around discounted Batch inference: the published batch table lists student/free-trial offers as unavailable, and batch would not serve the live path anyway.

Budget illustration, deliberately **not** an Azure price quote:

| Assumption | Value |
|---|---:|
| Full-match test runs | 25 |
| Model requests per run, including tool round trips and audience variants | 200 |
| Average input tokens per request | 2,000 |
| Average output tokens per request | 400 |
| Total input/output | 10 million / 2 million |
| Hypothetical price per million input/output tokens | $1 / $4 |
| Model inference total at those hypothetical prices | $18 |

Replace those prices with the actual eligible deployment quote and measured token counts. Azure's [model pricing page](https://azure.microsoft.com/en-us/pricing/details/azure-openai/) varies by deployment choice; do not use the above illustrative rates as a purchase quote. Reasoning tokens, retries, long tool results and growing conversation context can change the estimate substantially.

Suggested internal allocation, not a forecast of Azure charges:

| Envelope | Budget |
|---|---:|
| Model integration and evaluation | $30 |
| Small hosting/storage allowance | $15 |
| Monitoring allowance | $5 |
| Demonstration, judging availability and contingency reserve | $50 |

Keep the frontend, simulator and most testing local first. A small eligible first-party model with the needed tool/structured-output support is the default; benchmark it before escalating to a larger model. Different agent roles can share one model deployment.

Avoid GPU VMs, AKS, provisioned model capacity, unnecessary search/vector infrastructure and an always-running hosted-agent container unless genuinely required. [Foundry Agent Service pricing](https://azure.microsoft.com/en-us/pricing/details/foundry-agent-service/) distinguishes model/tool charges from hosted-agent container compute. Your Python analytics functions do not require paid Code Interpreter sessions.

Cost controls: short evidence packets, bounded output, one concurrency-limited worker initially, an application request/token allowance, at most one corrective retry per episode, shared cohort caching and an explicit fallback. Configure Azure budget alerts where available, but they are notifications rather than hard cutoffs; cost reporting can lag. New subscriptions can take time to expose budgeting features. See [Azure budgets](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets). Use the sponsorship credit view and application token counters too.

## 3. Pipeline and agent roles

```text
Generator / scheduled JSONL replay
    -> ingestion adapter: validate, order, deduplicate, checkpoint
    -> incremental match state and window statistics
    -> deterministic candidate detector and rate limiter
    -> Analyst agent: choose a useful interpretation; request bounded tools
    -> evidence validation
    -> Story agent: explain significance and cite evidence
    -> claim validation
    -> Experience agent: adapt for active audience/language cohorts
    -> claim + locale + length validation
    -> timed insight delivery
    -> existing frontend overlay / feed / recap presentation

Halftime / full-time / catch-up request
    -> same Story agent in recap mode, using the accepted insight ledger
       plus the authoritative statistics for that cutoff
```

The coordinator is application workflow logic, not another always-on manager LLM. Three specialist agents are enough to demonstrate a meaningful handoff. Do not add a separate model-powered ingest agent or arithmetic agent. Microsoft documents both sequential and concurrent patterns and advises using only the complexity needed: [agent orchestration patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns).

### Analyst agent

Input: candidate event/window, immutable snapshot ID, replay cutoff and available evidence.

Tools to implement around the existing engine:

- `get_team_window_comparison(snapshot_id, team_id, current_window_ms, previous_window_ms)`
- `get_player_context(snapshot_id, player_id)`
- `get_possession_chain(snapshot_id, possession_id)`
- `get_score_and_match_context(snapshot_id)`

All tools enforce the snapshot cutoff themselves. They return exact facts, definitions, sample counts, event IDs and limitations. The agent selects a supported interpretation or returns `no_story`. It cannot manufacture data or read a later snapshot.

Examples: a shot changes the score context; repeated chances accumulate despite an unchanged score; a substitute contributes to a qualifying chance; a sequence shows more observed turnovers than its previous comparable window. Avoid declaring a tactical formation or coaching intention from the generator's hidden scenario label. Pressure-event frequency is an observation, not proof of a professional pressing system.

### Story agent

Input: accepted interpretation and evidence, not the entire match file.

Output: short headline, why-it-matters explanation, structured claims, evidence references, source cutoff and limitations. The explanation should connect chance quality, score/time and a supported comparison. Describe association rather than claiming that one event caused an unsupported tactical change. Do not invent season/career records without a real synthetic history store supporting them.

Recaps are a mode of this agent, not a fourth permanent agent. Use halftime/full-time snapshots and accepted moments; do not summarize only the last model conversation. Distinguish a full-match recap from a recap of events since a viewer's last cursor.

### Experience agent

Input: the same accepted intelligence, with viewer/cohort preferences: casual/analyst, locale, favourite team, favourite player and metric focus.

Output: audience-appropriate language, relevance, explanation depth and length. Casual fans should get plain-language significance; analysts should get exact windows, metrics, definitions and caveats. Translation must preserve names, values, meaning and evidence. A favourite team changes relevance and tone, not factual outcomes.

Generate only active cohorts. Reuse an output for viewers with identical preferences rather than invoking a model per viewer. Filter and route preferences deterministically before adaptation. Cache keys include match ID, snapshot/candidate ID, audience, locale, relevant team/player/metric, prompt version and model configuration. Start with English plus one language a teammate can review, such as Hindi if the team can evaluate it.

### Verification and publication

Verification is a mandatory code step, not an LLM voting on another LLM's confidence. Confirm entity identity, exact claim values, units, time window, evidence existence, allowed interpretation, source cutoff and output shape. Preserve the uncalibrated xG qualification. A rejected output gets one bounded correction or the existing factual fallback.

Localization introduces numeric/date formatting differences: preserve canonical typed claims independently of display text. A numeric regex alone cannot verify causal meaning or translation quality; constrain claim types/wording and review multilingual examples.

The publication layer supplies display timing and rejects stale responses. A factual goal/card label appears immediately; model narration arrives asynchronously and never blocks player movement or the scoreboard.

## 4. Live operation limits

- Ingest every event, including motion where needed for the board. Do not narrate every movement sample or ordinary pass.
- Inspect candidate windows cheaply at a configurable interval, e.g. 30 simulated seconds. A detector evaluation is not a model request.
- Prioritize goals, red cards, penalties and significant chances; use meaningful context for substitutions. Suppress repeated descriptions of the same phase.
- Aim initially for roughly 40–60 accepted narrative moments in a full match, with a configurable cap; this is a testing budget, not a promise that every match contains that many worthy stories.
- Budget an episode by actual requests, including tool-result continuation calls. Start with a maximum of six model requests and four analytics-tool calls total per episode. One corrective retry must remain inside that cap.
- Use short contexts and a proposed live deadline of about eight wall-clock seconds; measure latency before promising a service level. Use cached/factual output when late.
- Targets: statistics stay responsive independently of inference; obtain actual p50/p95 model latency, token use and acceptance rates from traces. Aspirational targets are not measured results.
- Derive expiry from the replay clock and priority, e.g. 60 simulated seconds for a live narrative, rather than assuming a fixed wall-clock duration.
- Demonstrate cloud narration at 1x or modest playback speed. At 60x, a five-second model call trails five match minutes; use that speed for deterministic regression tests instead.
- A rewind or new uploaded match changes the session epoch. Drop pending outputs from the previous epoch. Agents and caches must never reveal future results at an earlier replay time.
- Handle 429 responses with bounded backoff and coalescing. Retry transient failures, not invalid credentials or missing quota indefinitely. Do not let a recovered backlog flood the screen with obsolete insights.

## 5. What already exists, and what still needs building

| Area | Current repository | Preparation work |
|---|---|---|
| Synthetic data and metrics | Generator, validators, event evidence, motion, team/player stats, ratings and xG | Reuse; add window-tool wrappers and suitable fixtures |
| Replay | `simulator.replay` schedules JSONL to stdout | Build an actual receiver/adapter; stdout replay alone is not an integrated ingestion service |
| UI bridge | `simulator.ui_server` serves files and `/api/state` | Add or integrate a narrative service and one same-origin delivery contract |
| Explainability backend | Evidence packet, strict verification, reviewed templates, casual/analyst variants and `NarrativeProvider` seam | Add window/player/xG evidence and a Foundry provider/workflow |
| Existing narrative contract | Provider selects a template and exact claims; local provider is explicitly not AI | Prove a first cloud call through this contract, then version it for richer interpretation/localization; do not silently disable verification |
| Multi-agent runtime | Not implemented | Add typed roles, bounded handoffs and tracing |
| Multilingual/personalization | English and basic two-mode prototype | Add explicit profiles, locale schemas, reviewed localized outputs and cohort caching |
| Live AI overlays and recaps | Not connected to Foundry | Add asynchronous scheduling, accepted-insight ledger, recap triggers and failure states |

Current backend details: [backend README](../backend/README.md). Existing xG limitations and UI integration: [expected goals](EXPECTED-GOALS.md), [main UI handoff](UI-INTEGRATION.md).

## 6. Work to finish before Azure access

### A. Agree the contracts first

Define JSON schemas or Pydantic models for `EventEnvelope`, `MatchSnapshot`, `EvidencePacketV2`, `InsightCandidate`, `AcceptedInsight`, `ViewerProfile` and `OverlayMessage`. Preserve schema 1.9 and support older source fixtures. Use `match_time_ms` for playback, not a naive 90-minute clock that loses added time.

An accepted insight should carry:

```text
schema_version, insight_id, match_id, snapshot_id, through_sequence,
as_of_match_time_ms, source_event_ids, audience_mode, locale,
team_id/player_id where relevant, headline, explanation,
typed claims and evidence_ids, limitations, status, provider,
prompt_version, model configuration, generated_at_utc,
display_from_match_ms, display_until_match_ms, priority,
trace_id and session_epoch
```

These are proposed fields, not an existing API. Keep the browser's minimal display payload separate from detailed server traces if necessary.

### B. Make a local vertical slice

Connect scheduled replay to validation/deduplication, state updates, one candidate detector, a mock three-role runner, validation and a browser card. Suggested new routes (not currently implemented): `POST /api/events`, `GET /api/insights/stream` using SSE, and `POST /api/recaps`. Adapt the existing UI server or run a backend with a same-origin reverse proxy; do not leave competing `/api` handlers or accidental cross-origin requests.

Store raw fixtures and checkpoints locally at first. SSE reconnects use insight IDs/cursors; ingestion is idempotent on `(match_id,event_id)`, with defined sequence-gap and out-of-order handling. Tie all output to the correct replay/session clock.

### C. Write the deterministic evidence tools

Use the existing reducers as the only statistical authority. Add rolling/comparable windows, per-player context, score context and possession-chain evidence. Include denominators and minimum-sample rules. Do not invent tactical intensity from raw counts or treat missing metrics as zero. Keep unused `evaluation-only.json` truth and final summaries out of live prompts.

### D. Build the agent abstraction and mock runner

Define an internal `run_agent(role, payload)` boundary returning a typed result plus optional usage/trace metadata. Provide a mock implementation now and a Foundry implementation later. Mock latency, malformed responses, unsupported claims and service errors explicitly. Mocked output remains visibly labelled as such.

Write three prompts, tool descriptions and schema-constrained output examples. Snapshot prompt versions. Set all caps and timeouts in configuration rather than relying on prompt instructions alone. Let deterministic code enforce bounds.

### E. Create an evaluation set

Use 20–30 selected event windows from existing fixtures and controlled tests. Cover: goal, saved chance, poor-angle shot, penalty, missed penalty, red card, offside/invalid shot, substitution, substitute contribution, goalless quiet period, pressure/turnover change, halftime/full-time/catch-up, duplicate event, sequence gap, malformed event, unknown metric, rewind and late response.

For each case, specify required facts, permitted significance, forbidden claims, two audience treatments and the reviewed second-language version. Include the explicit `no_story` outcome. Measure JSON validity, numerical/entity/window correctness, unsupported-claim rate, translation preservation, latency and cost. Passing mocks validates plumbing, not actual model quality; run real inference evaluation once access arrives.

### F. Connect the UI against mock data

Add audience and language settings, favourite team/player, metric focus, an insight card/overlay, a recap action and an expandable evidence view. Preserve existing replay and score controls. Display loading, unavailable, mock, live-model and factual-fallback states honestly. Show when a narrative belongs to an earlier phase, or suppress it when expired.

### G. Prepare the environment

Keep the simulator dependency-light. Use a project virtual environment for AI/backend additions. The currently documented selective SDK is `agent-framework-foundry`; the full `agent-framework` package is an alternative, not a second required framework. See [Microsoft's Python instructions](https://github.com/microsoft/agent-framework/blob/main/python/README.md).

Example preparation commands; review against the team's environment rather than running them globally:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install agent-framework-foundry azure-identity python-dotenv pydantic fastapi uvicorn httpx pytest
```

Pin the successfully tested versions in the project dependency file. Prepare Azure CLI for sign-in; Docker Desktop is useful if containerizing, but not a prerequisite for local model-adapter tests. Avoid rewriting the working frontend into another framework for this integration.

Prepare `.env.example` with empty placeholders for `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL`, plus your application-specific mock/provider selection and request limits. Keep real credentials out of the browser and Git. Prefer developer identity locally and managed identity for a supported cloud host. Share team resource access with individual identities, not a committed shared key.

### H. Prepare deployment and observability

Draft a minimal deployment manifest/Bicep template and optional Docker Compose for web/API/simulator. Keep it undeployed. Start with local app plus real Foundry calls; if hosted delivery is needed, choose one small Container Apps deployment or another simple eligible host, with Blob Storage only when persistence is useful. Check service eligibility and quotas before instantiating templates.

Record trace ID, role, snapshot/cutoff, tool names, latency, token usage, validation status and fallback reason. Add Application Insights/OpenTelemetry wiring as an adapter; local structured logs are enough to test it tonight. Cap log volume. Do not send entire match files in every trace.

Treat Fabric history, a database, Event Hubs and Azure MCP integrations as explicit separately scoped choices. If any is a confirmed requirement, reserve an owner and validate access; otherwise implement the smallest useful extension after the core live loop works. An Azure MCP server is not needed simply to move event JSON between your own services.

## 7. Four-person allocation

| Owner | Before Azure | First task after access |
|---|---|---|
| You / data lead | Ordered ingestion, reducers, window tools, event/evidence schemas | Verify cloud tools return identical local facts at the same cutoff |
| AI/workflow teammate | Three role contracts, prompts, mock runner, validators and evaluation set | Connect one real Foundry provider; run evaluations before expanding roles |
| UI teammate | Reviewable UI work plus mock insight cards, profile/locale controls, evidence and recap states | Replace mock transport with accepted real outputs, preserving replay timing |
| Platform/testing teammate | Virtual environment/lockfile, deployment draft, logs, failure tests, demo and cost plan | Verify subscription/region/quota/identity, deploy minimum resources and measure usage |

First agree the schemas together, then work independently against those contracts. Have a local end-to-end integration checkpoint before anyone builds additional services.

## 8. First Azure session: verify before expanding

1. Confirm the Azure for Students subscription, credit balance and correct tenant.
2. Find a supported Foundry/model/region combination for that subscription and inspect its actual quota, billing type, pricing and role permissions. Check Agent Service availability separately from model availability.
3. Create the minimum resource/project/deployment. Send one tiny model request; then test a structured response and one analytics tool call. Record actual token use, latency and deployment identity. Do not deploy the whole stack before this gate passes.
4. If blocked, capture the exact policy/quota error and ask organizers or the institution's Azure admin about an approved subscription/resource. Do not assume more credits fix missing eligibility or silently substitute a non-Foundry endpoint as a compliant integration.
5. Connect the existing narrow narrative provider first. This proves authentication and evidence wiring with minimal new code.
6. Run a small real-model evaluation set; then connect Analyst -> Story -> Experience under the same caps. Start with one English audience, then add the second audience and one reviewed second language.
7. Turn on caching, token counters, rate limits and fallback handling. Re-run failure and rewind cases with real calls.
8. Demonstrate the full five-stage path. Add halftime/full-time/catch-up recaps, then host the minimal review build if required. Verify it from a teammate's device.
9. Reserve credit and an availability plan for the judging period, not just the recorded demonstration. Clearly label recorded/mock fallbacks; they do not replace proof of the actual Foundry integration.

## 9. Completion checklist

- [ ] Local replay feeds a real ingestion path with deterministic state and checkpoints.
- [ ] Statistics remain identical with AI enabled, disabled or failing.
- [ ] A versioned evidence contract links every accepted claim to a snapshot and source.
- [ ] One actual Foundry model request and one tool round trip are demonstrated.
- [ ] Three bounded role handoffs are visible in traces; tool continuation requests are counted.
- [ ] Casual and analyst views differ meaningfully while preserving the same facts.
- [ ] A reviewed second language preserves numerical and entity claims.
- [ ] Player/team/metric preferences filter relevance without changing facts.
- [ ] The overlay uses playback timing and handles rewinds and late responses.
- [ ] Halftime/full-time and viewer catch-up recaps are generated from supported evidence.
- [ ] 429s, timeouts, malformed outputs and missing evidence have honest fallbacks.
- [ ] Actual model latency, token consumption and estimated cost are measured.
- [ ] The demo shows one event going through ingest, interpret, explain, render and personalize.
- [ ] Remaining student credit and deployment access cover the intended judging availability.

Tonight's target: a complete local pipeline with mocked model roles and the same contracts the real Foundry provider will use. Tomorrow's target: prove eligible cloud inference immediately, then replace the mock model boundary without rebuilding the rest of the application.
