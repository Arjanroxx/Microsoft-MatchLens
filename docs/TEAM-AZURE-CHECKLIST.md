# MatchLens: four-person Azure integration checklist

Prepared 25 October 2026, Asia/Kolkata. Azure access expected in approximately one hour. This document assigns preparation and subsequent integration work; unchecked items are proposed work, not claims about existing functionality. The earlier architecture and budget discussion is in [FOUNDRY-READINESS-PLAN.md](FOUNDRY-READINESS-PLAN.md).

## The workflow we are implementing

```text
Synthetic generator / replay
  -> deterministic ingestion: validate, order, deduplicate
  -> existing Python statistics and an immutable evidence snapshot
  -> deterministic candidate detector
  -> Analyst agent: choose supported significance / request bounded tools
  -> Story agent: explain why it matters using that evidence
  -> deterministic claim verification
  -> Experience agent: adapt to audience, language and relevant preferences
  -> deterministic final verification and playback scheduling
  -> existing UI: insight, evidence, player focus and recap
```

Three agent roles can use the same eligible model deployment. They do not need three different models. The coordinator is bounded application workflow code. No LLM maintains possession, counts passes, calculates ratings or adds up xG. Halftime/full-time/catch-up are modes of the Story agent, rather than a fourth permanent agent.

The Python statistics and source events already exist. Ingestion into a live backend, rolling-window tool wrappers, three agent handoffs and AI insight delivery still need implementation. The existing backend is a narrow template-selection/evidence prototype, explicitly not connected to Foundry. Do not rebuild working statistics or assume the frontend already has live narrative transport.

## First 10 minutes: everyone together

- [ ] Each person checks for local edits, then fetches current `main` without overwriting their work. UI baseline commit: `7e6d1ac`. New teammate commits may exist; inspect before merging.
- [ ] Assign the four owners below. Use separate branches/checkouts and avoid editing each other's owned files. No agent should silently overwrite another person's schema or endpoint.
- [ ] Choose one shared source fixture: `data/examples/movement-match` for the main demonstration. Reuse the small `data/examples/xg-match` for fast iteration and the discipline/offside fixtures for targeted checks. Do not invent new metric values for the demonstration.
- [ ] Agree one same-origin backend route owner, one shared insight contract and one replay-clock contract. Freeze their initial versions before independent work.
- [ ] Choose one first trigger: a valid completed shot or goal. The first tool is player/score context around that event. Add complex trend detection after this works.
- [ ] Pick English plus one language a teammate can actually review for the later multilingual milestone. English + Hindi is a reasonable choice if a reviewer is available.

### Shared contract: one owner writes it, all four agree

Platform owner maintains the initial shared schema file, e.g. proposed `backend/app/contracts.py`; data/AI owners supply the evidence and claim definitions. This path is not currently implemented.

Minimum accepted insight envelope:

```text
schema_version = "insight-v1"     # distinct from event schema 1.9
insight_id, match_id, snapshot_id, through_sequence
as_of_match_time_ms, session_epoch
audience_mode, locale, team_id/player_id when applicable
headline, explanation
claims[], evidence_ids[], source_event_ids[], limitations[]
display_from_match_ms, display_until_match_ms, priority
status, provider, trace_id
```

Each typed claim identifies its metric, entity, exact canonical value, unit, window if relevant and supporting evidence references. Keep typed claims separate from localized display numbers. Both audience variants reference the same underlying evidence and snapshot.

Clock rules:

- Use the simulator's monotonic match time, including added time; retain period-local time where needed.
- The server creates the authoritative snapshot and cutoff from ingested events. The browser cannot supply arbitrary statistics and have them treated as verified evidence.
- Tool queries are constrained to that snapshot. Agents cannot request future events.
- A rewind/new match changes `session_epoch`; late results from an old epoch are rejected.
- An insight with unavailable or expired display timing is not shown as a current live observation.

Suggested interfaces, **not existing endpoints**:

- `POST /api/events`: receive an event against startup-loaded/registered match metadata.
- `POST /api/insights`: request an insight for an authorized snapshot/cutoff and viewer profile; can return a mock response during preparation.
- `GET /api/insights/stream`: later SSE delivery with IDs/reconnect cursor, if needed for continuous publication.
- `POST /api/recaps`: later recap request with cutoff, scope and profile.

Keep the existing `/api/state?time_ms=...` usable. Start with the request/response insight interface if SSE would delay the first working path. Agree metadata registration/startup loading and invalid input responses; do not stream events without their roster and match metadata.

## Teammate 1: you / data and ingestion owner

Owned areas: simulator adapters, new statistics-tool wrappers and candidate detection. Coordinate any shared evidence changes with teammate 2. Existing source: `simulator/statistics.py`, `simulator/player_statistics.py`, `simulator/xg.py`, `simulator/replay.py`.

