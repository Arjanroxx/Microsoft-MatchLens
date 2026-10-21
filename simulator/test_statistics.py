import copy
import unittest

from simulator.engine import generate
from simulator.statistics import METRICS, MatchStatistics, calculate_statistics


def metadata(duration=20_000):
    return {"match_id": "fixture", "period_duration_ms": duration,
            "teams": [{"team_id": "home", "name": "Home"}, {"team_id": "away", "name": "Away"}],
            "players": [{"player_id": "away-02", "team_id": "away"}],
            "final_score": {"home": 999, "away": 999}}


def events(*rows):
    return [{"match_id": "fixture", "event_id": f"e-{i}", "sequence": i,
             "period": row[0], "period_time_ms": row[1], "type": row[2],
             "team_id": row[3], **(row[4] if len(row) > 4 else {})} for i, row in enumerate(rows, 1)]


class StatisticsTests(unittest.TestCase):
    def test_possession_is_time_based_and_excludes_loose_ball(self):
        stream = events((1, 0, "restart", "home"),
                        (1, 9000, "pass", "home", {"outcome": "complete"}),
                        (1, 10_000, "turnover", "home"),
                        (1, 12_000, "recovery", "away"),
                        (1, 20_000, "period_end", None))
        result = calculate_statistics(metadata(), stream)
        self.assertEqual(result["teams"]["home"]["possession"]["time_ms"], 10_000)
        self.assertEqual(result["teams"]["away"]["possession"]["time_ms"], 8000)
        self.assertEqual(result["possession"]["unassigned_time_ms"], 2000)
        self.assertEqual(result["teams"]["home"]["possession"]["percentage"], 55.56)
        self.assertEqual(result["teams"]["away"]["possession"]["percentage"], 44.44)

    def test_shot_flight_and_goal_restart_gap_not_given_to_either_team(self):
        stream = events((1, 0, "restart", "home"),
                        (1, 5000, "shot", "home", {"outcome": "goal", "ball_trajectory": [{"period_time_ms": 4000}, {"period_time_ms": 5000}]}),
                        (1, 5000, "goal", "home"), (1, 7000, "restart", "away"),
                        (1, 10_000, "period_end", None), (2, 0, "period_start", None),
                        (2, 0, "restart", "away"), (2, 10_000, "period_end", None))
        result = calculate_statistics(metadata(10_000), stream)
        self.assertEqual(result["teams"]["home"]["possession"]["time_ms"], 4000)
        self.assertEqual(result["teams"]["away"]["possession"]["time_ms"], 13_000)
        self.assertEqual(result["possession"]["unassigned_time_ms"], 3000)
        self.assertEqual(result["teams"]["home"]["goals"], 1)
        self.assertEqual(result["teams"]["home"]["shots"]["on_target"], 1)

    def test_team_metrics_and_defensive_credit_are_not_pooled(self):
        stream = events(
            (1, 0, "restart", "home"),
            (1, 1000, "pass", "home", {"outcome": "complete", "distance_m": 10,
                "pass_difficulty": {"score": 20}, "ball_speed": {"average_kmh": 36}}),
            (1, 2000, "pass", "home", {"outcome": "incomplete", "distance_m": 30,
                "pass_difficulty": {"score": 60}, "interceptor_id": "away-02"}),
            (1, 2000, "turnover", "home"), (1, 2000, "recovery", "away"),
            (1, 3000, "pass", "away", {"outcome": "complete", "distance_m": 50,
                "pass_difficulty": {"score": 80}, "ball_speed": {"average_kmh": 72}}),
            (1, 3500, "pressure", "home"),
            (1, 5000, "shot", "away", {"outcome": "no_goal", "outcome_reason": "saved",
                "ball_trajectory": [{"period_time_ms": 4000}, {"period_time_ms": 5000}],
                "shot_speed": {"kmh": 100}, "ball_speed": {"average_kmh": 80}}))
        result = calculate_statistics(metadata(), stream)["teams"]
        self.assertEqual(result["home"]["passes"]["accuracy_percentage"], 50)
        self.assertEqual(result["away"]["passes"]["accuracy_percentage"], 100)
        self.assertEqual(result["home"]["metrics"]["pass_distance_m"]["mean"], 20)
        self.assertEqual(result["away"]["metrics"]["pass_distance_m"]["mean"], 50)
        self.assertEqual(result["home"]["metrics"]["pass_difficulty_score"]["mean"], 40)
        self.assertEqual(result["away"]["metrics"]["pass_difficulty_score"]["mean"], 80)
        self.assertEqual(result["home"]["pressure_events"], 1)
        self.assertEqual(result["away"]["interceptions"], 1)
        self.assertEqual(result["home"]["saves"], 1)
        self.assertEqual(result["away"]["shots"]["on_target"], 1)

    def test_empty_values_are_unavailable_and_no_future_score_leaks(self):
        stream = events((1, 0, "restart", "home"), (1, 9000, "goal", "away"))
        result = calculate_statistics(metadata(), stream, as_of=(1, 3000))
        for team in result["teams"].values():
            self.assertEqual(team["goals"], 0)
            self.assertIsNone(team["passes"]["accuracy_percentage"])
            for metric in METRICS:
                self.assertEqual(team["metrics"][metric]["count"], 0)
                self.assertIsNone(team["metrics"][metric]["mean"])
        self.assertEqual(result["teams"]["home"]["possession"]["time_ms"], 3000)
        empty = calculate_statistics(metadata(), [])
        self.assertIsNone(empty["teams"]["home"]["possession"]["percentage"])

    def test_duplicate_events_and_repeat_snapshots_do_not_double_count(self):
        reducer = MatchStatistics(metadata())
        event = events((1, 0, "restart", "home"))[0]
        reducer.update(event)
        reducer.update(event)
        first = reducer.snapshot((1, 2000))
        self.assertEqual(reducer.snapshot((1, 2000)), first)
        self.assertEqual(reducer.cursor, 0)
        self.assertEqual(first["teams"]["home"]["event_counts"]["restart"], 1)

    def test_generated_totals_reconcile_and_shots_are_optional(self):
        match, stream, _ = generate(2, minutes_per_half=5)
        original = copy.deepcopy(stream)
        result = calculate_statistics(match, stream)
        self.assertEqual(stream, original)
        self.assertEqual(sum(t["goals"] for t in result["teams"].values()), sum(e["type"] == "goal" for e in stream))
        self.assertEqual(sum(t["passes"]["attempted"] for t in result["teams"].values()), sum(e["type"] == "pass" for e in stream))
        controlled = sum(t["possession"]["time_ms"] for t in result["teams"].values())
        self.assertEqual(controlled + result["possession"]["unassigned_time_ms"], match["match_duration_ms"])
        self.assertEqual(sum(t["possession"]["percentage"] for t in result["teams"].values()), 100)


if __name__ == "__main__":
    unittest.main()
