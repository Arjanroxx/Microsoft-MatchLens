import copy
import unittest

from simulator.engine import generate
from simulator.generate import validate
from simulator.statistics import calculate_statistics
from simulator.substitutions import SubstitutionManager


class SubstitutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata, cls.events, _ = generate(42)
        cls.result = calculate_statistics(cls.metadata, cls.events)
        cls.subs = [e for e in cls.events if e["type"] == "substitution"]

    def test_position_limits_and_timing(self):
        validate(self.metadata, self.events)
        self.assertEqual(len(self.metadata["players"]), 40)
        roster = {p["player_id"]: p for p in self.metadata["players"]}
        self.assertTrue(self.subs)
        for team in ("home", "away"):
            subs = [e for e in self.subs if e["team_id"] == team]
            self.assertTrue(1 <= len(subs) <= 5)
            self.assertLessEqual(len({e["window_id"] for e in subs if not e["halftime"]}), 3)
            self.assertEqual(len(self.result["lineups"][team]["on_pitch"]), 11 - len(self.result["lineups"][team]["sent_off"]))
        for event in self.subs:
            self.assertNotEqual(roster[event["player_off_id"]]["role"], "GK")
            self.assertEqual(roster[event["player_off_id"]]["position_group"], roster[event["player_on_id"]]["position_group"])
            if not event["halftime"]:
                minute = ((event["period"] - 1) * self.metadata["period_duration_ms"] + event["period_time_ms"]) / 60_000
                self.assertTrue(60 <= minute <= 75)  # waits for the next natural stoppage
            self.assertEqual(len(event["positions_after"]), 22)

    def test_selection_uses_rating_at_decision_not_final_rating(self):
        # First member of each window is the lowest rated eligible player at that time.
        windows = set()
        for event in self.subs:
            before = calculate_statistics(self.metadata, self.events[:event["sequence"] - 1])
            off = event["player_off_id"]
            self.assertEqual(event["selection"]["player_off_rating"], before["players"][off]["rating"]["value"])
            if event["window_id"] not in windows:
                windows.add(event["window_id"])
                rated = [p["rating"] for p in event["selection"]["eligible_candidate_ratings"] if p["rating"] is not None]
                if rated:
                    self.assertEqual(event["selection"]["player_off_rating"], min(rated))

    def test_off_player_freezes_on_player_builds_own_minutes_and_rating(self):
        event = self.subs[0]
        now = event["match_time_ms"]
        at_sub = calculate_statistics(self.metadata, self.events, as_of=(event["period"], event["period_time_ms"]))
        off, on = event["player_off_id"], event["player_on_id"]
        self.assertEqual(at_sub["players"][off]["rating"], self.result["players"][off]["rating"])
        self.assertFalse(at_sub["players"][off]["rating"]["provisional"])
        self.assertEqual(self.result["players"][off]["minutes_played_ms"], now)
        self.assertEqual(at_sub["players"][on]["minutes_played_ms"], 0)
        self.assertIsNone(at_sub["players"][on]["rating"]["value"])
        self.assertGreater(self.result["players"][on]["involvement_events"], 0)
        self.assertEqual(self.result["players"][on]["minutes_played_ms"], self.metadata["match_duration_ms"] - now)
        before = calculate_statistics(self.metadata, self.events, as_of=(event["period"], event["period_time_ms"] - 1))
        self.assertEqual(before["players"][on]["squad_status"], "on_bench")
        self.assertEqual(before["players"][on]["minutes_played_ms"], 0)

    def test_evolving_ratings_and_team_minutes_reconcile(self):
        for team in ("home", "away"):
            players = [p for p in self.result["players"].values() if p["team_id"] == team]
            deficit = sum(self.metadata["match_duration_ms"] - e["match_time_ms"] for e in self.events if e["type"] == "dismissal" and e["team_id"] == team)
            self.assertEqual(sum(p["minutes_played_ms"] for p in players), 11 * self.metadata["match_duration_ms"] - deficit)
            for p in players:
                if p["squad_status"] == "unused_substitute":
                    self.assertEqual(p["minutes_played_ms"], 0)
                    self.assertIsNone(p["rating"]["value"])
        early = calculate_statistics(self.metadata, self.events, as_of=(1, 600_000))
        self.assertTrue(any(early["players"][pid]["rating"]["value"] != p["rating"]["value"]
                            for pid, p in self.result["players"].items() if p["is_starter"]))

    def test_halftime_and_scaled_short_match(self):
        match, stream, _ = generate(0, minutes_per_half=5)
        validate(match, stream)
        halftime = [e for e in stream if e["type"] == "substitution" and e["halftime"]]
        self.assertTrue(halftime)
        self.assertTrue(all(e["period"] == 2 and e["period_time_ms"] == 0 for e in halftime))
        for event in (e for e in stream if e["type"] == "substitution" and not e["halftime"]):
            scaled_minute = ((event["period"] - 1) * match["period_duration_ms"] + event["period_time_ms"]) / (match["period_duration_ms"] / 45)
            self.assertGreaterEqual(scaled_minute, 60)  # next natural opportunity can be delayed
            self.assertIn(event["stoppage_event_id"], {e["event_id"] for e in stream if e["type"] == "stoppage"})

    def test_invalid_lineup_and_off_player_action_are_rejected(self):
        changed = copy.deepcopy(self.events)
        sub = next(e for e in changed if e["type"] == "substitution")
        sub["player_on_id"] = "away-12" if sub["team_id"] == "home" else "home-12"
        with self.assertRaises(ValueError):
            validate(self.metadata, changed)
        changed = copy.deepcopy(self.events)
        original = self.subs[0]
        action = next(e for e in changed if e["sequence"] > original["sequence"] and e["type"] == "pass" and e["team_id"] == original["team_id"])
        action["player_id"] = original["player_off_id"]
        with self.assertRaises(ValueError):
            validate(self.metadata, changed)

    def test_no_keeper_no_reentry_and_unrated_is_not_treated_as_zero(self):
        roster = {
            "home-01": {"team_id": "home", "role": "GK", "position_group": "GK", "is_starter": True},
            "home-02": {"team_id": "home", "role": "DF", "position_group": "FB", "is_starter": True},
            "home-03": {"team_id": "home", "role": "DF", "position_group": "FB", "is_starter": True},
            "home-13": {"team_id": "home", "role": "DF", "position_group": "FB", "is_starter": False},
        }
        manager = SubstitutionManager(42, 2_700_000, roster)
        players = {pid: {"rating": {"value": value}} for pid, value in (("home-01", 1), ("home-02", 5), ("home-03", None))}
        choices, _ = manager.select("home", ["home-01", "home-02", "home-03"], players, 1)
        self.assertEqual(choices, [("home-02", "home-13")])
        manager.used_players.add("home-13")
        self.assertEqual(manager.select("home", ["home-01", "home-02", "home-03"], players, 1)[0], [])


if __name__ == "__main__":
    unittest.main()
