"""Small automatic behaviour changes; policy labels are evaluation-only."""
import random


BEHAVIOURS = ("balanced", "higher-press", "patient", "quick-play")


class MatchProgression:
    def __init__(self, seed, period_duration_ms):
        self.duration = period_duration_ms
        self.schedules, self.responses, self.previous, self.audit = {}, {}, {}, []
        # Normal matches change every 5–8 minutes. Short demos scale the interval.
        self.minimum_interval_ms = min(300_000, max(15_000, period_duration_ms // 5))
        self.maximum_interval_ms = min(480_000, max(30_000, period_duration_ms // 3))
        self.response_duration_ms = min(180_000, max(10_000, period_duration_ms // 4))
        for team in ("home", "away"):
            rng = random.Random(f"{seed}-{team}-progression-v1")
            schedule = [(0, "balanced")]
            time_ms, previous = 0, "balanced"
            while time_ms < 2 * period_duration_ms:
                time_ms += rng.randint(self.minimum_interval_ms, self.maximum_interval_ms)
                previous = rng.choice([mode for mode in BEHAVIOURS if mode != previous])
                schedule.append((time_ms, previous))
            self.schedules[team] = schedule

    def absolute_time(self, period, period_time_ms):
        return (period - 1) * self.duration + period_time_ms

    def states(self, period, period_time_ms):
        now = self.absolute_time(period, period_time_ms)
        states = {}
        for team in ("home", "away"):
            behaviour = "balanced"
            for start, candidate in self.schedules[team]:
                if start > now:
                    break
                behaviour = candidate
            reason, trigger = "interval_change", None
            response = self.responses.get(team)
            if response and now < response["until_ms"]:
                behaviour, reason, trigger = "higher-press", "after_conceding", response["goal_event_id"]
            states[team] = behaviour
            identity = (behaviour, reason, trigger)
            if self.previous.get(team) != identity:
                self.audit.append({"team_id": team, "period": period, "period_time_ms": period_time_ms,
                                   "behaviour": behaviour, "reason": reason, "trigger_event_id": trigger})
                self.previous[team] = identity
        return states

    def goal(self, scoring_team, period, period_time_ms, goal_event_id):
        conceding_team = "away" if scoring_team == "home" else "home"
        self.responses[conceding_team] = {
            "until_ms": self.absolute_time(period, period_time_ms) + self.response_duration_ms,
            "goal_event_id": goal_event_id,
        }
        return self.states(period, period_time_ms)
