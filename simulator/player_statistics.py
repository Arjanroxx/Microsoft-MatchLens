"""Per-player event aggregation with strictly linked key passes and assists."""
import copy

from simulator.aggregates import METRICS, distribution, record_action_metrics
from simulator.ratings import RATING_MODEL, player_rating


class PlayerStatistics:
    def __init__(self, metadata):
        self.duration = metadata["period_duration_ms"]
        self.roster = {p["player_id"]: p for p in metadata["players"]}
        self.players = {pid: {
            "player_id": pid, "team_id": p["team_id"], "name": p.get("name", pid),
            "shirt_number": p.get("shirt_number"), "role": p.get("role", "unknown"),
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
        if pid not in self.players:
            return
        self.players[pid][field] += 1
        self.evidence[pid].add(event["event_id"])

    def _keeper(self, team):
        candidates = [pid for pid, p in self.roster.items() if p["team_id"] == team and p.get("role") == "GK"]
        return candidates[0] if len(candidates) == 1 else None

    def update(self, event):
        if event["event_id"] in self.seen:
            return
        self.seen.add(event["event_id"])
        kind, actor, team = event["type"], event.get("player_id"), event.get("team_id")
        if kind in ("period_start", "period_end"):
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
            # Current simulator has 22 starters, no substitutions or dismissals.
            stats["minutes_played"] = round(elapsed_ms / 60_000, 2)
            stats["minutes_basis"] = "all_roster_players_are_starters_no_substitutions"
            stats["rating"] = player_rating(stats, self.evidence[pid], elapsed_ms < 2 * self.duration)
        return players
