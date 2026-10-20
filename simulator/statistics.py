"""Event-derived, per-team statistics and explicitly defined possession time."""
import copy


METRICS = (
    "pass_distance_m", "intended_pass_distance_m", "pass_difficulty_score",
    "pass_average_ball_speed_kmh", "pass_peak_segment_ball_speed_kmh",
    "shot_average_ball_speed_kmh", "shot_initial_segment_speed_kmh",
    "shot_peak_segment_speed_kmh", "ball_average_speed_kmh",
)


def distribution(values):
    return {"count": len(values), "min": round(min(values), 4),
            "mean": round(sum(values) / len(values), 2), "max": round(max(values), 4)} if values else {
                "count": 0, "min": None, "mean": None, "max": None}


class MatchStatistics:
    """Consume an ordered stream; snapshots never read future events or final score."""

    def __init__(self, metadata):
        self.metadata = metadata
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
            "pressure_events": 0, "possessions": 0, "event_counts": {},
        } for team in ("home", "away")}
        self.values = {team: {metric: [] for metric in METRICS} for team in self.counts}

    def _time(self, period, period_time_ms):
        if period not in (1, 2) or not 0 <= period_time_ms <= self.duration:
            raise ValueError("Invalid statistics clock")
        return (period - 1) * self.duration + period_time_ms

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
        when = self._time(event["period"], event["period_time_ms"])
        kind, team = event["type"], event.get("team_id")
        # At shot completion, resolve the previously unknown release interval.
        if kind == "shot":
            samples = event.get("ball_trajectory", [])
            if not samples:
                raise ValueError("Shot observations are required for possession timing")
            kick = self._time(event["period"], samples[0]["period_time_ms"])
            self._advance(kick)
            self.owner = None
        self._advance(when)
        if kind in ("period_start", "period_end", "turnover", "goal"):
            self.owner = None
        if kind in ("restart", "recovery"):
            self.owner = team
            pid = event.get("possession_id")
            if pid and pid not in self.possessions:
                self.possessions.add(pid)
                self.counts[team]["possessions"] += 1
        if team not in self.counts:
            return
        stats, values = self.counts[team], self.values[team]
        stats["event_counts"][kind] = stats["event_counts"].get(kind, 0) + 1
        for event_type, counter in (("goal", "goals"), ("recovery", "recoveries"),
                                    ("turnover", "turnovers"), ("pressure", "pressure_events")):
            if kind == event_type:
                stats[counter] += 1
        if kind not in ("pass", "shot"):
            return
        speed = event.get("ball_speed", {})
        if "average_kmh" in speed:
            values["ball_average_speed_kmh"].append(speed["average_kmh"])
            values[f'{kind}_average_ball_speed_kmh'].append(speed["average_kmh"])
        if "peak_segment_mps" in speed:
            key = "pass_peak_segment_ball_speed_kmh" if kind == "pass" else "shot_peak_segment_speed_kmh"
            values[key].append(speed["peak_segment_mps"] * 3.6)
        if kind == "pass":
            stats["passes"]["attempted"] += 1
            stats["passes"]["completed" if event["outcome"] == "complete" else "incomplete"] += 1
            for field, metric in (("distance_m", "pass_distance_m"), ("intended_distance_m", "intended_pass_distance_m")):
                if field in event:
                    values[metric].append(event[field])
            if "pass_difficulty" in event:
                values["pass_difficulty_score"].append(event["pass_difficulty"]["score"])
            interceptor_team = self.roster.get(event.get("interceptor_id"))
            if interceptor_team:
                self.counts[interceptor_team]["interceptions"] += 1
        else:
            stats["shots"]["total"] += 1
            reason = event.get("outcome_reason")
            if event["outcome"] == "goal" or reason == "saved":
                stats["shots"]["on_target"] += 1
            if reason == "off_target":
                stats["shots"]["off_target"] += 1
            if reason == "saved":
                self.counts["away" if team == "home" else "home"]["saves"] += 1
            if "shot_speed" in event:
                values["shot_initial_segment_speed_kmh"].append(event["shot_speed"]["kmh"])

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
        return {"teams": teams, "possession": {
            "method": "team_phase_time_v1",
            "definition": "Restart/recovery to loss; pass flights belong to passing team; shot flights and loose-ball/restart gaps unassigned",
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

    parser = argparse.ArgumentParser(description="Recalculate team statistics for an existing match; events stay unchanged")
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
    print(json.dumps({"updated": str(path), "teams": summary["teams"], "possession": summary["possession"]}, indent=2))


if __name__ == "__main__":
    main()
