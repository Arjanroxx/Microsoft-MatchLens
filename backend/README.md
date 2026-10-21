# MatchLens AI/explainability prototype

This backend package turns structured MatchLens team statistics into one
evidence-backed football insight. It is intentionally small and uses only the
Python standard library.

**Important:** the included provider is a deterministic local demonstration and
test provider. It is **not** a real AI model, and this step does not connect to
Microsoft AI Foundry.

## What it does

```text
summary.json or calculate_statistics() snapshot
        -> validated evidence packet
        -> provider selects an allowlisted template and exact claims
        -> strict verification
        -> reviewed deterministic template
        -> numeric and language audits
        -> verified insight or factual fallback
```

The provider is not allowed to write the headline or explanation. It may only
select a reviewed template and cite exact facts. This keeps the first version
conservative and makes unsupported wording easy to reject.

## Run the local demo

From the repository root:

```powershell
python -B -m backend.app.insights `
  --input data/examples/short-match/summary.json `
  --team home `
  --mode casual
```

For the analyst style:

```powershell
python -B -m backend.app.insights `
  --input data/examples/short-match/summary.json `
  --team home `
  --mode analyst
```

For a live-style snapshot returned by `calculate_statistics()`, which has no
`match_id`, pass one explicitly if needed:

```powershell
python -B -m backend.app.insights `
  --input path/to/snapshot.json `
  --match-id demo-001 `
  --team away
```

## Output fields

| Field | Meaning |
|---|---|
| `match_id` | Match identifier when available; otherwise `null`. |
| `template_id` | The reviewed wording template selected by the provider. |
| `headline`, `explanation` | Deterministic text rendered from verified facts. |
| `claims` | Exact evidence facts used by the text. |
| `evidence_ids` | Exactly the evidence IDs referenced by accepted claims. |
| `caveat` | Fixed descriptive-only caveat. |
| `audience_mode` | `casual` or `analyst`. |
| `language` | Currently `en`. |
| `status` | `verified` or `fallback`. |
| `provider` | Provider name; the local provider reports `local-demo`. |
| `fallback_reason` | `null` for verified output, otherwise a failure category. |

## Verification rules

- Candidate fields must match the required schema exactly; free-form prose is
  rejected.
- Each claim must match the original evidence packet by evidence ID, metric,
  team ID, value, and JSON/Python numeric type.
- `evidence_ids` must exactly match the IDs referenced by accepted claims,
  with no extra, missing, or duplicate IDs.
- The selected template must require exactly the accepted claim set.
- Rendered statistical numbers must be backed by accepted claims. Team-name
  digits are masked so harmless names are not rejected.
- A conservative phrase guard rejects accidental causal, historical,
  comparative, or tactical wording.
- Any failure produces a deterministic fallback built only from available
  facts.

## Run the tests

```powershell
python -B -m unittest discover -s backend/tests -t . -p "test_*.py" -v
```

The tests cover valid casual/analyst output, wrong values and types, exact
evidence-ID matching, unsupported interpretations, malformed JSON, missing
fields, provider exceptions, timeouts, numeric auditing, and the checked-in
sample match.

## Data-source notes

- The reader uses only `teams.home` and `teams.away`.
- It does not use `final_score`, pooled top-level metrics, or
  `evaluation-only.json`.
- Missing optional fields are omitted, never replaced with zero.
- Malformed values raise `EvidenceError` instead of being silently converted.
- The checked-in `summary.json` includes `match_id`; snapshots returned by
  `calculate_statistics()` do not.

## Limitations

- The local provider is not an AI model.
- The first version produces descriptive snapshots, not tactical conclusions.
- Strict exact-value verification may reject rounded model output; the pipeline
  then returns a safe fallback.
- No live streaming, overlay scheduling, or Foundry integration is included.
- Frontend files and the existing simulator are untouched.
