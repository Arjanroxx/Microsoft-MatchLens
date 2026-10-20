import unittest

from simulator.generate import generate, validate
from simulator.progression import MatchProgression


class ProgressionTests(unittest.TestCase):
    def test_regular_changes_are_reproducible_and_independent(self):
        first, second = MatchProgression(42, 2_700_000), MatchProgression(42, 2_700_000)
        self.assertEqual(first.schedules, second.schedules)
        self.assertNotEqual(first.schedules["home"], first.schedules["away"])
        for schedule in first.schedules.values():
            for (a, before), (b, after) in zip(schedule, schedule[1:]):
                self.assertTrue(300_000 <= b - a <= 480_000)
                self.assertNotEqual(before, after)

    def test_conceding_team_presses_and_response_expires(self):
        model = MatchProgression(42, 2_700_000)
        model.schedules = {"home": [(0, "patient")], "away": [(0, "balanced"), (120_000, "patient")]}
        self.assertEqual(model.goal("home", 1, 100_000, "goal-1"), {"home": "patient", "away": "higher-press"})
        self.assertEqual(model.states(1, 200_000)["away"], "higher-press")
        self.assertEqual(model.states(1, 280_000)["away"], "patient")
        self.assertTrue(any(entry["trigger_event_id"] == "goal-1" for entry in model.audit))

    def test_goal_response_can_cross_halftime(self):
        model = MatchProgression(1, 2_700_000)
        model.goal("away", 1, 2_650_000, "goal-2")
        self.assertEqual(model.states(2, 0)["home"], "higher-press")

    def test_default_match_has_changes_and_goal_reactions(self):
        metadata, events, audit = generate(42)
        validate(metadata, events)
        self.assertIn("progression", metadata["simulation_model"])
        for team in ("home", "away"):
            changes = [a for a in audit if a["team_id"] == team and a["reason"] == "interval_change"]
            self.assertGreater(len(changes), 3)
        goals = [e for e in events if e["type"] == "goal"]
        self.assertTrue(goals)
        for goal in goals:
            reactions = [a for a in audit if a["trigger_event_id"] == goal["event_id"]]
            self.assertEqual(len(reactions), 1)
            self.assertNotEqual(reactions[0]["team_id"], goal["team_id"])
            self.assertEqual(reactions[0]["behaviour"], "higher-press")
        self.assertFalse(any("behaviour" in e for e in events))


if __name__ == "__main__":
    unittest.main()
