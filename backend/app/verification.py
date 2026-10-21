"""Deterministic validation of structured narrative candidates.

The verifier is intentionally strict. A candidate may select a reviewed
template and copy exact evidence facts, but it may not supply free-form prose.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .evidence import EvidenceFact, EvidencePacket


CANDIDATE_KEYS = frozenset(
    {
        "template_id",
        "audience_mode",
        "language",
        "caveat_id",
        "claims",
        "evidence_ids",
    }
)
CLAIM_KEYS = frozenset({"evidence_id", "metric", "team_id", "value"})
AUDIENCE_MODES = ("casual", "analyst")

_NUMBER_PATTERN = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
_UNSUPPORTED_PHRASES = (
    "because",
    "caused",
    "therefore",
    "proves",
    "shows that",
    "tactical",
    "tactic",
    "pressing",
    "injury",
    "injured",
    "career",
    "last season",
    "history",
    "historical",
    "transfer",
    "manager",
    "coach",
    "substitution",
    "more than",
    "fewer than",
    "better than",
    "worse than",
    "compared with",
    "than",
)


@dataclass(frozen=True)
class TemplateSpec:
    """Metadata needed to verify a provider's template selection."""

    template_id: str
    modes: tuple[str, ...]
    required_metrics: tuple[str, ...]
    allow_any_single_metric: bool = False


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    errors: tuple[str, ...]
    claim_facts: tuple[EvidenceFact, ...] = ()


def _is_number(value: Any) -> bool:
    """Return True for JSON numbers, but never for booleans."""
    return type(value) is int or type(value) is float


def _mask_team_names(text: str, team_names: tuple[str, ...]) -> str:
    """Remove team names before auditing numbers and language.

    This prevents harmless digits or words inside a synthetic club name from
    being treated as statistical claims or unsupported commentary.
    """
    masked = text
    for name in sorted(team_names, key=len, reverse=True):
        masked = masked.replace(name, " ")
    return masked


def _expected_facts(
    packet: EvidencePacket, spec: TemplateSpec
) -> tuple[EvidenceFact, ...] | None:
    """Return the exact facts a template requires, or None if unavailable."""
    facts: list[EvidenceFact] = []
    for metric in spec.required_metrics:
        fact = packet.fact_by_metric(packet.focus_team, metric)
        if fact is None:
            return None
        facts.append(fact)
    return tuple(facts)


