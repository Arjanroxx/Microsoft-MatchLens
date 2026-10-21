"""Per-player event aggregation with strictly linked key passes and assists."""
import copy

from simulator.aggregates import METRICS, distribution, record_action_metrics
from simulator.ratings import RATING_MODEL, player_rating


class PlayerStatistics:
    def __init__(self, metadata):
        self.duration = metadata["period_duration_ms"]
        self.roster = {p["player_id"]: p for p in metadata["players"]}
        self.stints = {pid: {"entered_at_ms": 0 if p.get("is_starter", True) else None,
                             "left_at_ms": None} for pid, p in self.roster.items()}
        self.active = {pid for pid, stint in self.stints.items() if stint["entered_at_ms"] is not None}
        self.substitutions = []
        self.players = {pid: {
            "player_id": pid, "team_id": p["team_id"], "name": p.get("name", pid),
            "shirt_number": p.get("shirt_number"), "role": p.get("role", "unknown"),
            "position_group": p.get("position_group", p.get("role", "unknown")),
            "is_starter": p.get("is_starter", True),
            "goals": 0, "assists": 0, "key_passes": 0, "passes_received": 0,
            "passes": {"attempted": 0, "completed": 0, "incomplete": 0, "hard_completed": 0},
            "shots": {"total": 0, "on_target": 0, "off_target": 0},
            "saves": 0, "goals_conceded": 0, "interceptions": 0, "recoveries": 0,
            "turnovers": 0, "pressure_events": 0, "event_counts": {},
        } for pid, p in self.roster.items()}
        self.values = {pid: {key: [] for key in METRICS} for pid in self.roster}
        self.evidence = {pid: set() for pid in self.roster}
        self.seen, self.last_pass, self.shot_creators = set(), {}, {}

    def _credit(self, pid, field, event):
        if pid not in self.active:
            return
        self.players[pid][field] += 1
        self.evidence[pid].add(event["event_id"])

    def _keeper(self, team):
        candidates = [pid for pid, p in self.roster.items() if pid in self.active and p["team_id"] == team and p.get("role") == "GK"]
        return candidates[0] if len(candidates) == 1 else None

    def update(self, event):
        if event["event_id"] in self.seen:
            return
        self.seen.add(event["event_id"])
        kind, actor, team = event["type"], event.get("player_id"), event.get("team_id")
        if kind == "substitution":
            off, on = event["player_off_id"], event["player_on_id"]
            if (off not in self.active or on not in self.roster or on in self.active
                    or self.stints[on]["entered_at_ms"] is not None
                    or self.roster[off]["team_id"] != team or self.roster[on]["team_id"] != team):
                raise ValueError("Invalid player participation transition")
            now = (event["period"] - 1) * self.duration + event["period_time_ms"]
            self.stints[off]["left_at_ms"] = now
            self.stints[on]["entered_at_ms"] = now
            self.active.remove(off)
            self.active.add(on)
            self.last_pass.clear()
            self.substitutions.append({k: event[k] for k in ("event_id", "team_id", "period", "period_time_ms", "player_off_id", "player_on_id", "window_id")}
                                      | {"halftime": event.get("halftime", False),
                                         "formation_slot": event.get("formation_slot"),
                                         "position_group": event.get("position_group"),
                                         "rating_at_exit": event.get("selection", {}).get("player_off_rating")})
            return
        if actor in self.roster and actor not in self.active:
            raise ValueError("An inactive player cannot perform an action")
        if kind == "resume":
            return
        if kind in ("period_start", "period_end", "stoppage"):
            self.last_pass.clear()
        if actor in self.players:
            self.evidence[actor].add(event["event_id"])
            counts = self.players[actor]["event_counts"]
            counts[kind] = counts.get(kind, 0) + 1
            for event_type, field in (("goal", "goals"), ("recovery", "recoveries"),
                                      ("turnover", "turnovers"), ("pressure", "pressure_events")):
                if kind == event_type:
                    self.players[actor][field] += 1
            if kind in ("pass", "shot"):
                record_action_metrics(self.values[actor], event)
        if kind == "pass":
            if actor in self.players:
                passes = self.players[actor]["passes"]
                passes["attempted"] += 1
                complete = event["outcome"] == "complete"
                passes["completed" if complete else "incomplete"] += 1
                if complete and event.get("pass_difficulty", {}).get("score", 0) >= 65:
                    passes["hard_completed"] += 1
            if event["outcome"] == "complete":
                self._credit(event.get("recipient_id"), "passes_received", event)
                self.last_pass[event.get("possession_id")] = event
            else:
                self.last_pass.pop(event.get("possession_id"), None)
                self._credit(event.get("interceptor_id"), "interceptions", event)
        elif kind == "shot":
            if actor in self.players:
                shots = self.players[actor]["shots"]
                shots["total"] += 1
                if event["outcome"] == "goal" or event.get("outcome_reason") == "saved":
                    shots["on_target"] += 1
                if event.get("outcome_reason") == "off_target":
                    shots["off_target"] += 1
            if event.get("outcome_reason") == "saved" and team in ("home", "away"):
                self._credit(self._keeper("away" if team == "home" else "home"), "saves", event)
            prior = self.last_pass.pop(event.get("possession_id"), None)
            kick_ms = event["ball_trajectory"][0]["period_time_ms"]
            if (prior and prior["team_id"] == team and prior["period"] == event["period"]
                    and prior.get("recipient_id") == actor and prior.get("player_id") != actor
                    and 0 <= kick_ms - prior["period_time_ms"] <= RATING_MODEL["assist_window_ms"]):
                creator = prior.get("player_id")
                self._credit(creator, "key_passes", event)
                if creator in self.players:
                    self.evidence[creator].add(prior["event_id"])
                    self.shot_creators[event["event_id"]] = creator
        elif kind == "goal":
            creator = self.shot_creators.pop(event.get("shot_event_id"), None)
            self._credit(creator, "assists", event)
            if team in ("home", "away"):
                self._credit(self._keeper("away" if team == "home" else "home"), "goals_conceded", event)
        elif kind in ("turnover", "recovery", "restart"):
            self.last_pass.pop(event.get("possession_id"), None)

    def snapshot(self, elapsed_ms):
        players = copy.deepcopy(self.players)
        for pid, stats in players.items():
            attempts = stats["passes"]["attempted"]
            stats["passes"]["accuracy_percentage"] = round(100 * stats["passes"]["completed"] / attempts, 2) if attempts else None
            stats["metrics"] = {key: distribution(values) for key, values in self.values[pid].items()}
            stats["involvement_events"] = len(self.evidence[pid])
            stint = self.stints[pid]
            entered, left = stint["entered_at_ms"], stint["left_at_ms"]
            end = min(elapsed_ms, left if left is not None else elapsed_ms)
            stats["minutes_played"] = round(max(0, end - entered) / 60_000, 2) if entered is not None else 0
            stats["minutes_played_ms"] = max(0, end - entered) if entered is not None else 0
            stats["entered_at_ms"], stats["left_at_ms"] = entered, left
            stats["minutes_basis"] = "starting_lineup_and_substitution_events" if any("is_starter" in p for p in self.roster.values()) else "legacy_all_roster_players_start"
            stats["squad_status"] = ("substituted_off" if left is not None else
                                      "on_bench" if entered is None and elapsed_ms < 2 * self.duration else
                                      "unused_substitute" if entered is None else
                                      "full_time" if elapsed_ms >= 2 * self.duration else "on_pitch")
            stats["rating"] = player_rating(stats, self.evidence[pid], left is None and elapsed_ms < 2 * self.duration)
            stats["rating"]["finalised_at_ms"] = left if left is not None else 2 * self.duration if elapsed_ms >= 2 * self.duration else None
        return players
