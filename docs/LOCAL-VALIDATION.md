# Local edition validation — 28 October 2026

## Publication review — 2 November 2026

Gitleaks 8.30.1 reported no secrets in all 20 pre-publication commits (all refs, about 82 MB scanned) or in staged project changes. Generated scanner reports and local logs stay under ignored `data/generated/`. No environment files, private keys, local databases or logs are tracked. Ignore rules now cover environment variants and cloud credential directories. See [SECURITY.md](../SECURITY.md).

The final regression run passed 103 tests: 63 frontend, 31 backend and 9 replay HTTP/security tests. New tests reject remote/credential-bearing Ollama endpoints, cloud model names and remote model metadata. Real inference clients disable redirects and environment proxies; `/api/show` must confirm a model has no remote host/model before each role runs. The GitHub workflow has read-only permissions and a pinned, checksum-verified full-history Gitleaks check on pushes and pull requests.

After starting the installed local Ollama service, all four real-model evaluations passed: opening shot, analyst goal, Hindi goal and halftime recap. All three roles completed with verified source-prefix claims; observed case latency was approximately 5–23 seconds. The ignored local report is `data/generated/publication-model-evaluation.json`.

The 28–29 October results below are historical baselines. Remote CI results must be checked on the published commit; local validation alone does not prove those jobs passed on GitHub.

Validated on Windows with Python 3.12.14, Microsoft Agent Framework core 1.23.0, Ollama integration 1.0.0b261022, and local `qwen3:1.7b`. Direct SDK dependencies are in `requirements-ai.txt`; the complete tested Python environment is recorded in `requirements-ai-lock.txt`.

| Check | Result |
|---|---|
| Backend tests, including original evidence verifier and new workflow contracts | 28 passed |
| Frontend tests, including existing simulator UI goldens and stale/live guards | 63 passed |
| Existing replay HTTP server compatibility tests | 5 passed |
| Real-model evaluation: opening shot, goal in analyst mode, Hindi goal, halftime recap | 4/4 verified, all three roles completed |
| HTTP live ingestion of `xg-match` | All 718 events accepted in sequence |
| Complete duplicate HTTP replay | Event count stayed 718; duplicate acknowledgements returned |
| SQLite restart recovery test | Full event list and final snapshot matched the original replay |
| Browser verification | Real goal explanation and Hindi analyst variant displayed; evidence/trace available; no console errors observed |
| Live board verification | Reached full time at the acknowledged watermark; team shot/xG counters shown |
| Mobile recap layout | Phone viewport: 375 px page/content width, no horizontal overflow; recap controls and complete text visible |

The final recorded four-case model evaluation took approximately **4.0–18.2 seconds per workflow**, under local development load. A browser goal request completed in 5.5 seconds. These are a handful of observations, not a latency benchmark or service guarantee. Hardware, model warm-up, context size and simultaneous activity affect results.

Reports and screenshots are generated under ignored `data/generated/`: `agent-evaluation-real.json`, `agent-evaluation-demo.json`, `portfolio-backend-tests.txt`, `portfolio-frontend-tests.txt`, `portfolio-ui-server-tests.txt`, and `matchlens-local-ai-preview.png`. Reproduce them using the commands in [PROJECT-COMPLETION.md](PROJECT-COMPLETION.md).

The full simulator physics suite was not rerun for this backend/frontend addition; simulator physics and reducers were unchanged. Its replay-server compatibility tests and existing frontend Python-statistics goldens were exercised. GitHub Actions configuration has been added but cannot be reported as passing remotely until the changes are pushed and a run completes.

Limitations remain explicit: reviewed evidence rendering instead of unrestricted model prose; English/Hindi only; synthetic, uncalibrated xG/ratings; local development hosting; no video recognition or Azure Foundry connection.
# UI and security follow-up — 29 October 2026

The polished commentary UI and server protections passed 101 tests: 63 frontend, 29 backend, and 9 replay HTTP/security tests. The frontend smoke test now includes hostile imported metadata/evidence; the backend covers rollback on a failed journal commit. All 19 locked Python dependencies were scanned with pip-audit with no known vulnerabilities reported. Desktop/mobile, light/dark, English/Hindi explanations and recaps were checked in the browser. See [UI-POLISH-AND-SECURITY.md](UI-POLISH-AND-SECURITY.md) for scope and limitations. Earlier validation above describes the previous baseline.
