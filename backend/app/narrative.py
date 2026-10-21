"""Reviewed templates, provider orchestration, and safe fallback.

The provider selects a template and cites exact facts. It does not write the
football prose; the reviewed renderers below do. This keeps the first version
conservative and makes the factual wording testable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from .evidence import EvidenceFact, EvidencePacket, build_prompt
from .verification import (
    AUDIENCE_MODES,
    TemplateSpec,
    audit_rendered_narrative,
    verify_candidate,
)


CAVEATS = {
    "descriptive_only": (
        "Descriptive statistics only; no causal or tactical conclusion is implied."
    )
}

TEMPLATE_SPECS = {
    "casual_form": TemplateSpec(
        template_id="casual_form",
        modes=("casual",),
        required_metrics=(
            "possession_percentage",
            "shots",
            "pass_accuracy_percentage",
        ),
    ),
    "casual_workrate": TemplateSpec(
        template_id="casual_workrate",
        modes=("casual",),
        required_metrics=("recoveries", "possession_percentage"),
    ),
    "analyst_form": TemplateSpec(
        template_id="analyst_form",
        modes=("analyst",),
        required_metrics=(
            "possession_percentage",
            "shots",
            "shots_on_target",
            "passes_completed",
            "passes_attempted",
            "pass_accuracy_percentage",
            "recoveries",
        ),
    ),
    "analyst_workrate": TemplateSpec(
        template_id="analyst_workrate",
        modes=("analyst",),
        required_metrics=(
            "recoveries",
            "possession_percentage",
            "passes_completed",
            "passes_attempted",
            "pass_accuracy_percentage",
        ),
    ),
    "generic_fact": TemplateSpec(
        template_id="generic_fact",
        modes=("casual", "analyst"),
        required_metrics=(),
        allow_any_single_metric=True,
    ),
}

MODE_TEMPLATES = {
    "casual": ("casual_form", "casual_workrate"),
    "analyst": ("analyst_form", "analyst_workrate"),
}

FACT_PRIORITY = (
    "possession_percentage",
    "shots",
    "shots_on_target",
    "passes_completed",
    "passes_attempted",
    "pass_accuracy_percentage",
    "recoveries",
    "goals",
)


class NarrativeProvider(Protocol):
    """Minimal interface for a real or local narrative provider."""

    def generate(self, prompt: str) -> str:
        """Return a JSON string containing only a template selection and claims."""


@dataclass(frozen=True)
class NarrativeText:
    headline: str
    explanation: str


def _generic_fact(packet: EvidencePacket) -> EvidenceFact:
    """Choose one deterministic fallback fact when no full template fits."""
    for metric in FACT_PRIORITY:
        fact = packet.fact_by_metric(packet.focus_team, metric)
        if fact is not None:
            return fact
    team_facts = packet.facts_for_team(packet.focus_team)
    if not team_facts:
        raise ValueError("No facts are available for the focus team")
    return team_facts[0]


def choose_template(packet: EvidencePacket, audience_mode: str) -> str:
    """Select the most detailed available reviewed template for the mode."""
    if audience_mode not in AUDIENCE_MODES:
        raise ValueError("audience_mode must be 'casual' or 'analyst'")
    for template_id in MODE_TEMPLATES[audience_mode]:
        spec = TEMPLATE_SPECS[template_id]
        if all(
            packet.fact_by_metric(packet.focus_team, metric) is not None
            for metric in spec.required_metrics
        ):
            return template_id
    return "generic_fact"


def _claim_facts_for_template(
    packet: EvidencePacket, template_id: str
) -> tuple[EvidenceFact, ...]:
    spec = TEMPLATE_SPECS[template_id]
    if spec.allow_any_single_metric:
        return (_generic_fact(packet),)

    facts: list[EvidenceFact] = []
    for metric in spec.required_metrics:
        fact = packet.fact_by_metric(packet.focus_team, metric)
        if fact is None:
            raise ValueError(f"Template {template_id} requires unavailable {metric}")
        facts.append(fact)
    return tuple(facts)


def build_candidate_payload(
    packet: EvidencePacket, audience_mode: str, template_id: str
) -> dict[str, Any]:
    """Build the exact structured payload expected from a provider."""
    claim_facts = _claim_facts_for_template(packet, template_id)
    claims = [
        {
            "evidence_id": fact.evidence_id,
            "metric": fact.metric,
            "team_id": fact.team_id,
            "value": fact.value,
        }
        for fact in claim_facts
    ]
    return {
        "template_id": template_id,
        "audience_mode": audience_mode,
        "language": "en",
        "caveat_id": "descriptive_only",
        "claims": claims,
        "evidence_ids": [fact.evidence_id for fact in claim_facts],
    }


def _format_with_unit(fact: EvidenceFact) -> str:
    if fact.unit == "%":
        return f"{fact.value}%"
    return f"{fact.value} {fact.unit}"


def _format_count(
    fact: EvidenceFact, singular: str, plural: str | None = None
) -> str:
    noun = singular if fact.value == 1 else (plural or f"{singular}s")
    return f"{fact.value} {noun}"


def _render_casual_form(
    facts: dict[str, EvidenceFact], team_name: str
) -> tuple[str, str]:
    possession = facts["possession_percentage"]
    shots = facts["shots"]
    accuracy = facts["pass_accuracy_percentage"]
    headline = f"{team_name}: possession watch"
    explanation = (
        f"{team_name} have had {_format_with_unit(possession)} possession, "
        f"taken {_format_count(shots, 'shot')}, and completed "
        f"{_format_with_unit(accuracy)} of their passes."
    )
    return headline, explanation


def _render_casual_workrate(
    facts: dict[str, EvidenceFact], team_name: str
) -> tuple[str, str]:
    recoveries = facts["recoveries"]
    possession = facts["possession_percentage"]
    times = "time" if recoveries.value == 1 else "times"
    headline = f"{team_name}: winning the ball back"
    explanation = (
        f"{team_name} have won the ball back {recoveries.value} {times} and had "
        f"{_format_with_unit(possession)} possession."
    )
    return headline, explanation


def _render_analyst_form(
    facts: dict[str, EvidenceFact], team_name: str
) -> tuple[str, str]:
    possession = facts["possession_percentage"]
    shots = facts["shots"]
    on_target = facts["shots_on_target"]
    completed = facts["passes_completed"]
    attempted = facts["passes_attempted"]
    accuracy = facts["pass_accuracy_percentage"]
    recoveries = facts["recoveries"]
    headline = f"{team_name}: statistical snapshot"
    explanation = (
        f"{team_name}: {_format_with_unit(possession)} possession; "
        f"{_format_count(shots, 'shot')} ({on_target.value} on target); "
        f"{_format_with_unit(accuracy)} pass accuracy "
        f"({completed.value}/{attempted.value} passes); "
        f"{_format_count(recoveries, 'recovery', 'recoveries')}."
    )
    return headline, explanation


def _render_analyst_workrate(
    facts: dict[str, EvidenceFact], team_name: str
) -> tuple[str, str]:
    possession = facts["possession_percentage"]
    recoveries = facts["recoveries"]
    completed = facts["passes_completed"]
    attempted = facts["passes_attempted"]
    accuracy = facts["pass_accuracy_percentage"]
    headline = f"{team_name}: workrate breakdown"
    explanation = (
        f"{team_name}: {_format_with_unit(possession)} possession; "
        f"{_format_count(recoveries, 'recovery', 'recoveries')}; "
        f"{_format_with_unit(accuracy)} pass accuracy "
        f"({completed.value}/{attempted.value} passes)."
    )
    return headline, explanation


def _render_generic_fact(
    facts: dict[str, EvidenceFact], team_name: str
) -> tuple[str, str]:
    fact = next(iter(facts.values()))
    headline = f"{team_name}: {fact.label}"
    value = f"{fact.value}%" if fact.unit == "%" else str(fact.value)
    explanation = f"{team_name}: {fact.label} = {value}."
    return headline, explanation


RENDERERS = {
    "casual_form": _render_casual_form,
    "casual_workrate": _render_casual_workrate,
    "analyst_form": _render_analyst_form,
    "analyst_workrate": _render_analyst_workrate,
    "generic_fact": _render_generic_fact,
}


def render_template(
    template_id: str, claim_facts: tuple[EvidenceFact, ...]
) -> NarrativeText:
    """Render reviewed prose from already-verified facts."""
    if not claim_facts:
        raise ValueError("At least one verified fact is required")
    facts_by_metric = {fact.metric: fact for fact in claim_facts}
    team_name = claim_facts[0].team_name
    headline, explanation = RENDERERS[template_id](facts_by_metric, team_name)
    return NarrativeText(headline=headline, explanation=explanation)


def _canonical_claims(
    claim_facts: tuple[EvidenceFact, ...]
) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": fact.evidence_id,
            "metric": fact.metric,
            "team_id": fact.team_id,
            "value": fact.value,
        }
        for fact in claim_facts
    ]


def _provider_name(provider: NarrativeProvider) -> str:
    return getattr(provider, "name", provider.__class__.__name__)


def _make_result(
    *,
    packet: EvidencePacket,
    audience_mode: str,
    provider: NarrativeProvider,
    template_id: str,
    narrative: NarrativeText,
    claim_facts: tuple[EvidenceFact, ...],
    caveat: str,
    status: str,
    fallback_reason: str | None,
) -> dict[str, Any]:
    return {
        "match_id": packet.match_id,
        "template_id": template_id,
        "headline": narrative.headline,
        "explanation": narrative.explanation,
        "claims": _canonical_claims(claim_facts),
        "evidence_ids": [fact.evidence_id for fact in claim_facts],
        "caveat": caveat,
        "audience_mode": audience_mode,
        "language": "en",
        "status": status,
        "provider": _provider_name(provider),
        "fallback_reason": fallback_reason,
    }


def _minimal_fallback_result(
    packet: EvidencePacket,
    audience_mode: str,
    provider: NarrativeProvider,
    reason: str,
) -> dict[str, Any]:
    fact = _generic_fact(packet)
    value = f"{fact.value}%" if fact.unit == "%" else str(fact.value)
    narrative = NarrativeText(
        headline=f"{fact.team_name}: {fact.label}",
        explanation=f"{fact.team_name}: {fact.label} = {value}.",
    )
    return _make_result(
        packet=packet,
        audience_mode=audience_mode,
        provider=provider,
        template_id="generic_fact",
        narrative=narrative,
        claim_facts=(fact,),
        caveat=CAVEATS["descriptive_only"],
        status="fallback",
        fallback_reason=reason,
    )


def _fallback(
    packet: EvidencePacket,
    audience_mode: str,
    provider: NarrativeProvider,
    reason: str,
) -> dict[str, Any]:
    """Build a deterministic, evidence-only result after provider failure."""
    try:
        template_id = choose_template(packet, audience_mode)
        candidate = build_candidate_payload(packet, audience_mode, template_id)
        verification = verify_candidate(
            candidate,
            packet,
            audience_mode,
            TEMPLATE_SPECS,
            CAVEATS,
        )
        if verification.ok:
            narrative = render_template(template_id, verification.claim_facts)
            audit_errors = audit_rendered_narrative(
                narrative.headline,
                narrative.explanation,
                verification.claim_facts,
                packet.team_names,
            )
            if not audit_errors:
                return _make_result(
                    packet=packet,
                    audience_mode=audience_mode,
                    provider=provider,
                    template_id=template_id,
                    narrative=narrative,
                    claim_facts=verification.claim_facts,
                    caveat=CAVEATS["descriptive_only"],
                    status="fallback",
                    fallback_reason=reason,
                )
    except Exception:
        # Fall through to the smallest possible evidence-only response.
        pass
    return _minimal_fallback_result(packet, audience_mode, provider, reason)


def generate_insight(
    packet: EvidencePacket,
    audience_mode: str,
    provider: NarrativeProvider,
) -> dict[str, Any]:
    """Generate a verified insight or return a safe factual fallback."""
    if audience_mode not in AUDIENCE_MODES:
        raise ValueError("audience_mode must be 'casual' or 'analyst'")

    allowed_templates = tuple(MODE_TEMPLATES[audience_mode]) + ("generic_fact",)
    prompt = build_prompt(packet, audience_mode, allowed_templates)

    try:
        raw_response = provider.generate(prompt)
    except TimeoutError:
        return _fallback(packet, audience_mode, provider, "timeout")
    except Exception:
        return _fallback(packet, audience_mode, provider, "service_error")

    if not isinstance(raw_response, str):
        return _fallback(packet, audience_mode, provider, "invalid_json")

    try:
        candidate = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError):
        return _fallback(packet, audience_mode, provider, "invalid_json")

    verification = verify_candidate(
        candidate,
        packet,
        audience_mode,
        TEMPLATE_SPECS,
        CAVEATS,
    )
    if not verification.ok:
        return _fallback(packet, audience_mode, provider, "verification_failed")

    template_id = candidate["template_id"]
    narrative = render_template(template_id, verification.claim_facts)
    audit_errors = audit_rendered_narrative(
        narrative.headline,
        narrative.explanation,
        verification.claim_facts,
        packet.team_names,
    )
    if audit_errors:
        return _fallback(packet, audience_mode, provider, "verification_failed")

    return _make_result(
        packet=packet,
        audience_mode=audience_mode,
        provider=provider,
        template_id=template_id,
        narrative=narrative,
        claim_facts=verification.claim_facts,
        caveat=CAVEATS[candidate["caveat_id"]],
        status="verified",
        fallback_reason=None,
    )
