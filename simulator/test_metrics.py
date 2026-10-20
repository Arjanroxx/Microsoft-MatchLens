import copy
import unittest

from simulator.generate import generate, validate
from simulator.metrics import ball_speed, make_trajectory, pass_difficulty


class MetricTests(unittest.TestCase):
    def setUp(self):
        self.start = {"x_m": 20, "y_m": 30}
        self.end = {"x_m": 50, "y_m": 30}

    def test_known_distance_time_and_unit_conversion(self):
        samples = make_trajectory(self.start, self.end, 1000, 10)
        speed = ball_speed(samples)
        self.assertEqual(speed["duration_ms"], 3000)
        self.assertEqual(speed["distance_m"], 30)
        self.assertEqual(speed["average_mps"], 10)
        self.assertEqual(speed["average_kmh"], 36)
        self.assertEqual(samples[-1]["period_time_ms"], 4000)

    def test_shot_uses_initial_window_not_flight_average(self):
        speed = ball_speed(make_trajectory(self.start, self.end, 0, 30, decelerate=True))
        self.assertEqual(speed["average_mps"], 30)
        self.assertGreater(speed["initial_segment_mps"], speed["average_mps"])
        self.assertEqual(speed["initial_segment_duration_ms"], 50)

    def test_zero_distance_and_short_duration(self):
        speed = ball_speed(make_trajectory(self.start, self.start, 0, 10))
        self.assertEqual(speed["average_mps"], 0)
        self.assertEqual(speed["duration_ms"], 1)
        samples = make_trajectory(self.start, {"x_m": 20.1, "y_m": 30}, 0, 30)
        self.assertEqual(len(samples), 2)
        self.assertLessEqual(ball_speed(samples)["average_mps"], 30)

    def test_invalid_timestamps_and_speed(self):
        samples = make_trajectory(self.start, self.end, 0, 10)
        samples[1]["period_time_ms"] = samples[0]["period_time_ms"]
        with self.assertRaises(ValueError):
            ball_speed(samples)
        for invalid in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                make_trajectory(self.start, self.end, 0, invalid)

    def test_difficulty_factors_and_direction_normalisation(self):
        def score(end=self.end, nearest=8, lane=0):
            return pass_difficulty(self.start, end, 1, nearest, lane)["score"]
        self.assertGreater(score(nearest=1), score())
        self.assertGreater(score(lane=3), score())
        self.assertGreater(score(end={"x_m": 80, "y_m": 30}), score())
        forward = pass_difficulty(self.start, self.end, 1, 1, 2)
        backward = pass_difficulty(self.start, self.end, -1, 1, 2)
        mirrored = pass_difficulty({"x_m": 85, "y_m": 30}, {"x_m": 55, "y_m": 30}, -1, 1, 2)
        self.assertGreater(forward["score"], backward["score"])
        self.assertEqual(forward, mirrored)
        self.assertFalse(forward["is_probability"])
        self.assertEqual(pass_difficulty({"x_m": 0, "y_m": 0}, {"x_m": 105, "y_m": 0}, 1, 0, 3)["score"], 100)

    def test_generated_metrics_and_rejection_of_tampering(self):
        metadata, events, _ = generate(42, "high-press", 45)
        validate(metadata, events)
        self.assertTrue(any(e["type"] == "shot" for e in events))
        for kind, field, key in (("pass", "pass_difficulty", "score"),
                                 ("pass", "ball_speed", "average_mps"),
                                 ("shot", "shot_speed", "kmh")):
            corrupted = copy.deepcopy(events)
            event = next(e for e in corrupted if e["type"] == kind)
            event[field][key] += 1
            with self.assertRaises(ValueError):
                validate(metadata, corrupted)


if __name__ == "__main__":
    unittest.main()