### Before Azure: must-have, minutes 10–40

- [ ] Reuse the current reducers rather than write a second statistics implementation.
- [ ] Implement a minimal ordered ingestion adapter: validate identity/schema, deduplicate on `(match_id,event_id)` and preserve source sequence. Define what happens to a gap or out-of-order event; reject/buffer with a bounded policy rather than silently apply inconsistent state.
- [ ] Export an immutable snapshot with match ID, cutoff, sequence and stable snapshot ID. Keep final-summary values and `evaluation-only.json` out of the live path.
- [ ] Provide one tool-shaped evidence response for a selected valid shot: shooter/team, score/time, shot xG and available player context, with source IDs and the xG caveat. Implement a deterministic shot/goal candidate trigger and respect `valid_for_statistics`.
- [ ] Supply teammate 2 one actual candidate and evidence packet, and teammate 3 the corresponding mock insight source context. Include a quiet/invalid case that should produce no narrative.
- [ ] Check duplicate ingestion, a cutoff before the shot, and an invalid/offside shot. Statistics must remain identical when agents are disabled or fail.

### Before Azure: stretch, only after that handoff

- [ ] Add proposed `get_team_window_comparison`, `get_player_context`, `get_possession_chain` and `get_score_and_match_context` wrappers. Pin every call to a snapshot ID.
- [ ] Add rolling windows with units, denominators, sample counts and missing-data rules; suppress claims when the sample is insufficient.
- [ ] Add candidate deduplication, priority and a cooldown so ordinary passes/movement do not invoke agents repeatedly.

### After Azure access

- [ ] Connect the same tools to the real Analyst agent; compare returned facts with the local evidence byte-for-byte or by canonical typed values.
- [ ] Verify the agent chooses a useful tool, accepts its result and produces an evidence-linked interpretation. A canned context prompt alone does not demonstrate tool use.
- [ ] Run a complete match and verify no double counting, future leakage or invalid-attack credits.
- [ ] Expand observed-pattern detection: chance-quality changes, turnovers/rhythm, supported player contributions and substitution context. Do not infer formation or coaching intentions from a hidden generator scenario.

Completion evidence: ingested source event -> snapshot ID -> tool result -> identical existing statistics, including explicit no-story/invalid cases.

## Teammate 2: AI, workflow and verification owner

Owned areas: `backend/app/providers.py`, `narrative.py`, `verification.py`, new role prompts/workflow and AI evaluations. Coordinate shared contracts with teammate 4. Existing provider only selects templates and exact claims; it does not support unrestricted prose or multilingual storytelling yet.

### Before Azure: must-have, minutes 10–40

- [ ] Define a typed internal `run_agent(role,payload)` boundary and a mock runner. Reuse the existing `NarrativeProvider` for the first narrow connection; version richer outputs instead of disabling its verification rules.
- [ ] Write three short, versioned role prompts: Analyst chooses supported significance or `no_story`; Story explains using approved evidence; Experience adapts audience/locale without changing facts.
- [ ] Run the candidate from teammate 1 through all three mock roles. Produce casual and analyst versions with the same evidence, and visibly label the provider as mock/local-demo.
- [ ] Enforce shape/entity/value/unit/evidence/cutoff checks in code, including after audience adaptation. Never use another model's confidence as the factual validator.
- [ ] Put bounds in code: initially at most six model requests and four analytics-tool calls per episode, including continuation/correction requests; one corrective retry must fit inside the total cap. Keep the live deadline configurable, initially around eight wall-clock seconds, with factual fallback.
- [ ] Prepare five priority evaluation cases: valid goal/chance, unsupported number, invalid/offside shot, no-story quiet period, timeout/malformed response. Record expected facts and prohibited claims.

### Before Azure: stretch

- [ ] Expand to 20–30 cases covering penalties, cards, substitutions, recaps, translation, missing evidence, rewinds and stale results.
- [ ] Prepare recap prompts using accepted-insight history plus authoritative cutoff statistics, with halftime/full-time/catch-up scope.
- [ ] Add a cohort cache keyed by match/snapshot/candidate, audience, locale, relevant preferences, prompt version and model configuration. Do not key only by clock or viewer ID.

### After Azure access

- [ ] With teammate 4, prove one small real request using the selected SDK and deployment. Then prove one structured response and one tool round trip.
- [ ] Connect one Foundry-backed role through the existing narrow provider before expanding the workflow. Record actual deployment/model identity, token use, latency and result status.
- [ ] Replace mocks at the model boundary and run Analyst -> Story -> verification -> Experience -> verification. Multiple roles may share one deployment.
- [ ] Run the priority evaluations with the real model; fix unsupported claims before adding more features.
- [ ] Add the reviewed second language and recap modes, then test their meaning and numerical preservation.
- [ ] Confirm there is meaningful interpretation: the result explains relevance to score/time/chance quality or a supported comparison, rather than restating that a shot happened.

