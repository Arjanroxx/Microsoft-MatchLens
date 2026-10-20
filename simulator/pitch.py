"""Small persistent pitch state: bounded movement, intended passes, defenders."""
import math


def point(x, y):
    return {"x_m": round(max(0, min(105, x)), 4), "y_m": round(max(0, min(68, y)), 4)}


def distance(a, b):
    return math.hypot(a["x_m"] - b["x_m"], a["y_m"] - b["y_m"])


def pass_context(start, intended_end, defenders, corridor_m=2):
    """Measure context from defender coordinates, never sample context metrics."""
    length_sq = distance(start, intended_end) ** 2
    lane_ids = []
    for pid, pos in defenders.items():
        if not length_sq:
            continue
        u = ((pos["x_m"] - start["x_m"]) * (intended_end["x_m"] - start["x_m"])
             + (pos["y_m"] - start["y_m"]) * (intended_end["y_m"] - start["y_m"])) / length_sq
        projection = point(start["x_m"] + u * (intended_end["x_m"] - start["x_m"]),
                           start["y_m"] + u * (intended_end["y_m"] - start["y_m"]))
        if 0 < u < 1 and distance(pos, projection) <= corridor_m:
            lane_ids.append(pid)
    nearest_id = min(defenders, key=lambda pid: distance(start, defenders[pid]))
    nearest_m = round(distance(start, defenders[nearest_id]), 4)
    return {"source": "pitch_snapshot", "nearest_defender_id": nearest_id,
            "nearest_defender_m": nearest_m, "under_pressure": nearest_m <= 2.5,
            "defenders_in_lane": len(lane_ids), "lane_defender_ids": sorted(lane_ids),
            "corridor_half_width_m": corridor_m}


def resolve_pass(start, aimed_end, intended_end, defenders, speed_mps):
    """Intercept using kick-time geometry and bounded straight-line defender reach."""
    length = distance(start, aimed_end)
    candidates = []
    if length:
        for pid, pos in defenders.items():
            u = ((pos["x_m"] - start["x_m"]) * (aimed_end["x_m"] - start["x_m"])
                 + (pos["y_m"] - start["y_m"]) * (aimed_end["y_m"] - start["y_m"])) / length ** 2
            if not 0.1 <= u <= 0.9:
                continue
            crossing = point(start["x_m"] + u * (aimed_end["x_m"] - start["x_m"]),
                             start["y_m"] + u * (aimed_end["y_m"] - start["y_m"]))
            arrival_s = distance(start, crossing) / speed_mps
            if distance(pos, crossing) <= 4.5 * arrival_s:
                candidates.append((arrival_s, pid, crossing))
    if candidates:
        _, interceptor, end = min(candidates)
        return {"outcome": "incomplete", "reason": "intercepted", "end": end, "interceptor_id": interceptor}
    flight_s = length / speed_mps
    if distance(aimed_end, intended_end) <= min(2.5, 4.5 * flight_s):
        return {"outcome": "complete", "reason": "received", "end": aimed_end, "interceptor_id": None}
    return {"outcome": "incomplete", "reason": "missed_target", "end": aimed_end, "interceptor_id": None}


class PitchState:
    RUN_SPEED_MPS = 4.5
    FORMATION = [(5, 34), (25, 8), (25, 25), (25, 43), (25, 60),
                 (48, 15), (50, 34), (48, 53), (72, 14), (76, 34), (72, 54)]

    def __init__(self, period):
        self.period = period
        self.positions = {}
        for team in ("home", "away"):
            for i, (x, y) in enumerate(self.FORMATION, 1):
                self.positions[f"{team}-{i:02}"] = point(x if self.direction(team) == 1 else 105 - x, y)

    def direction(self, team):
        return 1 if (team == "home") == (self.period == 1) else -1

    def team_positions(self, team):
        return {pid: pos.copy() for pid, pos in self.positions.items() if pid.startswith(team + "-")}

    def nearest(self, team, ball):
        return min(self.team_positions(team), key=lambda pid: distance(self.positions[pid], ball))

    def move(self, pid, target, seconds):
        current = self.positions[pid]
        d = distance(current, target)
        fraction = min(1, self.RUN_SPEED_MPS * seconds / d) if d else 1
        self.positions[pid] = point(current["x_m"] + fraction * (target["x_m"] - current["x_m"]),
                                    current["y_m"] + fraction * (target["y_m"] - current["y_m"]))

    def advance(self, seconds, possessing_team, owner, ball, press=False, quiet=False):
        opponents = "away" if possessing_team == "home" else "home"
        chasing = sorted(self.team_positions(opponents), key=lambda pid: distance(self.positions[pid], ball))[:2]
        for pid in self.positions:
            if pid == owner:
                continue
            team, number = pid.split("-")
            if int(number) == 1:
                # Goalkeepers retain a goal-side position instead of shifting with outfield lines.
                target = point(2 if self.direction(team) == 1 else 103,
                               max(30, min(38, 34 + .2 * (ball["y_m"] - 34))))
                self.move(pid, target, seconds)
                continue
            anchor_x, anchor_y = self.FORMATION[int(number) - 1]
            direction = self.direction(team)
            own_ball_x = ball["x_m"] if direction == 1 else 105 - ball["x_m"]
            shift = (own_ball_x - 52.5) * 0.4 + (3 if quiet else 9) * (1 if team == possessing_team else -0.5)
            target = point(anchor_x + shift if direction == 1 else 105 - anchor_x - shift,
                           anchor_y + 0.15 * (ball["y_m"] - 34))
            if pid in chasing and int(number) != 1:
                if press:
                    # Scenario changes defensive behaviour, not the reported pressure metric.
                    offset = -1 if pid == chasing[0] else 1
                    target = point(ball["x_m"] + offset, ball["y_m"] + offset)
                elif distance(self.positions[pid], ball) < 15:
                    target = point(ball["x_m"] - 3 * direction, ball["y_m"] + 3)
            self.move(pid, target, seconds)
