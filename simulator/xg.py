"""Explainable, uncalibrated pre-shot chance heuristic, never outcome-derived.

Selected coefficients are original assumptions, not a trained StatsBomb/Opta
model. Units use six decimals so Python and JavaScript sums agree exactly.
"""
import math

MODEL = {"version": "matchlens-preshot-xg-v1", "calibrated": False,
         "label": "Synthetic xG estimate (uncalibrated)", "penalty_prior": .76,
         "coefficients": {"intercept": -1.3, "distance_m": -.1,
                          "angle_radians": 1.8, "blockers": -.22,
                          "pressure": -.35, "uncovered_keeper": .7,
                          "keeper_off_line_m": -.03, "direct_free_kick": -.35},
         "limitations": ["Original selected coefficients; not fitted or calibrated to real matches",
                         "Ground/foot-shot assumption; no height/body-part/assist-technique tracking",
                         "Pre-shot geometry only; excludes aim, shot speed, effort, skill and outcome",
                         "Fixed selected penalty prior; no goalkeeper/finisher identity adjustment"]}


def shot_xg(event, roster, goalkeeper_id=None):
    """Return None for unsupported legacy evidence; never invent missing frames."""
    start, frame = event.get("start"), event.get("pitch_snapshot", {}).get("players")
    if event.get("type") != "shot" or not start or not frame:
        return None
    team, period = event.get("team_id"), event.get("period")
    if team not in ("home", "away") or period not in (1, 2):
        return None
    def side(pid):
        row = roster.get(pid)
        return row.get("team_id") if isinstance(row, dict) else row
    keeper = event.get("goalkeeper_id") or goalkeeper_id
    # A starting keeper can be recovered for legacy frames. Modern reducers
    # pass the actual active role assignment after a dismissal.
    if keeper is None:
        keeper = next((p for p,r in roster.items() if isinstance(r,dict) and
                       r.get("role") == "GK" and side(p) != team and p in frame), None)
    d = 1 if (team == "home") == (period == 1) else -1
    goal_x = 105 if d == 1 else 0
    dx, dy = d*(goal_x-start["x_m"]), start["y_m"]-34
    distance = math.hypot(dx,dy)
    angle = math.atan2(abs(7.32*dx), dx*dx+dy*dy-3.66**2) if dx >= 0 else 0
    opponents = {p:q for p,q in frame.items() if side(p) is not None and side(p) != team}
    outfield = {p:q for p,q in opponents.items() if p != keeper}
    nearest = min((math.hypot(q["x_m"]-start["x_m"],q["y_m"]-start["y_m"]) for q in outfield.values()),default=None)
    def in_cone(pos):
        if dx <= 0: return False
        u = d*(pos["x_m"]-start["x_m"])/dx
        low = start["y_m"]+(30.34-start["y_m"])*u
        high = start["y_m"]+(37.66-start["y_m"])*u
        return 0 < u <= 1 and low <= pos["y_m"] <= high
    blockers = sorted(p for p,q in outfield.items() if in_cone(q))
    keeper_pos = frame.get(keeper)
    covered = in_cone(keeper_pos) if keeper_pos else None
    off_line = abs(goal_x-keeper_pos["x_m"]) if keeper_pos else None
    situation = event.get("set_piece_type") or "open_play"
    pressure = max(0,3-nearest)/3 if nearest is not None else 0
    c = MODEL["coefficients"]
    contributions = {"intercept":c["intercept"], "distance":c["distance_m"]*distance,
        "angle":c["angle_radians"]*angle, "blockers":c["blockers"]*len(blockers),
        "pressure":c["pressure"]*pressure,
        "uncovered_keeper":c["uncovered_keeper"] if covered is False else 0,
        "keeper_off_line":c["keeper_off_line_m"]*min(off_line or 0,10) if covered else 0,
        "direct_free_kick":c["direct_free_kick"] if situation == "direct_free_kick" else 0}
    logit = sum(contributions.values())
    value = MODEL["penalty_prior"] if situation == "penalty" else max(.001,min(.95,1/(1+math.exp(-max(-60,min(60,logit))))))
    return {"value":round(value,6), "model":MODEL["version"], "calibrated":False,
            "counted":event.get("valid_for_statistics") is not False,
            "features":{"distance_m":round(distance,6), "angle_radians":round(angle,6),
                "blocker_ids":blockers, "nearest_defender_m":round(nearest,6) if nearest is not None else None,
                "goalkeeper_id":keeper, "keeper_in_cone":covered,
                "keeper_off_line_m":round(off_line,6) if off_line is not None else None,
                "situation":situation, "body_part_assumption":"foot"},
            "logit_contributions":{k:round(v,6) for k,v in contributions.items()},
            "method":"selected_penalty_prior" if situation == "penalty" else "geometry_logistic_heuristic"}


class XGAccumulator:
    def __init__(self):
        self.shots = self.known = self.units = self.np_units = self.np_shots = self.np_known = 0
        self.assisted_units = self.assisted_missing = 0

    def add(self, event, roster, keeper=None):
        estimate = shot_xg(event,roster,keeper)
        self.shots += 1
        penalty = event.get("set_piece_type") == "penalty"
        self.np_shots += not penalty
        if estimate is not None:
            units = round(estimate["value"]*1_000_000)
            self.known += 1
            self.units += units
            if not penalty:
                self.np_known += 1
                self.np_units += units
        return estimate

    def assist(self, estimate):
        if estimate is None:
            self.assisted_missing += 1
        else:
            self.assisted_units += round(estimate["value"]*1_000_000)

    def summary(self, goals, on_target):
        total = self.units/1_000_000 if self.known == self.shots else None
        return {"xg":total, "non_penalty_xg":self.np_units/1_000_000 if self.np_known == self.np_shots else None,
                "xg_per_shot":math.floor(self.units/self.shots+.5)/1_000_000 if total is not None and self.shots else None,
                "goals_minus_xg":round(goals-total,6) if total is not None else None,
                "xg_assisted":self.assisted_units/1_000_000 if not self.assisted_missing else None,
                "shot_conversion_percentage":math.floor(goals*10_000/self.shots+.5)/100 if self.shots else None,
                "shot_accuracy_percentage":math.floor(on_target*10_000/self.shots+.5)/100 if self.shots else None,
                "xg_coverage":{"shots_with_xg":self.known,"shots_without_xg":self.shots-self.known,
                               "complete":self.known == self.shots},
                "xg_model":MODEL["version"]}
