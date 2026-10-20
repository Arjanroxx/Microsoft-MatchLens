import copy
import unittest

from simulator.engine import generate
from simulator.generate import validate
from simulator.metrics import ball_speed, pass_difficulty
from simulator.pitch import PitchState, distance, pass_context, resolve_pass


class PitchTests(unittest.TestCase):
    def test_pressure_and_lane_come_from_geometry(self):
        start, end = {"x_m": 20, "y_m": 30}, {"x_m": 50, "y_m": 30}
        close = {"away-02": {"x_m": 21, "y_m": 30}, "away-03": {"x_m": 35, "y_m": 31}}
        far = {"away-02": {"x_m": 21, "y_m": 40}, "away-03": {"x_m": 35, "y_m": 45}}
        context = pass_context(start, end, close)
        self.assertEqual(context["nearest_defender_m"], 1)
        self.assertEqual(context["defenders_in_lane"], 2)
        moved = pass_context(start, end, far)
        self.assertFalse(moved["under_pressure"])
        self.assertEqual(moved["defenders_in_lane"], 0)
        rating = lambda c: pass_difficulty(start, end, 1, c["nearest_defender_m"], c["defenders_in_lane"])["score"]
        self.assertGreater(rating(context), rating(moved))

    def test_same_attempt_changes_outcome_when_defender_moves(self):
        start, end = {"x_m": 20, "y_m": 30}, {"x_m": 50, "y_m": 30}
        blocked = resolve_pass(start, end, end, {"away-02": {"x_m": 35, "y_m": 30}}, 15)
        open_lane = resolve_pass(start, end, end, {"away-02": {"x_m": 35, "y_m": 55}}, 15)
        self.assertEqual(blocked["reason"], "intercepted")
        self.assertEqual(blocked["end"], {"x_m": 35, "y_m": 30})
        self.assertEqual(open_lane["outcome"], "complete")

    def test_persistent_movement_is_bounded(self):
        state = PitchState(1)
        before = copy.deepcopy(state.positions)
        state.advance(.1, "home", "home-07", state.positions["home-07"], press=True)
        for pid, position in state.positions.items():
            self.assertLessEqual(distance(before[pid], position), .4502)

    def test_same_path_faster_motion_has_higher_measured_speed(self):
        samples = [{"period_time_ms": 0, "x_m": 0, "y_m": 0},
                   {"period_time_ms": 2000, "x_m": 20, "y_m": 0}]
        original = ball_speed(samples)["average_mps"]
        samples[1]["period_time_ms"] = 1000
        self.assertEqual(ball_speed(samples)["average_mps"], 2 * original)

    def test_defender_context_and_outcome_tampering_rejected(self):
        metadata, events, _ = generate(42, "balanced", 5)
        validate(metadata, events)
        changed = copy.deepcopy(events)
        event = next(e for e in changed if e["type"] == "pass")
        pid = event["difficulty_context"]["nearest_defender_id"]
        event["pitch_snapshot"]["players"][pid] = event["start"].copy()
        with self.assertRaises(ValueError):
            validate(metadata, changed)
        changed = copy.deepcopy(events)
        event = next(e for e in changed if e["type"] == "pass")
        event["outcome_reason"] = "unrelated_random_outcome"
        with self.assertRaises(ValueError):
            validate(metadata, changed)


if __name__ == "__main__":
    unittest.main()