def verify_candidate(
    candidate: Any,
    packet: EvidencePacket,
    audience_mode: str,
    templates: Mapping[str, TemplateSpec],
    caveats: Mapping[str, str],
) -> VerificationResult:
    """Validate a candidate against the original evidence packet.

    Correct numbers alone are not enough: the template, metric, team, value
    type, claim set, and evidence-ID list must all agree exactly.
    """
    errors: list[str] = []

    if not isinstance(candidate, Mapping):
        return VerificationResult(False, ("candidate must be a JSON object",))
    if set(candidate.keys()) != CANDIDATE_KEYS:
        errors.append("candidate fields do not match the required schema")

    template_id = candidate.get("template_id")
    if not isinstance(template_id, str):
        errors.append("template_id must be a string")
        template_id = ""
    spec = templates.get(template_id)
    if spec is None:
        errors.append(f"unknown template_id: {template_id!r}")

    candidate_mode = candidate.get("audience_mode")
    if not isinstance(candidate_mode, str) or candidate_mode not in AUDIENCE_MODES:
        errors.append("audience_mode must be 'casual' or 'analyst'")
    elif candidate_mode != audience_mode:
        errors.append("audience_mode does not match the requested mode")
    elif spec is not None and candidate_mode not in spec.modes:
        errors.append("template_id does not support the requested audience_mode")

    if candidate.get("language") != "en":
        errors.append("language must be 'en'")

    caveat_id = candidate.get("caveat_id")
    if not isinstance(caveat_id, str) or caveat_id not in caveats:
        errors.append("caveat_id is not allowed")

    claims = candidate.get("claims")
    evidence_ids = candidate.get("evidence_ids")
    if not isinstance(claims, list) or not claims:
        errors.append("claims must be a non-empty list")
        claims = []
    if not isinstance(evidence_ids, list) or not evidence_ids:
        errors.append("evidence_ids must be a non-empty list")
        evidence_ids = []

    claim_facts: list[EvidenceFact] = []
    seen_evidence_ids: set[str] = set()

    for index, claim in enumerate(claims):
        if not isinstance(claim, Mapping):
            errors.append(f"claims[{index}] must be an object")
            continue
        if set(claim.keys()) != CLAIM_KEYS:
            errors.append(f"claims[{index}] fields do not match the required schema")
            continue

        evidence_id = claim.get("evidence_id")
        metric = claim.get("metric")
        team_id = claim.get("team_id")
        value = claim.get("value")

        if not isinstance(evidence_id, str):
            errors.append(f"claims[{index}].evidence_id must be a string")
            continue
        if not isinstance(metric, str):
            errors.append(f"claims[{index}].metric must be a string")
            continue
        if not isinstance(team_id, str):
            errors.append(f"claims[{index}].team_id must be a string")
            continue
        if not _is_number(value):
            errors.append(f"claims[{index}].value must be a JSON number")
            continue
        if evidence_id in seen_evidence_ids:
            errors.append(f"duplicate claim evidence_id: {evidence_id}")
            continue
        seen_evidence_ids.add(evidence_id)

        fact = packet.fact(evidence_id)
        if fact is None:
            errors.append(f"unknown evidence_id: {evidence_id}")
            continue
        if metric != fact.metric:
            errors.append(f"claims[{index}].metric does not match the evidence")
        if team_id != fact.team_id:
            errors.append(f"claims[{index}].team_id does not match the evidence")
        if fact.team_id != packet.focus_team:
            errors.append(f"claims[{index}] does not belong to the focus team")

        if fact.value_type == "integer":
            if type(value) is not int:
                errors.append(f"claims[{index}].value must be an integer")
        elif fact.value_type == "number":
            if type(value) is not float:
                errors.append(f"claims[{index}].value must be a number")
        else:
            errors.append(f"claims[{index}] has an unknown evidence type")

        if value != fact.value:
            errors.append(f"claims[{index}].value does not match the evidence")

        claim_facts.append(fact)

    if any(not isinstance(item, str) for item in evidence_ids):
        errors.append("evidence_ids must contain only strings")
    else:
        if len(evidence_ids) != len(set(evidence_ids)):
            errors.append("evidence_ids contains duplicates")
        if set(evidence_ids) != seen_evidence_ids:
            errors.append("evidence_ids must exactly match the claim evidence IDs")

    if spec is not None:
        if spec.allow_any_single_metric:
            if len(claim_facts) != 1:
                errors.append("generic_fact requires exactly one claim")
        else:
            expected = _expected_facts(packet, spec)
            if expected is None:
                errors.append("the selected template requires unavailable evidence")
            else:
                expected_ids = {fact.evidence_id for fact in expected}
                if seen_evidence_ids != expected_ids:
                    errors.append(
                        "claims do not exactly match the selected template's "
                        "required facts"
                    )

    return VerificationResult(not errors, tuple(errors), tuple(claim_facts))


def audit_numeric_tokens(
    text: str,
    claim_facts: tuple[EvidenceFact, ...],
    team_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Check that statistical numbers in rendered text are claimed.

    Team names are masked so harmless digits in names are not rejected. The
    audit does not try to interpret prose; the deterministic templates are the
    primary control over wording.
    """
    masked = _mask_team_names(text, team_names)
    allowed_values = [fact.value for fact in claim_facts]
    errors: list[str] = []
    seen: set[str] = set()

    for match in _NUMBER_PATTERN.finditer(masked):
        token = match.group(0)
        if token in seen:
            continue
        seen.add(token)
        parsed = float(token) if "." in token else int(token)
        if not any(parsed == value for value in allowed_values):
            errors.append(f"unsupported numeric value in narrative: {token}")

    return tuple(errors)


def audit_language(
    text: str, team_names: tuple[str, ...]
) -> tuple[str, ...]:
    """Reject a small set of unsupported causal, historical, and tactical terms."""
    masked = _mask_team_names(text, team_names).lower()
    errors: list[str] = []
    for phrase in _UNSUPPORTED_PHRASES:
        if phrase in masked:
            errors.append(f"unsupported language in narrative: {phrase!r}")
    return tuple(errors)


def audit_rendered_narrative(
    headline: str,
    explanation: str,
    claim_facts: tuple[EvidenceFact, ...],
    team_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Run the numeric and language audits over the rendered football text."""
    errors: list[str] = []
    for text in (headline, explanation):
        errors.extend(audit_numeric_tokens(text, claim_facts, team_names))
        errors.extend(audit_language(text, team_names))
    return tuple(dict.fromkeys(errors))
