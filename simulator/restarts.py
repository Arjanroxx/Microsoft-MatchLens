"""Auditable 2D whole-ball boundaries, restart awards and keeper contact model."""
import math

from simulator.pitch import distance, point

BALL_RADIUS_M = .11


def raw_point(x, y):
    """Ball coordinates may leave the field. Player coordinates still use point()."""
    return {"x_m": round(x, 6), "y_m": round(y, 6)}


def other(team):
    return "away" if team == "home" else "home"


def first_exit(start, aimed):
    """First whole-ball crossing along a segment; line touches remain in play.

    Simultaneous corner crossings use the touchline as a deterministic convention.
    Coordinates describe the ball centre and include its radius beyond the line.
    """
    candidates = []
    for axis, low, high, label in (("y_m", -BALL_RADIUS_M, 68 + BALL_RADIUS_M, "touchline"),
                                  ("x_m", -BALL_RADIUS_M, 105 + BALL_RADIUS_M, "goal_line")):
        delta = aimed[axis] - start[axis]
        for limit in (low, high):
            if delta and ((delta < 0 and aimed[axis] < limit <= start[axis]) or
                          (delta > 0 and aimed[axis] > limit >= start[axis])):
                fraction = (limit - start[axis]) / delta
                if 0 <= fraction <= 1:
                    at = raw_point(start["x_m"] + fraction * (aimed["x_m"] - start["x_m"]),
                                   start["y_m"] + fraction * (aimed["y_m"] - start["y_m"]))
                    candidates.append((fraction, 0 if label == "touchline" else 1, label, at))
    if not candidates:
        return None
    fraction, _, boundary, at = min(candidates)
    return {"fraction": fraction, "boundary": boundary, "location": at}


def award_restart(crossing, last_touch_team, last_touch_player, period):
    at, boundary = crossing["location"], crossing["boundary"]
    if boundary == "touchline":
        kind, team = "throw_in", other(last_touch_team)
        location = point(at["x_m"], 0 if at["y_m"] < 0 else 68)
    else:
        # Home defends x=0 in period 1 and x=105 in period 2.
        defending = "home" if (at["x_m"] < 0) == (period == 1) else "away"
        if last_touch_team == defending:
            kind, team = "corner_kick", other(defending)
            location = point(0 if at["x_m"] < 0 else 105, 0 if at["y_m"] < 34 else 68)
        else:
            kind, team = "goal_kick", defending
            location = point(5.5 if at["x_m"] < 0 else 99.5, 34)
    return {"type": kind, "team_id": team, "location": location,
            "last_touch_team_id": last_touch_team, "last_touch_player_id": last_touch_player}


def resolve_shot(start, aimed, keeper_position, speed_mps):
    """Contact at the keeper's goal-side plane, before any goal-line crossing.

    Reach uses available flight time and a 0.8m contact radius. A secure low-speed
    central contact is held; harder/stretch contacts are parried. No random save
    labels. This is a planar heuristic, not a calibrated keeper model.
    """
    crossing = first_exit(start, aimed)
    end = crossing["location"] if crossing else aimed
    goal = bool(crossing and crossing["boundary"] == "goal_line" and
                abs(end["y_m"] - 34) <= 3.66 - BALL_RADIUS_M)
    # An off-target ball cannot produce an on-target save in this model.
    contact = None
    if goal and aimed["x_m"] != start["x_m"]:
        u = (keeper_position["x_m"] - start["x_m"]) / (aimed["x_m"] - start["x_m"])
        if 0 < u < crossing["fraction"]:
            candidate = raw_point(keeper_position["x_m"], start["y_m"] + u * (aimed["y_m"] - start["y_m"]))
            seconds = distance(start, candidate) / speed_mps
            reach = .8 + 4.5 * max(0, seconds - .12)
            gap = distance(keeper_position, candidate)
            if gap <= reach:
                contact = candidate
                held = speed_mps <= 29 and gap <= max(.65, reach * .6)
                return {"end": contact, "outcome_reason": "saved", "save_outcome": "hold" if held else "parry",
                        "keeper_reach_m": round(reach, 6), "keeper_contact_distance_m": round(gap, 6)}
    return {"end": end, "outcome_reason": "goal" if goal else "off_target", "save_outcome": None}


def parry_target(start, contact, keeper_position, attacking_direction, speed_mps):
    # A centred contact sends the ball back into play; a stretching lateral
    # contact carries it beyond the keeper toward the near corner/touchline.
    lateral = contact["y_m"] - keeper_position["y_m"]
    if abs(lateral) > 1.0:
        return raw_point(contact["x_m"] + attacking_direction * 7,
                         contact["y_m"] + math.copysign(10, lateral))
    return raw_point(contact["x_m"] - attacking_direction * (5 + speed_mps * .16),
                     contact["y_m"] + (2 if lateral >= 0 else -2))
