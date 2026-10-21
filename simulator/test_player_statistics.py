import copy
import unittest

from simulator.engine import generate
from simulator.ratings import player_rating
from simulator.statistics import METRICS, calculate_statistics


def metadata():
    players = [{"player_id": f"{team}-{number:02}", "team_id": team, "name": f"{team} {number}",
                "role": role, "shirt_number": number} for team in ("home", "away")
               for number, role in ((1, "GK"), (7, "MF"), (9, "FW"))]
    return {"match_id": "fixture", "period_duration_ms": 60_000,
            "teams": [{"team_id": "home", "name": "Home"}, {"team_id": "away", "name": "Away"}],
            "players": players, "final_score": {"home": 99, "away": 99}}


def fixture(outcome="goal", delay=1000):
    rows = [
        {"period_time_ms": 0, "type": "restart", "team_id": "home", "player_id": "home-07"},
        {"period_time_ms": 1000, "type": "pass", "team_id": "home", "player_id": "home-07",
         "recipient_id": "home-09", "outcome": "complete", "distance_m": 20,
         "intended_distance_m": 20, "pass_difficulty": {"score": 70}, "ball_speed": {"average_kmh": 60}},
        {"period_time_ms": 2000 + delay, "type": "shot", "team_id": "home", "player_id": "home-09",
         "outcome": "goal" if outcome == "goal" else "no_goal", "outcome_reason": outcome,
         "ball_trajectory": [{"period_time_ms": 1000 + delay}, {"period_time_ms": 2000 + delay}],
         "shot_speed": {"kmh": 120}, "ball_speed": {"average_kmh": 100}},
    ]
    if outcome == "goal":
        rows.append({"period_time_ms": 2000 + delay, "type": "goal", "team_id": "home",
                     "player_id": "home-09", "shot_event_id": "e-3"})
    for i, row in enumerate(rows, 1):
        row.update(match_id="fixture", event_id=f"e-{i}", sequence=i, period=1, possession_id="pos-1")
    return rows


class PlayerStatisticsTests(unittest.TestCase):
    def test_assist_and_key_pass_are_linked_to_shot_and_goal(self):
        result = calculate_statistics(metadata(), fixture())
        passer, shooter, keeper = (result["players"][pid] for pid in ("home-07", "home-09", "away-01"))
        self.assertEqual(passer["assists"], 1)
        self.assertEqual(passer["key_passes"], 1)
        self.assertEqual(passer["passes"]["hard_completed"], 1)
        self.assertEqual(shooter["goals"], 1)
        self.assertEqual(shooter["shots"]["total"], 1)
        self.assertEqual(shooter["passes_received"], 1)
        self.assertEqual(keeper["goals_conceded"], 1)
        self.assertEqual(shooter["metrics"]["shot_initial_segment_speed_kmh"]["mean"], 120)
        self.assertEqual(passer["metrics"]["pass_distance_m"]["mean"], 20)
        self.assertIn("e-2", passer["rating"]["evidence_event_ids"])
        self.assertIn("e-4", passer["rating"]["evidence_event_ids"])

    def test_no_assist_on_a_save_or_expired_or_different_possession_pass(self):
        saved = calculate_statistics(metadata(), fixture("saved"))["players"]
        self.assertEqual(saved["home-07"]["key_passes"], 1)
        self.assertEqual(saved["home-07"]["assists"], 0)
        self.assertEqual(saved["away-01"]["saves"], 1)
        self.assertIsNotNone(saved["away-01"]["rating"]["value"])
        self.assertEqual(calculate_statistics(metadata(), fixture(delay=10_001))["players"]["home-07"]["assists"], 0)
        stream = fixture()
        stream[2]["possession_id"] = "different-possession"
        self.assertEqual(calculate_statistics(metadata(), stream)["players"]["home-07"]["assists"], 0)

    def test_future_goals_and_ratings_do_not_leak_and_duplicates_are_ignored(self):
        stream = fixture()
        early = calculate_statistics(metadata(), stream, as_of=(1, 1500))["players"]
        self.assertEqual(early["home-07"]["assists"], 0)
        self.assertEqual(early["home-09"]["goals"], 0)
        self.assertIsNone(early["home-09"]["rating"]["value"])
        self.assertTrue(early["home-09"]["rating"]["provisional"])
        self.assertEqual(calculate_statistics(metadata(), stream + [stream[-1]])["players"],
                         calculate_statistics(metadata(), stream)["players"])

    def test_every_roster_player_including_inactive_has_a_record(self):
        result = calculate_statistics(metadata(), [])
        self.assertEqual(len(result["players"]), 6)
        for stats in result["players"].values():
            self.assertEqual(stats["minutes_played"], 0)
            self.assertIsNone(stats["passes"]["accuracy_percentage"])
            self.assertEqual(stats["rating"]["status"], "insufficient_evidence")
            self.assertIsNone(stats["rating"]["value"])

    def test_ratings_are_role_aware_bounded_and_reconstructible(self):
        player = calculate_statistics(metadata(), fixture())["players"]["home-09"]
        evidence = set(player["rating"]["evidence_event_ids"])
        initial = player_rating(player, evidence, False)
        self.assertEqual(initial["value"], round(max(1, min(10, 6 + sum(initial["components"].values()))), 1))
        defender = copy.deepcopy(player)
        defender["role"] = "DF"
        self.assertGreater(player_rating(defender, evidence, False)["components"]["scoring"], initial["components"]["scoring"])
        player["goals"] = player["assists"] = player["saves"] = 1000
        player["interceptions"] = player["recoveries"] = 1000
        self.assertEqual(player_rating(player, evidence, False)["value"], 10)
        for rating in (initial, player_rating(defender, evidence, False)):
            self.assertTrue(1 <= rating["value"] <= 10)

    def test_generated_players_reconcile_with_teams_without_using_skill_for_rating(self):
        match, stream, _ = generate(2, minutes_per_half=5)
        result = calculate_statistics(match, stream)
        self.assertEqual(len(result["players"]), 22)
        for team, aggregate in result["teams"].items():
            players = [p for p in result["players"].values() if p["team_id"] == team]
            for field in ("goals", "saves", "interceptions", "recoveries", "turnovers", "pressure_events"):
                self.assertEqual(sum(p[field] for p in players), aggregate[field])
            for field in ("attempted", "completed", "incomplete"):
                self.assertEqual(sum(p["passes"][field] for p in players), aggregate["passes"][field])
            self.assertEqual(sum(p["shots"]["total"] for p in players), aggregate["shots"]["total"])
            for metric in METRICS:
                self.assertEqual(sum(p["metrics"][metric]["count"] for p in players), aggregate["metrics"][metric]["count"])
            for p in players:
                self.assertEqual(p["minutes_played"], 10)
                self.assertFalse(p["rating"]["provisional"])
        modified = copy.deepcopy(match)
        for p in modified["players"]:
            p["passing_skill"] = p["shooting_skill"] = 0
        altered = calculate_statistics(modified, stream)
        self.assertEqual({pid: p["rating"] for pid, p in result["players"].items()},
                         {pid: p["rating"] for pid, p in altered["players"].items()})


if __name__ == "__main__":
    unittest.main()
