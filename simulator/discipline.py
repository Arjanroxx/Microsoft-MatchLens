"""Geometry-supported challenge decisions and selected Law 12 restart rules.

Effort, timing and technique are seeded action controls, not sampled foul/card
labels. Outcomes and sanctions are deterministic from this action evidence.
"""
from simulator.pitch import distance, point


def in_penalty_area(location, defending_team, period):
    left = (defending_team == "home") == (period == 1)
    return ((0 <= location["x_m"] <= 16.5 if left else 88.5 <= location["x_m"] <= 105)
            and 13.84 <= location["y_m"] <= 54.16)


def resolve_challenge(ball, tackler, effort, timing_error_ms, technique):
    gap = distance(ball, tackler)
    if technique not in ("standing_tackle", "raised_boot") or not 0 <= effort <= 1:
        raise ValueError("Invalid challenge controls")
    if gap > 2.5:
        return {"outcome": "missed", "offence": None, "severity": None, "card": None}
    if technique == "raised_boot" and gap > .8 and effort >= .65:
        return {"outcome": "foul", "offence": "dangerous_play_without_contact", "severity": "reckless" if effort >= .9 else "dangerous", "card": "yellow" if effort >= .9 else None}
    if gap <= 1.5 and timing_error_ms > 80:
        severity = "excessive" if effort >= .97 and timing_error_ms >= 320 else "reckless" if effort >= .8 and timing_error_ms >= 220 else "careless"
        return {"outcome": "foul", "offence": "late_contact_challenge", "severity": severity,
                "card": "red" if severity == "excessive" else "yellow" if severity == "reckless" else None}
    if gap <= .8 and timing_error_ms <= 80:
        return {"outcome": "won", "offence": None, "severity": None, "card": None}
    return {"outcome": "missed", "offence": None, "severity": None, "card": None}


def foul_restart(location, offender_team, period, offence):
    team = "away" if offender_team == "home" else "home"
    indirect = offence == "dangerous_play_without_contact"
    kind = "indirect_free_kick" if indirect else "penalty" if in_penalty_area(location, offender_team, period) else "direct_free_kick"
    at = point(location["x_m"], location["y_m"])
    if kind == "penalty":
        at = point(11 if (offender_team == "home") == (period == 1) else 94, 34)
    elif indirect:
        # Attacking indirect free kick within the opponents' goal area is
        # taken on its parallel goal-area line, not on the goal line.
        left = (offender_team == "home") == (period == 1)
        goal_area = (at["x_m"] <= 5.5 if left else at["x_m"] >= 99.5) and 24.84 <= at["y_m"] <= 43.16
        if goal_area:
            at["x_m"] = 5.5 if left else 99.5
    return {"type": kind, "team_id": team, "location": at, "offence_location": location.copy()}


def separation_target(pos, centre, minimum):
    """Nearest legal in-field point on a distance circle, including near edges."""
    import math
    choices = []
    for degree in range(0, 360, 5):
        angle = math.radians(degree)
        target = point(centre["x_m"]+(minimum+.1)*math.cos(angle), centre["y_m"]+(minimum+.1)*math.sin(angle))
        if distance(target, centre) >= minimum:
            choices.append(target)
    return min(choices, key=lambda target: distance(pos, target))
