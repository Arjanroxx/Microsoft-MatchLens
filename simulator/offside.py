"""Law 11 decisions for a declared planar point-player model, not VAR.

Position is frozen at the teammate's first contact. Involvement is a separate
observation. Saves and uncontrolled deflections do not create a new phase.
"""
import copy
import math

EXEMPT_RESTARTS = {"throw_in", "goal_kick", "corner_kick"}
EPSILON_M = .001  # numerical tolerance, not a body-part or VAR allowance


def direction(team, period):
    return 1 if (team == "home") == (period == 1) else -1


def contact_frame(players, ball, team, actor, period, roster, restart_type=None):
    d = direction(team, period)
    opponents = sorted((p for p in players if roster[p]["team_id"] != team),
                       key=lambda p: (-d * players[p]["x_m"], p))
    if len(opponents) < 2:
        raise ValueError("Offside requires two active opponents")
    second = opponents[1]
    line = max(d * ball["x_m"], d * players[second]["x_m"])
    candidates = {}
    for pid, pos in players.items():
        if pid == actor or roster[pid]["team_id"] != team:
            continue
        ahead = d * pos["x_m"] - line
        opposing_half = d * (pos["x_m"] - 52.5) > EPSILON_M
        if opposing_half and ahead > EPSILON_M and restart_type not in EXEMPT_RESTARTS:
            candidates[pid] = {"x_m": pos["x_m"], "margin_m": round(ahead, 4)}
    return {"model": "law11-point-player-v1", "direction": d,
            "ball": copy.deepcopy(ball), "second_last_opponent_id": second,
            "second_last_opponent_x_m": players[second]["x_m"],
            "line_x_m": d * line, "candidates": candidates,
            "restart_type": restart_type, "direct_receipt_exempt": restart_type in EXEMPT_RESTARTS,
            "numerical_tolerance_m": EPSILON_M}


def contact_for(action, roster):
    return contact_frame(action["pitch_snapshot"]["players"], action["start"],
                         action["team_id"], action["player_id"], action["period"], roster,
                         action.get("restart_type"))


def interference(frame, players, ball, keeper):
    """Selected active interference: point-player obstructs keeper sight corridor.

    A candidate must be between ball and keeper, within 0.35m of that segment
    and within 3m of the keeper. No offence is inferred from position alone.
    This explicit 2D proxy cannot establish real human visual obstruction.
    """
    k = players[keeper]
    dx, dy = k["x_m"]-ball["x_m"], k["y_m"]-ball["y_m"]
    length2 = dx*dx+dy*dy
    for pid in sorted(frame["candidates"]):
        p = players[pid]
        u = ((p["x_m"]-ball["x_m"])*dx+(p["y_m"]-ball["y_m"])*dy)/length2 if length2 else -1
        separation = math.hypot(p["x_m"]-k["x_m"], p["y_m"]-k["y_m"])
        lateral = math.hypot(p["x_m"]-ball["x_m"]-u*dx, p["y_m"]-ball["y_m"]-u*dy)
        if 0 < u < 1 and separation <= 3 and lateral <= .35:
            return pid
    return None


def touch_control(start, contact, defender, speed):
    """Transparent selected controllability proxy, not a random outcome label.

    A ball arriving after >=0.5s at <=18m/s with >=0.2s spare running
    reach is a deliberate controlled play; a reaching interception otherwise
    represents a reflex deflection. A deliberate save is classified separately.
    """
    travel = math.hypot(contact["x_m"]-start["x_m"], contact["y_m"]-start["y_m"])/speed
    reach = math.hypot(contact["x_m"]-defender["x_m"], contact["y_m"]-defender["y_m"])/4.5
    controlled = travel >= .5 and speed <= 18 and travel-reach >= .2
    return {"model": "planar-controllability-v1", "arrival_ms": round(travel*1000),
            "reach_ms": round(reach*1000), "speed_mps": speed,
            "classification": "deliberate_play" if controlled else "deflection",
            "resets_offside": controlled}


def deflection_target(start, contact, defender):
    """A short rebound away from contact, continuing ball physics, not control."""
    dx, dy = contact["x_m"]-start["x_m"], contact["y_m"]-start["y_m"]
    norm = math.hypot(dx, dy) or 1
    side = 1 if defender["y_m"] <= contact["y_m"] else -1
    return {"x_m": round(contact["x_m"]+dx/norm*3, 6),
            "y_m": round(contact["y_m"]+dy/norm*3+side*2, 6)}
