# Security and local inference

MatchLens runs a synthetic-data simulator and a local Ollama workflow. No API key, Azure subscription or paid inference account is needed. The frontend contains no model credentials. This edition has no automatic cloud fallback: unavailable inference produces a labelled factual fallback.

The Ollama provider accepts only credential-free loopback HTTP endpoints, rejects cloud model names, and checks `/api/show` for remote model/host metadata before each agent invocation, including renamed cloud aliases. Its HTTP client ignores proxy environment settings and refuses redirects. Use downloaded weights such as `qwen3:1.7b`. This protects the application's inference path; unrelated software, a modified Ollama installation or manual changes are outside that boundary.

The application server binds to localhost and rejects foreign Host/Origin headers. It is intended for a trusted laptop. Public repository access does not expose the running local server. Public hosting would need a production server, authentication, authorization and operational limits.

## Before publishing changes

- Keep secrets in an untracked local environment file. Never put credentials in frontend code, screenshots, fixtures, commit messages or documentation.
- `.gitignore` excludes environment variants, private key/certificate files, cloud credential directories, local databases/logs, virtual environments and generated data. Example environment files are permitted only with placeholders.
- Run Gitleaks against both Git history and the staged changes with redaction enabled. A clean scan is useful evidence, not a guarantee that arbitrary secrets cannot exist.
- If a real credential is ever published, revoke/rotate it immediately. Removing it from the newest file does not remove it from Git history.
- GitHub Actions has read-only repository permissions. The supplied workflow needs no repository secrets and does not provision cloud services.
- Every push/PR runs Gitleaks over the full checked-out history using a pinned version and SHA-256-verified release binary. Fix a failing scan before merging further changes; an after-push check cannot undo disclosure that already occurred.

Do not post a security finding containing a live credential in a public issue. Use the repository's private security reporting channel if enabled, or contact the maintainer privately.

See [the focused security review](docs/UI-POLISH-AND-SECURITY.md) for the existing checks and deployment limitations.
