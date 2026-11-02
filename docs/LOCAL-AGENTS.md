# Local agent architecture

## Five-stage pipeline

```text
Synthetic JSONL → ordered ingestion → deterministic statistics/snapshot
                                           ↓
                       supported story candidates + evidence facts
                                           ↓
                       Analyst → Story → Experience (MAF + Ollama)
                                           ↓
                       verified selections → reviewed EN/HI renderer
                                           ↓
                       timed JSON → replay UI / overlay adapter
```

The generator remains the source of simulated football actions. The Python reducers remain the authority for possession, player/team totals, speeds, difficulty, ratings, and xG. There is no reason to ask an LLM to recount these numbers.

| Stage | Implementation | AI responsibility |
|---|---|---|
| Ingest | `MatchStore`, sequence/identity checks, SQLite journal, HTTP replay client | None: transport and validation are deterministic |
| Interpret | Existing statistics reducers plus bounded event/window story candidates | Analyst chooses a relevant supported candidate and inspects its facts |
| Explain | Story editor plus reviewed story frames and exact evidence receipts | Choose context/numbers emphasis; cannot invent statistics or causes |
| Render | Versioned timed JSON envelope and existing replay frontend | None: safe text rendering and synchronization |
| Personalize | Viewer profile, candidate filtering, Experience editor, EN/HI wording | Choose an allowed audience style without changing facts |

This is **three specialised model agents orchestrated sequentially by Python**, using the real Microsoft Agent Framework `Agent` and `OllamaChatClient`. It is not an autonomous swarm or a hosted Foundry workflow. Local execution keeps the application independent of the unavailable Azure subscription.

## Roles and bounded decisions

1. **Analyst** receives at most four current candidates and the viewer profile. Its `lookup_context` tool can read only an existing candidate in the immutable request snapshot. Its final response must be exactly `{"candidate_id":"..."}`. A candidate cannot pass unless it was inspected.
2. **Story** receives the chosen candidate and exact facts. It chooses exactly `{"frame":"context"}` or `{"frame":"numbers"}`.
3. **Experience** receives that choice, profile, and allowlisted styles. Casual audiences permit plain/supporter; analyst audiences permit technical/comparison. It returns exactly `{"style":"..."}`.
4. Python validates all decisions and inserts exact values into reviewed English/Hindi sentences. Unsupported decisions never become displayed model prose.

Some small models emit a JSON tool plan instead of native Ollama `tool_calls`, or return a candidate before the lookup. The provider accepts only the known tool/argument shape, dispatches the same bounded read, and requires a **second grounded model response**. The trace marks host-normalized dispatch. It does not label that repair as a native model tool call.

Prompts are versioned in `backend/app/agent_providers.py`. The tested setup uses `qwen3:1.7b`, temperature 0, thinking disabled, 4,096 context tokens and at most 180 output tokens per SDK run. The Analyst repair can add one run. The SDK bounds tool iterations and calls; the host also limits lookups to four. One local workflow may infer at a time; concurrent uncached requests receive HTTP 429. The default workflow deadline is 120 seconds (configurable 1–300). Cache keys bind snapshot, full profile, scope, model, provider, and prompt version.

## Evidence and explanation boundaries

- Snapshot IDs hash metadata and the complete accepted source prefix, sequence count, and cutoff. A different source history produces a different identity.
- Agents receive no future events. The renderer cites source event IDs and exact facts from the same snapshot. A rewind creates a distinct context.
- Goal/dismissal candidates outrank smaller recent moments. Shot stories use the existing geometric xG estimator, not an invented probability.
- Rhythm/pressure stories compare equal measured windows only when thresholds and sample counts are met. More pressure events do not prove a tactical intention or causation.
- Passing milestones are match-local counts. There is no historical database for career/club records.
- Player context uses current goals, assists, and xG. Unknown/unsupported values remain unavailable rather than becoming zero.
- Recaps cover only the requested interval and current score, with a bounded list of key recorded moments. Full means **full match to the cutoff**, not future results.
- Locale and audience alter wording/emphasis. They never translate or recalculate the underlying numeric facts.

## Failure and observability

`verified` means all three model roles completed with allowed decisions and source-bound facts. It is not a guarantee that every football interpretation is correct. `demo` means deterministic choices and **no model inference**. `fallback` means one or more model stages failed and factual defaults were rendered; the reason is shown. `no_story` means insufficient supported evidence for that focus.

Per-response traces record role, duration, error, snapshot and actual SDK usage when available. Tool receipts record inspected candidates. Cache hits reuse a prior inference and return `cached: true`; their token/latency fields describe that original run, not newly billed work. There is no dollar-cost estimate. SQLite stores event payloads and complete insight envelopes, including profile preferences, on this laptop. It does not store credentials. The audit database grows with use and can be archived locally when the server is stopped.

The server binds to loopback by default. Same-origin browser writes, size limits, explicit schemas, safe DOM text escaping, and unknown-action rejection are implemented. It remains a local development HTTP server without production authentication, TLS, distributed workers, or public-feed hardening.

## Source map

| File | Purpose |
|---|---|
| `backend/app/contracts.py` | Viewer/request validation and envelope version |
| `backend/app/match_store.py` | Replay prefixes, ordered ingestion, snapshot identity |
| `backend/app/intelligence.py` | Facts, supported candidates, reviewed bilingual rendering |
| `backend/app/agent_providers.py` | Real MAF/Ollama roles and explicit demo provider |
| `backend/app/workflow.py` | Handoffs, verification, budgets, cache, fallback |
| `backend/app/persistence.py` | SQLite stream recovery and insight history |
| `backend/app/server.py` | Local HTTP API and frontend serving |
| `backend/app/replay_client.py` | Event-time HTTP replay producer |
| `backend/app/evaluate.py` | Reproducible demo/real-model evaluation |
| `frontend/intelligence.mjs` | Controls, synchronization, model status and evidence UI |

Official references: [Microsoft Agent Framework Ollama integration](https://learn.microsoft.com/agent-framework/integrations/by-component/model-providers/ollama), [Microsoft's native Ollama samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/02-agents/providers/ollama), and [Ollama thinking controls](https://ollama.com/blog/thinking). SDK versions are pinned because this integration changes over time.
