"""Build a validated evidence packet from MatchLens team statistics.

The reader trusts only the per-team structure under ``teams``. It deliberately
does not use final scores, pooled metrics, or evaluation-only simulator data.
Missing optional values are omitted; they are never replaced with zero.
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class EvidenceError(ValueError):
    """Raised when match statistics are missing or malformed."""


@dataclass(frozen=True)
class EvidenceFact:
    """One inspectable statistic with a stable evidence ID."""

    evidence_id: str
    metric: str
    label: str
    team_id: str
    team_name: str
    value: int | float
    value_type: str
    unit: str


@dataclass(frozen=True)
class EvidencePacket:
    """The only facts an insight is allowed to use."""

    match_id: str | None
    focus_team: str
    team_names: tuple[str, ...]
    facts: tuple[EvidenceFact, ...]

    def fact(self, evidence_id: str) -> EvidenceFact | None:
        """Return one fact by evidence ID, or None when it is absent."""
        for fact in self.facts:
            if fact.evidence_id == evidence_id:
                return fact
        return None

    def fact_by_metric(self, team_id: str, metric: str) -> EvidenceFact | None:
        """Return one team metric, or None when that metric is unavailable."""
        for fact in self.facts:
            if fact.team_id == team_id and fact.metric == metric:
                return fact
        return None

    def facts_for_team(self, team_id: str) -> tuple[EvidenceFact, ...]:
        """Return all facts for one team."""
        return tuple(fact for fact in self.facts if fact.team_id == team_id)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceError(f"{path} must be an object")
    return value


def _optional_number(
    container: Mapping[str, Any],
    key: str,
    path: str,
    *,
    integer: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
) -> int | float | None:
    """Read an optional number without coercing strings or booleans."""
    value = container.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{path} must be a number")
    if integer and type(value) is not int:
        raise EvidenceError(f"{path} must be an integer")
    if not math.isfinite(value):
        raise EvidenceError(f"{path} must be finite")
    if minimum is not None and value < minimum:
        raise EvidenceError(f"{path} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise EvidenceError(f"{path} must be at most {maximum}")
    return value


def _value_type(value: int | float) -> str:
    return "integer" if type(value) is int else "number"


def _team_name(team: Mapping[str, Any], team_id: str) -> str:
    name = team.get("name")
    if not isinstance(name, str) or not name.strip():
        raise EvidenceError(f"teams.{team_id}.name must be a non-empty string")
    return name.strip()


def _validate_team_id(team: Mapping[str, Any], team_id: str) -> None:
    if "team_id" not in team:
        return
    declared = team["team_id"]
    if not isinstance(declared, str) or declared != team_id:
        raise EvidenceError(
            f"teams.{team_id}.team_id must be the string {team_id!r}"
        )


def _add_fact(
    facts: list[EvidenceFact],
    *,
    team_id: str,
    team_name: str,
    metric: str,
    label: str,
    value: int | float | None,
    unit: str,
) -> None:
    if value is None:
        return
    facts.append(
        EvidenceFact(
            evidence_id=f"ev-{team_id}-{metric}",
            metric=metric,
            label=label,
            team_id=team_id,
            team_name=team_name,
            value=value,
            value_type=_value_type(value),
            unit=unit,
        )
    )


def _team_facts(
    team: Mapping[str, Any], team_id: str, team_name: str
) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []

    goals = _optional_number(
        team, "goals", f"teams.{team_id}.goals", integer=True, minimum=0
    )
    _add_fact(
        facts,
        team_id=team_id,
        team_name=team_name,
        metric="goals",
        label="goals",
        value=goals,
        unit="goals",
    )

    shots_value = team.get("shots")
    if shots_value is not None:
        shots = _mapping(shots_value, f"teams.{team_id}.shots")
        total = _optional_number(
            shots, "total", f"teams.{team_id}.shots.total", integer=True, minimum=0
        )
        on_target = _optional_number(
            shots,
            "on_target",
            f"teams.{team_id}.shots.on_target",
            integer=True,
            minimum=0,
        )
        if total is not None and on_target is not None and on_target > total:
            raise EvidenceError(
                f"teams.{team_id}.shots.on_target cannot exceed shots.total"
            )
        _add_fact(
            facts,
            team_id=team_id,
            team_name=team_name,
            metric="shots",
            label="shots",
            value=total,
            unit="shots",
        )
        _add_fact(
            facts,
            team_id=team_id,
            team_name=team_name,
            metric="shots_on_target",
            label="shots on target",
            value=on_target,
            unit="shots on target",
        )

    passes_value = team.get("passes")
    if passes_value is not None:
        passes = _mapping(passes_value, f"teams.{team_id}.passes")
        attempted = _optional_number(
            passes,
            "attempted",
            f"teams.{team_id}.passes.attempted",
            integer=True,
            minimum=0,
        )
        completed = _optional_number(
            passes,
            "completed",
            f"teams.{team_id}.passes.completed",
            integer=True,
            minimum=0,
        )
        accuracy = _optional_number(
            passes,
            "accuracy_percentage",
            f"teams.{team_id}.passes.accuracy_percentage",
            minimum=0,
            maximum=100,
        )
        if attempted is not None and completed is not None and completed > attempted:
            raise EvidenceError(
                f"teams.{team_id}.passes.completed cannot exceed passes.attempted"
            )
        _add_fact(
            facts,
            team_id=team_id,
            team_name=team_name,
            metric="passes_completed",
            label="completed passes",
            value=completed,
            unit="passes",
        )
        _add_fact(
            facts,
            team_id=team_id,
            team_name=team_name,
            metric="passes_attempted",
            label="pass attempts",
            value=attempted,
            unit="passes",
        )
        _add_fact(
            facts,
            team_id=team_id,
            team_name=team_name,
            metric="pass_accuracy_percentage",
            label="pass accuracy",
            value=accuracy,
            unit="%",
        )

    recoveries = _optional_number(
        team,
        "recoveries",
        f"teams.{team_id}.recoveries",
        integer=True,
        minimum=0,
    )
    _add_fact(
        facts,
        team_id=team_id,
        team_name=team_name,
        metric="recoveries",
        label="recoveries",
        value=recoveries,
        unit="recoveries",
    )

    possession_value = team.get("possession")
    if possession_value is not None:
        possession = _mapping(possession_value, f"teams.{team_id}.possession")
        percentage = _optional_number(
            possession,
            "percentage",
            f"teams.{team_id}.possession.percentage",
            minimum=0,
            maximum=100,
        )
        _add_fact(
            facts,
            team_id=team_id,
            team_name=team_name,
            metric="possession_percentage",
            label="possession",
            value=percentage,
            unit="%",
        )

    return facts


def _resolve_match_id(
    summary: Mapping[str, Any], match_id: str | None
) -> str | None:
    if match_id is not None:
        if not isinstance(match_id, str) or not match_id.strip():
            raise EvidenceError("match_id override must be a non-empty string")
        return match_id.strip()

    value = summary.get("match_id")
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError("match_id must be a non-empty string when present")
    return value.strip()


def build_evidence_packet(
    summary: Mapping[str, Any],
    focus_team: str = "home",
    match_id: str | None = None,
) -> EvidencePacket:
    """Validate structured statistics and return an immutable evidence packet.

    ``summary`` may be a checked-in ``summary.json`` or the dictionary returned
    by ``simulator.statistics.calculate_statistics``. The latter has no
    ``match_id``, so callers can pass one explicitly when needed.
    """
    summary_mapping = _mapping(summary, "summary")
    teams = _mapping(summary_mapping.get("teams"), "summary.teams")
    for team_id in ("home", "away"):
        if team_id not in teams:
            raise EvidenceError(f"summary.teams.{team_id} is required")
    if focus_team not in ("home", "away"):
        raise EvidenceError("focus_team must be 'home' or 'away'")

    resolved_match_id = _resolve_match_id(summary_mapping, match_id)
    facts: list[EvidenceFact] = []
    team_names: list[str] = []

    for team_id in ("home", "away"):
        team = _mapping(teams[team_id], f"teams.{team_id}")
        _validate_team_id(team, team_id)
        team_name = _team_name(team, team_id)
        team_names.append(team_name)
        facts.extend(_team_facts(team, team_id, team_name))

    if not facts:
        raise EvidenceError("No usable team statistics were found")
    if not any(fact.team_id == focus_team for fact in facts):
        raise EvidenceError(f"No usable statistics were found for {focus_team}")

    return EvidencePacket(
        match_id=resolved_match_id,
        focus_team=focus_team,
        team_names=tuple(team_names),
        facts=tuple(facts),
    )


def build_prompt(
    packet: EvidencePacket,
    audience_mode: str,
    allowed_template_ids: tuple[str, ...] | list[str],
) -> str:
    """Build a constrained prompt for a future real model provider.

    The first-version provider may only select a template and cite exact facts.
    It is explicitly told not to write prose or add unsupported context.
    """
    facts = [
        {
            "evidence_id": fact.evidence_id,
            "metric": fact.metric,
            "label": fact.label,
            "team_id": fact.team_id,
            "team_name": fact.team_name,
            "value": fact.value,
            "value_type": fact.value_type,
            "unit": fact.unit,
        }
        for fact in packet.facts
    ]
    request = {
        "task": "Select one reviewed template and cite the exact evidence it uses.",
        "focus_team": packet.focus_team,
        "match_id": packet.match_id,
        "audience_mode": audience_mode,
        "allowed_template_ids": list(allowed_template_ids),
        "required_output_fields": [
            "template_id",
            "audience_mode",
            "language",
            "caveat_id",
            "claims",
            "evidence_ids",
        ],
        "claim_fields": ["evidence_id", "metric", "team_id", "value"],
        "rules": [
            "Return one JSON object only.",
            "Do not write a headline, explanation, or free-form interpretation.",
            "Select template_id only from allowed_template_ids.",
            "Copy evidence_id, metric, team_id, and value exactly from the facts.",
            "Preserve each value's JSON type.",
            "evidence_ids must list exactly the evidence IDs used by claims, without duplicates.",
            "Use language 'en' and caveat_id 'descriptive_only'.",
            "Do not add comparisons, causes, history, tactics, or predictions.",
        ],
        "facts": facts,
    }
    return json.dumps(request, indent=2)
