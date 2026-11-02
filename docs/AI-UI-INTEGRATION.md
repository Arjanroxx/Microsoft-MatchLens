# AI integration guide for the Replay Studio frontend

Read this alongside [UI-INTEGRATION.md](UI-INTEGRATION.md), which remains the field map for simulator priorities 1–3. The agent panel is already integrated into `frontend/index.html`, `frontend/intelligence.mjs`, `frontend/intelligence.css`, and the lifecycle in `frontend/app.mjs`. Preserve the existing pitch, evidence inspector, and prefix-statistics behaviour.

## Commentary UI (29 October update)

The integrated panel is now **In the box with Leo**, with an original fictional AI-generated portrait in `frontend/assets/commentator.png`. `studio-polish.css` loads after the existing styles and preserves their theme tokens. Desktop places commentary beside the pitch; at 1000 px and below it follows the pitch, before the statistics and timeline. No Figma file is required to run the app.

- **Talk me through it** calls the insight endpoint; **Catch me up** calls recaps. **Your view** contains audience, language, club, player and metric preferences.
- Keep the IDs and lifecycle methods in `intelligence.mjs`: changing match, replay position or profile aborts stale requests. Expired displayed insights clear as playback advances. All manual request buttons disable together while a request is pending.
- `data-state` on `#ai-panel` is `ready`, `thinking` or `offline`; `aria-busy` and the polite live region expose loading/results without moving keyboard focus. Reduced-motion settings suppress decorative CSS transitions and announcement animations.
- Verified, demo and fallback results remain visibly distinct. Leo is a presentation character, not a fourth agent or a speech engine. English/Hindi are supported by the current backend; other languages are not silently advertised.
- Keep player SVG group nodes stable during playback so keyboard focus and hover do not disappear each frame. Imported names, shirt numbers and evidence values must be escaped before insertion into HTML.
- Use the same origin for frontend and API. The server now rejects foreign origins/Host headers with 403 and ambiguous request framing with 400. POST limits are 16 KiB for insight/recap, 2 MiB for one event, and 64 MiB for match registration; the UI import cap remains 60 MiB. Requests beyond the concurrent POST limit return 429. This is a loopback-only application, not a public hosting server.

See [UI-POLISH-AND-SECURITY.md](UI-POLISH-AND-SECURITY.md) for verification and remaining deployment boundaries.

## Endpoints

| Method/path | Purpose |
|---|---|
| `GET /api/health` | Mode (`replay`/`live`), provider readiness, model name, SDK availability |
| `GET /api/state?time_ms=T&match_id=ID` | Authoritative player/team statistics at cutoff; no future data |
| `POST /api/insights` | Explain a supported current moment for a viewer |
| `POST /api/recaps` | Interval recap, current score and recorded key moments |
| `POST /api/matches` | Validate/register `{metadata,events}` for a locally imported replay |
| `POST /api/events` | Append **one original event object** to the default live match |
| `GET /api/live?after_sequence=N` | Default match metadata, subsequent events and ingestion watermark |
| `GET /api/history?time_ms=T&match_id=ID` | Most recent 20 saved envelopes at/before cutoff; may contain older profiles/epochs |

POST bodies require `application/json`. HTTP 400 means invalid input, 404 unknown source/route, 429 an occupied inference worker, and 500 an internal/storage failure. The UI automatically registers an imported replay on `unknown_match`, then retries once. Model failure normally returns a factual fallback envelope with HTTP 200; distinguish its status from success.

## Request contract

```json
{
  "match_id": "USE_METADATA_MATCH_ID",
  "time_ms": 2612545,
  "session_epoch": "NEW_UUID_FOR_THIS_REPLAY_CONTEXT",
  "profile": {
    "audience_mode": "casual",
    "locale": "en",
    "team_id": null,
    "player_id": null,
    "metric_focus": "all"
  }
}
```

`time_ms` is continuous elapsed match time **including generated added time**. Use `event_time`/the frontend's prepared `event.t`; do not assume the second half starts at 45:00. Never send a browser playback rate as match time. `team_id` is `home`, `away`, or null; player IDs come from metadata. Team/player selections must agree. Supported locales: `en`, `hi`; modes: `casual`, `analyst`; metric focus: `all`, `xg`, `passing`, `pressure`. Unknown fields/values are rejected.

