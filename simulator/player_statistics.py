"""Per-player event aggregation with strictly linked key passes and assists."""
import copy

from simulator.aggregates import METRICS, distribution, record_action_metrics
from simulator.ratings import RATING_MODEL, RATING_MODEL_V2, player_rating
from simulator.clock import event_time, total_duration
from simulator.xg import XGAccumulator


class PlayerStatistics:
    def __init__(self, metadata):
        self.metadata = metadata
        self.finished_at = None
        self.abandoned = False
        self.rating_model = RATING_MODEL_V2 if metadata.get("rating_model_version") == RATING_MODEL_V2["version"] or metadata.get("schema_version") in ("1.6", "1.7", "1.8", "1.9") else RATING_MODEL
        self.duration = metadata["period_duration_ms"]
        self.roster = {p["player_id"]: p for p in metadata["players"]}
        self.stints = {pid: {"entered_at_ms": 0 if p.get("is_starter", True) else None,
                             "left_at_ms": None} for pid, p in self.roster.items()}
        self.active = {pid for pid, stint in self.stints.items() if stint["entered_at_ms"] is not None}
        self.substitutions = []
        self.dismissed = set()
        self.goalkeepers = {p["team_id"]: pid for pid, p in self.roster.items() if pid in self.active and p.get("role") == "GK"}
        self.players = {pid: {
            "player_id": pid, "team_id": p["team_id"], "name": p.get("name", pid),
            "shirt_number": p.get("shirt_number"), "role": p.get("role", "unknown"),
            "position_group": p.get("position_group", p.get("role", "unknown")),
            "is_starter": p.get("is_starter", True),
            "goals": 0, "assists": 0, "key_passes": 0, "passes_received": 0,
            "passes": {"attempted": 0, "completed": 0, "incomplete": 0, "hard_completed": 0},
            "shots": {"total": 0, "on_target": 0, "off_target": 0},
            "saves": 0, "goals_conceded": 0, "interceptions": 0, "recoveries": 0,
            "turnovers": 0, "pressure_events": 0, "clearances": 0,
            "saves_held": 0, "saves_parried": 0, "rebound_shots": 0,
            "throw_ins": 0, "goal_kicks": 0, "corners": 0, "event_counts": {},
            "current_role": p.get("role", "unknown"), "has_kept_goal": p.get("role") == "GK",
            "fouls_committed": 0, "fouls_won": 0, "yellow_cards": 0, "red_cards": 0,
            "second_yellow_dismissals": 0, "tackles": {"attempted": 0, "won": 0, "foul": 0, "missed": 0},
            "free_kicks": 0, "direct_free_kicks": 0, "indirect_free_kicks": 0,
            "penalties_won": 0, "penalties_conceded": 0, "penalties_taken": 0,
            "penalties_scored": 0, "penalties_missed": 0, "offsides": 0,
        } for pid, p in self.roster.items()}
        self.xg = {pid:XGAccumulator() for pid in self.roster}
        self.values = {pid: {key: [] for key in METRICS} for pid in self.roster}
        self.evidence = {pid: set() for pid in self.roster}
        self.seen, self.last_pass, self.shot_creators = set(), {}, {}

    def _credit(self, pid, field, event):
        if pid not in self.active:
            return
        self.players[pid][field] += 1
        self.evidence[pid].add(event["event_id"])

    def _keeper(self, team):
        if self.goalkeepers.get(team) in self.active:
            return self.goalkeepers[team]
        candidates = [pid for pid, p in self.roster.items() if pid in self.active and p["team_id"] == team and p.get("role") == "GK"]
        return candidates[0] if len(candidates) == 1 else None

    def update(self, event):
        if event["event_id"] in self.seen:
            return
        self.seen.add(event["event_id"])
        kind, actor, team = event["type"], event.get("player_id"), event.get("team_id")
        if event.get("valid_for_statistics") is False:
            self.last_pass.clear()
            return
        if kind == "movement":
            return
        if kind == "dismissal":
            if actor not in self.active:
                raise ValueError("Dismissal of inactive player")
            self._credit(actor, "red_cards", event)
            if event["reason"] == "second_yellow":
                self._credit(actor, "second_yellow_dismissals", event)
            self.stints[actor]["left_at_ms"] = event_time(self.metadata, event)
            self.active.remove(actor)
            self.dismissed.add(actor)
            self.last_pass.clear()
            return
        if kind == "goalkeeper_change":
            if actor not in self.active or self.roster[actor]["team_id"] != team:
                raise ValueError("Inactive goalkeeper assignment")
            self.goalkeepers[team] = actor
            self.players[actor]["current_role"] = "GK"
            self.players[actor]["has_kept_goal"] = True
            return
        if kind == "match_abandoned":
            self.finished_at = event_time(self.metadata, event)
            self.abandoned = True
            self.last_pass.clear()
            return
        if kind == "substitution":
            off, on = event["player_off_id"], event["player_on_id"]
            if (off not in self.active or on not in self.roster or on in self.active
                    or self.stints[on]["entered_at_ms"] is not None
                    or self.roster[off]["team_id"] != team or self.roster[on]["team_id"] != team):
                raise ValueError("Invalid player participation transition")
            now = event_time(self.metadata, event)
            self.stints[off]["left_at_ms"] = now
            self.stints[on]["entered_at_ms"] = now
            self.active.remove(off)
            self.active.add(on)
            self.last_pass.clear()
            self.substitutions.append({k: event[k] for k in ("event_id", "team_id", "period", "period_time_ms", "player_off_id", "player_on_id", "window_id")}
                                      | {"halftime": event.get("halftime", False),
                                         "match_time_ms": event_time(self.metadata, event),
                                         "formation_slot": event.get("formation_slot"),
                                         "position_group": event.get("position_group"),
                                         "rating_at_exit": event.get("selection", {}).get("player_off_rating")})
            return
        if actor in self.roster and actor not in self.active:
            raise ValueError("An inactive player cannot perform an action")
        if kind in ("resume", "ball_release"):
            return
        if kind == "period_end" and event["period"] == 2:
            self.finished_at = event_time(self.metadata, event)
        if kind in ("period_start", "period_end", "stoppage", "ball_out", "loose_ball", "save", "offside", "opponent_touch"):
            self.last_pass.clear()
        if actor in self.players:
            self.evidence[actor].add(event["event_id"])
            counts = self.players[actor]["event_counts"]
            counts[kind] = counts.get(kind, 0) + 1
            for event_type, field in (("goal", "goals"), ("recovery", "recoveries"),
                                      ("turnover", "turnovers"), ("pressure", "pressure_events"), ("offside", "offsides"), ("clearance", "clearances")):
                if kind == event_type:
                    self.players[actor][field] += 1
            if kind in ("pass", "shot"):
                record_action_metrics(self.values[actor], event)
            if kind == "restart":
                field = {"throw_in": "throw_ins", "goal_kick": "goal_kicks", "corner_kick": "corners",
                         "direct_free_kick": "direct_free_kicks", "indirect_free_kick": "indirect_free_kicks"}.get(event.get("reason"))
                if field:
                    self.players[actor][field] += 1
                    if field.endswith("free_kicks"):
                        self.players[actor]["free_kicks"] += 1
            if kind == "tackle":
                self.players[actor]["tackles"]["attempted"] += 1
                self.players[actor]["tackles"][event["outcome"]] += 1
            if kind == "card" and event["card"] == "yellow":
                self.players[actor]["yellow_cards"] += 1
            if kind == "foul":
                self.players[actor]["fouls_committed"] += 1
                self._credit(event["victim_id"], "fouls_won", event)
                if event["restart"]["type"] == "penalty":
                    self.players[actor]["penalties_conceded"] += 1
                    self._credit(event["victim_id"], "penalties_won", event)
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
        elif kind == "restart_delivery":
            self._credit(event.get("interceptor_id"), "interceptions", event)
        elif kind == "shot":
            estimate = self.xg[actor].add(event,self.roster,self._keeper("away" if team == "home" else "home")) if actor in self.xg else None
            if event.get("set_piece_type") == "penalty":
                self._credit(actor, "penalties_taken", event)
                self._credit(actor, "penalties_scored" if event["outcome"] == "goal" else "penalties_missed", event)
            if event.get("is_rebound"):
                self._credit(actor, "rebound_shots", event)
            if actor in self.players:
                shots = self.players[actor]["shots"]
                shots["total"] += 1
                if event["outcome"] == "goal" or event.get("outcome_reason") == "saved":
                    shots["on_target"] += 1
                if event.get("outcome_reason") == "off_target":
                    shots["off_target"] += 1
            if event.get("outcome_reason") == "saved" and team in ("home", "away"):
                keeper = self._keeper("away" if team == "home" else "home")
                self._credit(keeper, "saves", event)
                if event.get("save_outcome") in ("hold", "parry"):
                    self._credit(keeper, "saves_held" if event["save_outcome"] == "hold" else "saves_parried", event)
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
                    self.xg[creator].assist(estimate)
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
            stats.update(self.xg[pid].summary(stats["goals"],stats["shots"]["on_target"]))
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
            finished = self.finished_at is not None or (self.metadata.get("schema_version") not in ("1.5", "1.6", "1.7", "1.8", "1.9") and elapsed_ms >= total_duration(self.metadata))
            stats["squad_status"] = ("sent_off" if pid in self.dismissed else "substituted_off" if left is not None else
                                      "on_bench" if entered is None and not finished else
                                      "unused_substitute" if entered is None else
                                      "match_ended" if finished and self.abandoned else "full_time" if finished else "on_pitch")
            stats["rating"] = player_rating(stats, self.evidence[pid], left is None and not finished, self.rating_model)
            stats["rating"]["finalised_at_ms"] = left if left is not None else (self.finished_at or total_duration(self.metadata)) if finished else None
        return players
