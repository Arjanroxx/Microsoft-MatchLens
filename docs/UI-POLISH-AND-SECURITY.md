# MatchLens UI polish and security review

Reviewed 29 October 2026; the UI changes were uncommitted at that review. The subsequent publication review and local-only inference safeguards are documented in [LOCAL-VALIDATION.md](LOCAL-VALIDATION.md) and [SECURITY.md](../SECURITY.md).

## Experience

The existing MatchLens identity now has calmer spacing, more legible commentary, quieter secondary controls and a companion beside the pitch. Leo is an original fictional AI-generated portrait, not a real commentator or an additional inference agent. The app retains the three-role local Ollama workflow, verified evidence and honest fallback labels.

Desktop has a pitch/statistics column and a commentary/timeline column. Mobile orders the pitch, commentary, statistics and timeline in one column. Light/dark themes use the existing tokens. Loading states let playback continue; preferences and technical receipts sit behind disclosures. Player SVG groups retain identity across frames, avoiding loss of keyboard focus. Long animation-frame gaps are capped so returning from a background tab does not abruptly jump the replay clock.

The design uses the existing application as its visual source. Product Design guidance informed implementation and review. No Figma file was supplied or created; the Figma design-system lookup could not run without a file key.

## Findings fixed

| Finding | Change and evidence |
|---|---|
| Imported shirt numbers and passing-lane evidence could enter HTML without escaping | Escape source values and shared metric cells. The actual app startup/import test loads hostile strings and checks player and pass inspectors contain escaped text, not injected elements. |
| Loopback server trusted arbitrary Host headers and did not reject cross-site reads | Shared guard enforces loopback Host/port, same Origin and Fetch Metadata; covers both replay bridge and AI server. Regression tests reject foreign hosts/origins, duplicate hosts and cross-site requests. |
| Request framing and body handling were too permissive | Reject transfer encoding and duplicate Content-Length; enforce endpoint size limits, complete body reads, socket timeout and bounded concurrent POST processing. Close POST connections after responses. |
| Static file exposure lacked defensive boundaries | Disable directory listing; reject hidden paths and resolved paths outside the frontend root. Add CSP, nosniff, frame protection and same-origin resource policy. Tests cover directory and hidden-file denial. |
| Failed durable ingestion could leave an event visible in memory | Roll back the newly accepted event on journal failure while holding the stream lock; test proves state restoration and successful retry. |
| Older JavaScript could survive a layout refresh | No-store response headers and versioned entry/transport module URLs. |
| Old AI responses could race a new profile/replay request | Use each request's own AbortController, retain epoch/cutoff checks, clear expired displayed insights and advance live cursors only after successful UI application. |

## Verification

- 63 frontend tests, including malicious import coverage in the real entrypoint smoke test.
- 29 backend tests, including journal-failure rollback.
- 9 replay HTTP/security tests.
- `pip-audit` checked all 19 pins in `requirements-ai-lock.txt`: no known vulnerabilities reported; no packages skipped. Report: `data/generated/dependency-audit.json` (ignored local artifact).
- Browser checks: desktop and narrow mobile layout, light/dark themes, goal seeking, local-model English/Hindi explanations, recap action and loading controls. Narrow viewport measured 375 px content width and 375 px page width: no horizontal overflow. No browser warnings/errors observed in these checks.
- Screenshot evidence under `data/generated/`: `ui-before-polish.png`, `ui-polished-dark.png`, `ui-polished-mobile.png`. These are local review artifacts, not required runtime assets.

Run the local app with `.venv\Scripts\python.exe -m backend.app.server --port 8082 --provider ollama`, then visit http://127.0.0.1:8082/. Ollama must already be running with `qwen3:1.7b` for real inference. The page labels a model outage as fallback rather than pretending an agent succeeded.

## Review boundaries

This was a focused source, dependency and browser review, not an independent penetration test or a guarantee that no vulnerabilities remain. The standard-library HTTP server is intended for a trusted local laptop. No login, TLS termination, multi-user authorization or public-service denial-of-service protection is provided. Do not expose it through a public tunnel or network binding; a hosted version needs a production server, authentication and operational limits. Other local processes are outside the browser-origin threat boundary.

Dependency results reflect published advisories at scan time and only the locked Python packages. They do not audit the Python/Node/Ollama executables, downloaded model weights, or the operating system. The frontend has no npm dependency tree. Fonts may load from Google; inference remains local. The xG model remains an explicitly uncalibrated synthetic-data heuristic.