For `/api/recaps`, add `"scope":"catchup"`, `"half"`, or `"full"`. Only catchup accepts optional `since_ms`. Without it, catchup covers the preceding 60,000 match milliseconds; with it, the interval starts at the previous successful catchup cursor. The current UI advances that cursor only after accepting a result. Interval counters use `(start,end]`; score is current at `end`. This can yield zero interval shots alongside a nonzero match score, which is correct.

## Response and display rules

The envelope uses `schema_version: "matchlens-insight-v1"`. Read these fields:

| Fields | Frontend behaviour |
|---|---|
| `match_id`, `snapshot_id`, `through_sequence` | Keep source identity and receipts together |
| `session_epoch`, `profile` | Accept only the still-active context and exact profile |
| `as_of_match_time_ms` | Cutoff requested by this UI action |
| `moment_time_ms` | Actual chosen event time; may be earlier than the cutoff |
| `display_from_match_ms`, `display_until_match_ms` | Match-clock display window, **not wall-clock timestamps** |
| `headline`, `explanation`, `locale` | Render escaped text, with `lang=en` or `lang=hi`; never `innerHTML` raw model strings |
| `status`, `real_model`, `model_stages` | Honest real/demo/fallback/no-story labels; no “AI” badge for demo |
| `claims`, `evidence_ids`, `source_event_ids` | Expandable source evidence; claims contain exact values, units, scope and snapshot |
| `trace`, `trace_id`, `provider`, `model` | Optional diagnostics drawer; inspect all three agent stages |
| `usage`, `latency_ms`, `cached` | Actual reported counts/timing; cached results refer to their original inference |
| `limitations`, `verification`, `fallback_reason` | Explain provenance, assumptions and failed model stages |
| `recap_scope`, `interval` | Scope/start/end/phase and recorded key moments for recap cards |

`no_story` is a valid empty state and may omit moment/kind/recap-specific fields. Do not assume every response has a player, interval, usage record, or three model stages. Numeric xG is an uncalibrated estimate; player ratings are event-based estimates.

Use the exported pure `acceptsInsight` helper as the final acceptance gate. A result must match schema, match, epoch, full profile, and requested cutoff. Its cutoff must not be in the current replay's future, and it must still lie in its match-clock display window. Rewinding, selecting another event/match, or changing preferences must abort the browser request, increment the request serial, change epoch, and clear the old result. Browser cancellation may leave a server model call running until its bounded deadline; a new request can temporarily get 429.

## Current interaction behaviour

- **Explain this moment:** explicitly request at the paused/current replay position; the replay need not stop while loading.
- **Auto insights:** off initially; when enabled, checks every 30 seconds of simulated play and requests period-boundary recaps near a period-end event. No model call per pass/frame.
- **Make it your match:** team/player/metric filters narrow candidate selection; a player selection sets the corresponding team. This does not currently move the camera or hide other players on the pitch.
- **Build recap / Catch me up:** interval narration with the same evidence and stale-result checks.
- **Following stream:** available only for `--live`; polls new events every 1.5 seconds and updates the existing board. Turning follow off lets the viewer inspect earlier play.
- Missing Ollama/SDK/model: provider status explains readiness and requests produce explicit factual fallback. Demo mode is separately labelled.

## Copyable teammate task

> Extend the existing MatchLens frontend using docs/AI-UI-INTEGRATION.md and docs/UI-INTEGRATION.md. Use the implemented local API rather than recalculating authoritative statistics or calling Ollama from the browser. Preserve acceptsInsight checks, epoch resets, exact profile matching, language tags, original evidence receipts, and honest demo/fallback labels. Keep unknown values unavailable. Retain all simulator P1–P3 controls and evidence panels. A player-focused view may highlight the chosen metadata player but must not invent tracking samples. Add UI enhancements around the current working integration, verify desktop/mobile, and run node --test frontend/tests/*.test.mjs. Avoid any Azure requirement for the local edition.

## Acceptance checks

1. Pause on a goal, request an English casual explanation, and verify the current score and goal event ID.
2. Request Analyst and Hindi variants; facts remain source-bound while presentation changes.
3. Select a player with no recent evidence; show a supported player summary or an honest empty state.
4. Request an explanation, immediately rewind/change profile, and confirm the previous result cannot appear in the new context.
5. Build catchup/half/full recaps at appropriate cutoffs. Full-time results must never appear while inspecting the first half.
6. Stop Ollama or use an unavailable model; show explicit fallback rather than a fake verified badge.
7. Start a live server and producer; verify exactly-once counting under duplicate retries and persistence after restart.
8. Check keyboard controls, small screens, long Hindi text, evidence drawer scrolling, and no browser errors.