Completion evidence: one trace showing real Foundry role execution and tool use, verified evidence, two different audience treatments and bounded fallback behaviour.

## Teammate 3: UI and audience-experience owner

Owned areas: frontend insight presentation and profile controls. Start from the reviewed responsive UI; preserve theme, scoreboard, board, decision overlays and existing player inspector.

### Before Azure: must-have, minutes 10–40

- [ ] Implement one insight card against the shared envelope, with headline, short explanation, source time, provider/status and expandable evidence references.
- [ ] Add casual/analyst selection and a profile object for locale, favourite team, favourite player and metric focus. Start with working defaults; do not block the card on a complex settings page.
- [ ] Show the two mock audience variants from teammate 2. Keep the same facts and source time, and make the difference in wording/depth clear.
- [ ] Implement honest loading, mock, verified live-provider, factual-fallback, unavailable and expired states. Do not call the mock output live AI.
- [ ] Drop responses for another match, a different profile request, an old session epoch, a future cutoff or an expired display window. Keep the pitch running while inference is pending.
- [ ] Put the transport behind one function so the mock response can be replaced without changing rendering. Agree same-origin routing with teammate 4; avoid two servers owning different `/api` routes accidentally.
- [ ] Check the card and controls on desktop and mobile; rerun the existing frontend tests.

### Before Azure: stretch

- [ ] Add a recap action and player-focused insight presentation. Do not replace the existing player statistics with generated prose.
- [ ] Add the reviewed second-language example and check wrapping, proper names and number formatting.
- [ ] Add a small trace/evidence detail view that distinguishes claims, source events and model metadata without overwhelming the normal fan view.

### After Azure access

- [ ] Switch the transport to accepted backend responses, keeping credentials and SDK calls off the browser.
- [ ] Test real latency and fallback states. Show factual goal/card labels immediately; model explanation arrives later.
- [ ] Demonstrate that changing audience, locale or favourite player affects relevance/presentation while preserving factual claims.
- [ ] Test a rewind during inference, a match change, a late result and an unavailable provider. Discard obsolete output.
- [ ] Verify the hosted/review link from another teammate's device when deployment is ready.

Completion evidence: one actual source-backed insight rendered for casual and analyst viewers, responsive controls, working evidence expansion and no future/stale insight after rewind.

## Teammate 4: platform, API integration and test owner

Owned areas: shared contracts file, new API/transport service, environment/lockfile, tracing, deployment draft and integration test harness. Coordinate service seams with teammates 1–3; do not edit their implementations independently.

### Before Azure: must-have, minutes 10–40

- [ ] Publish the agreed shared schema and endpoint examples immediately. This must happen before three people implement different payloads.
- [ ] Check Python/Node/Azure CLI availability, set up a project virtual environment, install the selected SDK/backend dependencies and pin tested versions. Use the Foundry integration package `agent-framework-foundry` or the full framework deliberately, not multiple competing agent frameworks.
- [ ] Prepare `.env.example` with empty `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL`, plus application-specific provider selection and request limits. Do not commit real credentials or assume a particular endpoint/API generation before the actual resource exists.
- [ ] Wire the minimal local API between ingestion, mock workflow and UI. One shot/goal must make the whole journey; request/response is sufficient initially if SSE is not ready.
- [ ] Add structured local traces: trace ID, snapshot/cutoff, role, tool, latency, provider, usage when available, validation status and fallback reason. Mock token usage must be unknown or labelled simulated, not presented as billed usage.
- [ ] Run a single local end-to-end test and capture the expected output. Maintain a short blocker list distinguishing subscription, SDK, contract and code issues.

