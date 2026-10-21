import copy
import unittest

from simulator.generate import SCENARIOS, generate, validate
from simulator.replay import scheduled_time


class GeneratorTests(unittest.TestCase):
    def test_seed_reproducibility_and_variation(self):
        self.assertEqual(generate(42), generate(42))
        self.assertNotEqual(generate(42)[1], generate(43)[1])

    def test_all_profiles_many_seeds(self):
        for scenario in SCENARIOS:
            for seed in range(12):
                with self.subTest(scenario=scenario, seed=seed):
                    metadata, events, _ = generate(seed, scenario)
                    validate(metadata, events)
                    self.assertEqual(sum(e["type"] == "period_start" for e in events), 2)
                    self.assertEqual(sum(e["type"] == "period_end" for e in events), 2)
                    self.assertTrue(all(e["source"] == "synthetic" for e in events))
                    # Every live flight continues from the prior ball endpoint.
                    # Only explicit dead-ball placement and period resets relocate it.
                    ball = None
                    for e in events:
                        if e["type"] == "period_start":
                            ball = None
                        if e["type"] == "ball_placement":
                            if ball is not None:
                                self.assertEqual(e["start"], ball)
                            ball = e["end"]
                        elif e["type"] in ("restart", "recovery"):
                            if ball is not None:
                                self.assertEqual(e["start"], ball)
                            ball = e["start"]
                        elif e["type"] in ("pass", "shot", "restart_delivery", "clearance", "parry", "carry"):
                            self.assertEqual(e["start"], ball)
                            ball = e["end"]
                        if e["type"] == "pass":
                            self.assertNotEqual(e["player_id"], e["recipient_id"])
                            self.assertGreater(e["distance_m"], 0)

    def test_pressure_policy_produces_observed_pressure_not_guaranteed_stories(self):
        metadata, events, _ = generate(42, "high-press")
        validate(metadata, events)
        # Outcomes now emerge from geometry; no fixed count of successful attacks is forced.
        self.assertTrue(any(e["type"] == "pressure" and e["team_id"] == "home" for e in events))
        self.assertTrue(any(e["type"] == "shot" for e in events))
        self.assertFalse(any(e.get("reason") == "possession_cycle_end" for e in events))

    def test_validator_rejects_corruption(self):
        metadata, events, _ = generate()
        cases = []
        duplicate = copy.deepcopy(events)
        duplicate[1]["event_id"] = duplicate[0]["event_id"]
        cases.append(duplicate)
        bad_position = copy.deepcopy(events)
        next(e for e in bad_position if e["type"] == "pass")["end"]["x_m"] = 106
        cases.append(bad_position)
        bad_recipient = copy.deepcopy(events)
        next(e for e in bad_recipient if e["type"] == "pass" and e["outcome"] == "complete")["recipient_id"] = "missing"
        cases.append(bad_recipient)
        for corrupted in cases:
            with self.assertRaises(ValueError):
                validate(metadata, corrupted)

    def test_clock_and_short_matches(self):
        for minutes in (1, 5, 45):
            metadata, events, _ = generate(42, "high-press", minutes)
            validate(metadata, events)
            times = [scheduled_time(e, metadata["period_duration_ms"]) for e in events]
            self.assertEqual(times, sorted(times))
            self.assertEqual(times[-1], metadata["match_duration_ms"])
            self.assertGreaterEqual(times[-1], minutes * 120_000)
        for minutes in (0, 46):
            with self.assertRaises(ValueError):
                generate(minutes_per_half=minutes)


if __name__ == "__main__":
    unittest.main()
