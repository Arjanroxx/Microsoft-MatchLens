"""Small rating-driven substitution policy, not a tactical configuration system."""
import random


class SubstitutionManager:
    MAX_SUBSTITUTES = 5
    MAX_WINDOWS = 3

    def __init__(self, seed, duration_ms, roster):
        self.duration = duration_ms
        self.roster = roster
        self.plans, self.used, self.windows, self.used_players = {}, {}, {}, set()
        for team in ("home", "away"):
            rng = random.Random(f"{seed}-{team}-subs-v1")
            plans = []
            # Optional half-time change; most changes occur in the 60–70 minute band.
            if rng.random() < .2:
                plans.append({"at_ms": duration_ms, "count": 1, "halftime": True})
            plans.extend([
                {"at_ms": round(duration_ms * rng.uniform(60, 64) / 45), "count": 2, "halftime": False},
                {"at_ms": round(duration_ms * rng.uniform(66, 69) / 45), "count": 1, "halftime": False},
            ])
            self.plans[team], self.used[team], self.windows[team] = plans, 0, 0

    def due(self, period, t):
        now = (period - 1) * self.duration + t
        due = []
        for team, plans in self.plans.items():
            for plan in plans:
                # Added time in half one can exceed the nominal halftime
                # threshold. Keep this plan pending until the actual interval.
                if plan["halftime"] and not (period == 2 and t == 0):
                    continue
                if plan.get("done") or now < plan["at_ms"]:
                    continue
                plan["done"] = True
                if self.used[team] >= self.MAX_SUBSTITUTES or (not plan["halftime"] and self.windows[team] >= self.MAX_WINDOWS):
                    continue
                due.append((team, plan))
        return due

    def select(self, team, active, players, count):
        bench = [pid for pid, p in self.roster.items() if p["team_id"] == team and not p["is_starter"]
                 and pid not in self.used_players and pid not in active and p["role"] != "GK"]
        candidates = [pid for pid in active if self.roster[pid]["team_id"] == team
                      and self.roster[pid]["is_starter"] and self.roster[pid]["role"] != "GK"
                      and players[pid].get("current_role") != "GK"
                      and any(self.roster[b]["position_group"] == self.roster[pid]["position_group"] for b in bench)]
        # NR is unknown, not a poor score. Rated players are considered first.
        candidates.sort(key=lambda pid: (players[pid]["rating"]["value"] is None,
                                         players[pid]["rating"]["value"] if players[pid]["rating"]["value"] is not None else 6,
                                         pid))
        choices = []
        for off in candidates:
            compatible = [pid for pid in bench if self.roster[pid]["position_group"] == self.roster[off]["position_group"]]
            if not compatible or len(choices) >= min(count, self.MAX_SUBSTITUTES - self.used[team]):
                continue
            on = compatible[0]
            bench.remove(on)
            choices.append((off, on))
        return choices, [{"player_id": pid, "rating": players[pid]["rating"]["value"]} for pid in candidates]