Microsoft currently documents the selective Python installation here: [Agent Framework Python setup](https://github.com/microsoft/agent-framework/blob/main/python/README.md). Example environment command from the repo root, if a suitable environment does not already exist:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install agent-framework-foundry azure-identity python-dotenv pydantic fastapi uvicorn httpx pytest
```

### Before Azure: stretch

- [ ] Draft a minimal deployment and optional Compose setup, without provisioning resources. Do not make Docker installation or a full Bicep rollout block the local integration.
- [ ] Prepare rate limiting, cohort caching, application request/token allowances, capped backoff, cancellation and queue coalescing.
- [ ] Prepare SSE reconnect/deduplication if required by the live publisher.

### After Azure access: lead the access gate

- [ ] Sign in to the correct tenant and subscription. Verify the student credit balance, subscription status and team permissions.
- [ ] Check actual eligible model/region/deployment availability, model quota, Agent Service access and billing type. A balance, resource creation success or visible catalogue entry is not sufficient evidence of working inference.
- [ ] Provision only the minimum Foundry resource/project and one eligible model deployment. Verify one real request and one tool cycle with teammate 2 before building the rest of the cloud stack.
- [ ] Prefer local developer identity and supported managed identity on the eventual cloud host. Give teammates individual resource access rather than sharing secrets in Git/chat.
- [ ] If blocked, record the exact policy/quota/permission error and contact the organizer/institution admin for an approved route. Keep local work moving; do not silently substitute another provider and claim Foundry integration.
- [ ] Configure budget alerts where available and enforce application limits immediately. Azure budgets do not stop consumption, reporting can lag and new subscriptions can take time to expose cost-management features: [budget documentation](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets).
- [ ] Confirm credit eligibility for the chosen service. Student credit cannot pay for Azure Marketplace offers: [education FAQ](https://learn.microsoft.com/en-us/azure/education-hub/faq).
- [ ] After local real-Foundry integration works, deploy the smallest eligible host required for review, with basic monitoring. Keep AKS, GPU VMs, provisioned inference and unnecessary search services out of the critical path.

Completion evidence: a genuine Foundry call, structured result/tool test, measured usage and latency, all four roles integrated locally and a minimal deployment path with a spending reserve.

## Minutes 40–60: everyone integrates

Do this checkpoint even if some stretch items are incomplete:

1. Teammate 1 replays a chosen event through the receiver and exports the immutable evidence snapshot.
2. Teammate 2 runs the mock Analyst -> Story -> Experience workflow using that snapshot.
3. Teammate 4 exposes the result through the agreed local API and records one trace.
4. Teammate 3 renders it, switches audience, opens evidence and rewinds to before the source event.
5. Confirm the same facts reach both audiences, no future output appears after rewind, and statistics still work if the mock workflow fails.

**Hour-one exit criterion:** one real source event travels through the whole local pipeline with honestly labelled mock agents. If that is not complete, finish it before adding deployment services or additional agents. A mock pass proves contracts and plumbing, not real-model quality or Foundry compliance.

## Sequence after the subscription arrives

These are ordered gates, not promised Azure provisioning durations:

| Gate | Owners | Evidence required before moving on |
|---|---|---|
| 1. Access | Platform + AI | Eligible deployment, usable quota, identity and one successful real request |
| 2. Tools | AI + data | One real agent tool request, deterministic result and structured final response |
| 3. Workflow | AI + platform | Three bounded Foundry-backed roles, typed handoffs and working validators |
| 4. Audience | UI + AI | Casual and analyst presentations from the same evidence; one reviewed second language |
| 5. Live behaviour | All four | Responsive replay, scheduling, expiry, failures, reconnect/rewind and no future leakage |
| 6. Recaps | AI + data + UI | Halftime, full-time and viewer catch-up use authoritative cutoff data and accepted moments |
| 7. Submission build | Platform + all | Accessible review build, truthful provider labels, measured latency/cost and a rehearsed demonstration |

Start cloud development with one English audience, then expand. Hosted Foundry agents, local Agent Framework orchestration calling Foundry agents, and ordinary model endpoint calls are different deployment choices; confirm and document which one the project actually uses. If organizers mandate a specific managed runtime, test its availability at gate 1.

## Cross-team acceptance cases to cover after the first working path

- [ ] Goal, valid saved shot, penalty/miss and red card.
- [ ] Offside/invalid attack excluded from statistical and narrative credits.
- [ ] Substitution and substitute contribution keep correct player identity and live rating context.
- [ ] Quiet period produces no unnecessary model call/story.
- [ ] Insufficient samples and missing evidence never become invented facts or zeros.
- [ ] Duplicate, reordered/missing-sequence and malformed events follow the defined ingestion policy.
- [ ] Incorrect model number, unknown entity, wrong unit, unsupported causal claim and malformed JSON are rejected.
- [ ] Timeouts, 429s and temporary outages use bounded handling without a stale-response flood.
- [ ] Different audience/profile/locale outputs preserve canonical claims and source times.
- [ ] Rewind, new match, changed preferences and delayed responses do not leak future or obsolete insights.
- [ ] Halftime/full-time recaps and catch-up since a viewer cursor remain distinct.
- [ ] Token usage, request counts and p50/p95 latency are measured for the real model, not inferred from mocks.
- [ ] Core demonstration uses 1x/modest replay speed; accelerated regression tests do not dispatch a full model episode for every source event.
- [ ] Credit reserve and application availability cover intended judging access, not just the recorded demo.

## What to defer

Do not use this hour for more generator realism, another UI redesign, video auto-eventing, a large multi-agent group chat, fine-tuning, historical RAG without a dataset, GPU compute, Kubernetes or integrating every named Azure product. If a separate service is a confirmed organizer requirement, assign and validate it explicitly; otherwise finish the complete five-stage path first.

For team debugging, each person should report: completed artifact, one command/action demonstrating it, schema/interface used, known limitation and blocker. This is more useful than reporting that a package installed or a portal page opened.
