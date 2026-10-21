"""Event-derived, per-team statistics and explicitly defined possession time."""
import copy

from simulator.aggregates import METRICS, distribution, record_action_metrics
from simulator.player_statistics import PlayerStatistics
from simulator.ratings import RATING_MODEL
from simulator.clock import elapsed, event_time


class MatchStatistics:
    """Consume an ordered stream; snapshots never read future events or final score."""

    def __init__(self, metadata):
        self.metadata = copy.deepcopy(metadata)
        self.duration = metadata["period_duration_ms"]
        self.team_names = {t["team_id"]: t["name"] for t in metadata["teams"]}
        self.roster = {p["player_id"]: p["team_id"] for p in metadata["players"]}
        self.seen, self.possessions = set(), set()
        self.cursor, self.owner = 0, None
        self.times = {"home": 0, "away": 0, "unassigned": 0}
        self.counts = {team: {
            "team_id": team, "name": self.team_names[team], "goals": 0,
            "passes": {"attempted": 0, "completed": 0, "incomplete": 0},
            "shots": {"total": 0, "on_target": 0, "off_target": 0},
            "saves": 0, "interceptions": 0, "recoveries": 0, "turnovers": 0,
            "pressure_events": 0, "possessions": 0, "substitutions": 0, "event_counts": {},
            "throw_ins": 0, "goal_kicks": 0, "corners": 0, "clearances": 0,
            "saves_held": 0, "saves_parried": 0, "rebound_shots": 0,
        } for team in ("home", "away")}
        self.values = {team: {metric: [] for metric in METRICS} for team in self.counts}
        self.player_statistics = PlayerStatistics(self.metadata)

    def _time(self, period, period_time_ms):
        limit = self.metadata.get("period_actual_durations_ms", {}).get(str(period),
                    float("inf") if self.metadata.get("schema_version") == "1.5" else self.duration)
        if period not in (1, 2) or not 0 <= period_time_ms <= limit:
            raise ValueError("Invalid statistics clock")
        return elapsed(self.metadata, period, period_time_ms)

    def _advance(self, target):
        if target < self.cursor:
            raise ValueError("Statistics require events in time order")
        self.times[self.owner or "unassigned"] += target - self.cursor
        self.cursor = target

    def update(self, event):
        if event["match_id"] != self.metadata["match_id"]:
            raise ValueError("Statistics event belongs to a different match")
        identity = event["event_id"]
        if identity in self.seen:
            return
        self.seen.add(identity)
        if event["type"] == "period_start" and "match_time_ms" in event:
            self.metadata.setdefault("period_offsets_ms", {})[str(event["period"])] = event["match_time_ms"]
        when = event_time(self.metadata, event)
        kind, team = event["type"], event.get("team_id")
        # At shot completion, resolve the previously unknown release interval.
        if kind in ("shot", "parry", "clearance"):
            samples = event.get("ball_trajectory", [])
            if not samples:
                raise ValueError("Shot observations are required for possession timing")
            kick = elapsed(self.metadata, event["period"], samples[0]["period_time_ms"])
            self._advance(max(self.cursor, kick))
            self.owner = None
        self._advance(when)
        if kind in ("period_start", "period_end", "turnover", "goal", "stoppage", "ball_out", "loose_ball", "save", "ball_release"):
            self.owner = None
        if kind == "resume":
            self.owner = team if event.get("player_id") else None
        if kind in ("restart", "recovery"):
            self.owner = team if event.get("ball_in_play", True) else None
            pid = event.get("possession_id")
            if pid and pid not in self.possessions:
                self.possessions.add(pid)
                self.counts[team]["possessions"] += 1
        self.player_statistics.update(event)
        if team not in self.counts:
            return
        stats, values = self.counts[team], self.values[team]
        stats["event_counts"][kind] = stats["event_counts"].get(kind, 0) + 1
        for event_type, counter in (("goal", "goals"), ("recovery", "recoveries"),
                                    ("turnover", "turnovers"), ("pressure", "pressure_events"),
                                    ("substitution", "substitutions"), ("clearance", "clearances")):
            if kind == event_type:
                stats[counter] += 1
        if kind == "restart":
            field = {"throw_in": "throw_ins", "goal_kick": "goal_kicks", "corner_kick": "corners"}.get(event.get("reason"))
            if field:
                stats[field] += 1
        if kind == "restart_delivery":
            defender_team = self.roster.get(event.get("interceptor_id"))
            if defender_team:
                self.counts[defender_team]["interceptions"] += 1
        if kind not in ("pass", "shot"):
            return
        record_action_metrics(values, event)
        if kind == "pass":
            stats["passes"]["attempted"] += 1
            stats["passes"]["completed" if event["outcome"] == "complete" else "incomplete"] += 1
            interceptor_team = self.roster.get(event.get("interceptor_id"))
            if interceptor_team:
                self.counts[interceptor_team]["interceptions"] += 1
        else:
            if event.get("is_rebound"):
                stats["rebound_shots"] += 1
            stats["shots"]["total"] += 1
            reason = event.get("outcome_reason")
            if event["outcome"] == "goal" or reason == "saved":
                stats["shots"]["on_target"] += 1
            if reason == "off_target":
                stats["shots"]["off_target"] += 1
            if reason == "saved":
                keeper_team = self.counts["away" if team == "home" else "home"]
                keeper_team["saves"] += 1
                if event.get("save_outcome") in ("hold", "parry"):
                    keeper_team["saves_held" if event["save_outcome"] == "hold" else "saves_parried"] += 1

    def snapshot(self, as_of=None):
        """Optionally extend the current state to a known playback time, without mutation."""
        target = self.cursor if as_of is None else self._time(*as_of)
        if target < self.cursor:
            raise ValueError("Rebuild from an event prefix to query an earlier time")
        times = self.times.copy()
        times[self.owner or "unassigned"] += target - self.cursor
        controlled = times["home"] + times["away"]
        home_share = round(100 * times["home"] / controlled, 2) if controlled else None
        shares = {"home": home_share, "away": round(100 - home_share, 2) if home_share is not None else None}
        teams = copy.deepcopy(self.counts)
        for team, stats in teams.items():
            passes = stats["passes"]
            passes["accuracy_percentage"] = round(100 * passes["completed"] / passes["attempted"], 2) if passes["attempted"] else None
            stats["metrics"] = {name: distribution(values) for name, values in self.values[team].items()}
            stats["possession"] = {"time_ms": times[team], "time_seconds": round(times[team] / 1000, 3),
                                   "percentage": shares[team],
                                   "elapsed_time_percentage": round(100 * times[team] / target, 2) if target else None}
        lineups = {team: {
            "on_pitch": sorted(pid for pid in self.player_statistics.active if self.roster[pid] == team),
            "bench": sorted(pid for pid, s in self.player_statistics.stints.items() if self.roster[pid] == team and s["entered_at_ms"] is None),
            "substituted_off": sorted(pid for pid, s in self.player_statistics.stints.items() if self.roster[pid] == team and s["left_at_ms"] is not None),
        } for team in self.counts}
        return {"teams": teams, "players": self.player_statistics.snapshot(target), "lineups": lineups,
                "substitutions": copy.deepcopy(self.player_statistics.substitutions),
                "player_rating_model": copy.deepcopy(RATING_MODEL), "possession": {
            "method": "team_phase_time_v1",
            "definition": "Live restart/recovery to loss; pass/restart-delivery flights belong to initiating team; shot/clearance/parry flights and loose/dead-ball gaps unassigned",
            "percentage_denominator": "home_time_ms + away_time_ms (excludes unassigned time)",
            "elapsed_time_ms": target, "controlled_time_ms": controlled,
            "unassigned_time_ms": times["unassigned"],
            "unassigned_time_percentage": round(100 * times["unassigned"] / target, 2) if target else None,
        }}


def calculate_statistics(metadata, events, as_of=None):
    """Calculate final statistics or a live event-prefix snapshot at (period, time_ms)."""
    reducer = MatchStatistics(metadata)
    for event in events:
        if as_of is not None and (event["period"], event["period_time_ms"]) > as_of:
            break
        reducer.update(event)
    return reducer.snapshot(as_of)


def main():
    import argparse
    import json
    from pathlib import Path
    from simulator.generate import validate

    parser = argparse.ArgumentParser(description="Recalculate team/player statistics and ratings; events stay unchanged")
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    for name in ("metadata.json", "events.jsonl"):
        if not (args.input / name).is_file():
            parser.error(f"Missing match file: {args.input / name}")
    metadata = json.loads((args.input / "metadata.json").read_text(encoding="utf-8"))
    events = [json.loads(line) for line in (args.input / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]
    validate(metadata, events)
    path = args.input / "summary.json"
    summary = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"match_id": metadata["match_id"]}
    summary.update(calculate_statistics(metadata, events))
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"updated": str(path), "teams": summary["teams"], "possession": summary["possession"],
                      "player_count": len(summary["players"]), "rating_model": RATING_MODEL["version"]}, indent=2))


if __name__ == "__main__":
    main()
