import copy
import unittest
from pathlib import Path
import json

from simulator.clock import PeriodClock
from simulator.engine import generate
from simulator.generate import validate
from simulator.metrics import ball_speed
from simulator.restarts import award_restart, first_exit, parry_target, raw_point, resolve_shot
from simulator.statistics import calculate_statistics
from simulator.statistics import MatchStatistics
from simulator.pitch import resolve_pass


class BoundaryTests(unittest.TestCase):
    def test_whole_ball_not_centre_and_no_clamping(self):
        start = raw_point(50, 1)
        self.assertIsNone(first_exit(start, raw_point(50, -.05)))
        crossing = first_exit(start, raw_point(50, -5))
        self.assertEqual(crossing["boundary"], "touchline")
        self.assertEqual(crossing["location"], raw_point(50, -.11))
        self.assertLess(crossing["fraction"], 1)

    def test_first_boundary_wins_on_diagonal(self):
        near_corner = raw_point(104, 67)
        self.assertEqual(first_exit(near_corner, raw_point(110, 69))["boundary"], "goal_line")
        self.assertEqual(first_exit(near_corner, raw_point(106, 75))["boundary"], "touchline")
        self.assertIsNone(first_exit(raw_point(10, 10), raw_point(30, 30)))

    def test_a_defender_cannot_intercept_after_the_ball_has_left_the_pitch(self):
        start, aim, intended = raw_point(50, 1), raw_point(80, -8), raw_point(80, 1)
        result = resolve_pass(start, aim, intended, {"away-02": raw_point(75, 0)}, 10, stop_at_boundary=True)
        self.assertEqual(result["reason"], "out_of_play")
        self.assertEqual(result["end"], first_exit(start, aim)["location"])
        self.assertIsNone(result["interceptor_id"])

    def test_throw_in_award_opposite_last_touch_and_correct_side(self):
        for y in (-5, 74):
            crossing = first_exit(raw_point(44, 34), raw_point(56, y))
            award = award_restart(crossing, "home", "home-07", 1)
            self.assertEqual(award["type"], "throw_in")
            self.assertEqual(award["team_id"], "away")
            self.assertEqual(award["location"]["y_m"], 0 if y < 0 else 68)
            self.assertEqual(award["last_touch_player_id"], "home-07")

    def test_goal_line_awards_both_halves_both_ends(self):
        for period in (1, 2):
            for x in (-5, 110):
                crossing = first_exit(raw_point(52, 20), raw_point(x, 20))
                defending = "home" if (x < 0) == (period == 1) else "away"
                attacking = "away" if defending == "home" else "home"
                corner = award_restart(crossing, defending, f"{defending}-04", period)
                goal_kick = award_restart(crossing, attacking, f"{attacking}-09", period)
                self.assertEqual((corner["type"], corner["team_id"]), ("corner_kick", attacking))
                self.assertEqual((goal_kick["type"], goal_kick["team_id"]), ("goal_kick", defending))
                self.assertEqual(corner["location"], raw_point(0 if x < 0 else 105, 0))
                self.assertEqual(goal_kick["location"]["x_m"], 5.5 if x < 0 else 99.5)

    def test_hold_parry_and_goal_come_from_contact_geometry(self):
        start, aim, keeper = raw_point(80, 34), raw_point(108, 34), raw_point(103, 34)
        held = resolve_shot(start, aim, keeper, 25)
        parried = resolve_shot(start, aim, keeper, 33)
        beaten = resolve_shot(start, aim, raw_point(103, 42), 33)
        missed = resolve_shot(start, raw_point(108, 45), keeper, 25)
        self.assertEqual((held["outcome_reason"], held["save_outcome"]), ("saved", "hold"))
        self.assertEqual(parried["save_outcome"], "parry")
        self.assertEqual(beaten["outcome_reason"], "goal")
        self.assertEqual(missed["outcome_reason"], "off_target")
        self.assertLess(held["end"]["x_m"], beaten["end"]["x_m"])

    def test_parry_continues_from_contact_instead_of_off_target_recovery(self):
        contact, keeper = raw_point(103, 34), raw_point(103, 34)
        rebound = parry_target(raw_point(80, 34), contact, keeper, 1, 33)
        self.assertLess(rebound["x_m"], contact["x_m"])
        self.assertIsNone(first_exit(contact, rebound))
        wide_contact = raw_point(103, 36)
        parry_out = parry_target(raw_point(80, 34), wide_contact, keeper, 1, 33)
        crossing = first_exit(wide_contact, parry_out)
        self.assertEqual(crossing["boundary"], "goal_line")
        self.assertEqual(award_restart(crossing, "away", "away-01", 1)["type"], "corner_kick")


class AddedTimeTests(unittest.TestCase):
    def test_minimum_rounding_and_further_loss_extends_half(self):
        clock = PeriodClock(2_700_000)
        clock.lost(1000, 31_000, "substitutions", "event-1")
        clock.lost(40_000, 81_000, "goal_celebration", "event-2")
        self.assertEqual(clock.announce(), 120_000)
        self.assertEqual(clock.end, 2_820_000)
        clock.lost(2_730_000, 2_750_000, "substitutions", "event-3")
        self.assertEqual(clock.end, 2_840_000)
        self.assertEqual(clock.announced, 120_000)  # minimum never reduced

    def test_no_loss_no_added_time_and_short_match_quantum(self):
        clock = PeriodClock(60_000)
        self.assertEqual(clock.announce(), 0)
        self.assertEqual(clock.end, 60_000)
        self.assertGreaterEqual(clock.quantum, 1000)


class ConnectedRestartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = Path(__file__).resolve().parents[1]/"data"/"examples"/"restarts-match"
        cls.metadata = json.loads((base/"metadata.json").read_text())
        cls.events = [json.loads(line) for line in (base/"events.jsonl").read_text().splitlines()]
        cls.result = calculate_statistics(cls.metadata, cls.events)

    def test_showcase_exercises_every_priority_one_outcome(self):
        validate(self.metadata, self.events)
        reasons = {e.get("reason") for e in self.events if e["type"] == "restart"}
        self.assertTrue(reasons >= {"kickoff", "throw_in", "goal_kick", "corner_kick"})
        self.assertEqual({e["outcome"] for e in self.events if e["type"] == "save"}, {"hold", "parry"})
        self.assertTrue(any(e.get("is_rebound") for e in self.events))
        self.assertTrue(any(e["type"] == "clearance" for e in self.events))
        self.assertTrue(any(e["type"] == "goal" for e in self.events))

    def test_natural_substitutions_preserve_live_selection_and_opportunity(self):
        by_id = {e["event_id"]: e for e in self.events}
        subs = [e for e in self.events if e["type"] == "substitution"]
        self.assertTrue(subs)
        for sub in subs:
            stop = by_id[sub["stoppage_event_id"]]
            self.assertIn(stop["reason"], ("ball_out", "goal_celebration", "period_interval"))
            self.assertNotEqual(stop["reason"], "substitution_break")
            before = calculate_statistics(self.metadata, self.events[:sub["sequence"]-1])
            self.assertEqual(sub["selection"]["player_off_rating"], before["players"][sub["player_off_id"]]["rating"]["value"])

    def test_no_possession_accrues_until_restart_is_live(self):
        for stop in (e for e in self.events if e["type"] == "stoppage"):
            release = next((e for e in self.events[stop["sequence"]:] if
                            e["type"] == "resume" or (e["type"] == "restart" and e.get("ball_in_play"))), None)
            if not release or release["period"] != stop["period"]:
                continue
            before = calculate_statistics(self.metadata, self.events[:stop["sequence"]])
            after = calculate_statistics(self.metadata, self.events[:release["sequence"]])
            self.assertEqual(before["possession"]["controlled_time_ms"], after["possession"]["controlled_time_ms"])

    def test_restarts_obey_setup_distances_and_penalty_area(self):
        roster = {p["player_id"]: p for p in self.metadata["players"]}
        for event in (e for e in self.events if e["type"] == "restart"):
            for pid, pos in event["positions_after"].items():
                if roster[pid]["team_id"] == event["team_id"]:
                    continue
                if event["reason"] in ("throw_in", "corner_kick", "kickoff"):
                    from simulator.pitch import distance
                    self.assertGreaterEqual(distance(pos, event["start"]), 2 if event["reason"] == "throw_in" else 9.15)
                if event["reason"] == "goal_kick":
                    own_left = (event["team_id"] == "home") == (event["period"] == 1)
                    in_x = pos["x_m"] < 16.5 if own_left else pos["x_m"] > 88.5
                    self.assertFalse(in_x and 13.84 < pos["y_m"] < 54.16)

    def test_clocks_minutes_and_counts_reconcile_with_added_time(self):
        self.assertGreater(self.metadata["match_duration_ms"], 600_000)
        end1 = next(e for e in self.events if e["type"] == "period_end" and e["period"] == 1)
        start2 = next(e for e in self.events if e["type"] == "period_start" and e["period"] == 2)
        self.assertEqual(end1["match_time_ms"], start2["match_time_ms"])
        self.assertEqual(self.result["possession"]["elapsed_time_ms"], self.metadata["match_duration_ms"])
        for team in ("home", "away"):
            players = [p for p in self.result["players"].values() if p["team_id"] == team]
            self.assertEqual(sum(p["minutes_played_ms"] for p in players), 11*self.metadata["match_duration_ms"])
            for key in ("throw_ins", "goal_kicks", "corners", "clearances", "saves", "saves_held", "saves_parried", "rebound_shots"):
                self.assertEqual(sum(p[key] for p in players), self.result["teams"][team][key])
        second_half_regulation = calculate_statistics(self.metadata, self.events, as_of=(2, 300_000))
        self.assertTrue(any(p["rating"]["provisional"] for p in second_half_regulation["players"].values() if p["squad_status"] == "on_pitch"))

    def test_saved_shot_is_not_counted_again_by_follow_up_save_event(self):
        saved = sum(e["type"] == "shot" and e["outcome_reason"] == "saved" for e in self.events)
        self.assertEqual(sum(t["saves"] for t in self.result["teams"].values()), saved)
        self.assertEqual(sum(t["saves_held"]+t["saves_parried"] for t in self.result["teams"].values()), saved)
        for rebound in (e for e in self.events if e.get("is_rebound")):
            prior = next(e for e in self.events if e["event_id"] == rebound["rebound_of_shot_event_id"])
            self.assertEqual(prior["save_outcome"], "parry")
            self.assertLess(prior["sequence"], rebound["sequence"])

    def test_corrupted_last_touch_clock_restart_parry_and_speed_are_rejected(self):
        for corruption in ("last_touch", "award", "clock", "parry", "speed", "delivery"):
            changed = copy.deepcopy(self.events)
            if corruption in ("last_touch", "award"):
                out = next(e for e in changed if e["type"] == "ball_out")
                if corruption == "last_touch":
                    out["last_touch_player_id"] = "home-01"
                else:
                    out["restart"]["team_id"] = "home" if out["restart"]["team_id"] == "away" else "away"
            if corruption == "clock":
                changed[-1]["match_time_ms"] -= 1
            if corruption == "parry":
                next(e for e in changed if e["type"] == "parry")["shot_event_id"] = "missing"
            if corruption == "speed":
                next(e for e in changed if e["type"] == "clearance")["ball_speed"]["average_kmh"] += 5
            if corruption == "delivery":
                next(e for e in changed if e["type"] == "restart_delivery")["recipient_id"] = "missing"
            with self.subTest(corruption=corruption), self.assertRaises(ValueError):
                validate(self.metadata, changed)

    def test_legacy_versions_still_validate(self):
        root = Path(__file__).resolve().parents[1]/"data"/"examples"
        for name in ("short-match", "substitutions-match"):
            metadata = json.loads((root/name/"metadata.json").read_text())
            events = [json.loads(line) for line in (root/name/"events.jsonl").read_text().splitlines()]
            validate(metadata, events)

    def test_true_streaming_reducer_does_not_need_final_durations(self):
        metadata = copy.deepcopy(self.metadata)
        for key in ("final_score", "match_duration_ms", "period_offsets_ms", "period_actual_durations_ms"):
            metadata.pop(key, None)
        reducer = MatchStatistics(metadata)
        for event in self.events:
            reducer.update(event)
            live = reducer.snapshot((event["period"], event["period_time_ms"]))
            expected = calculate_statistics(self.metadata, self.events[:event["sequence"]])
            self.assertEqual(live["possession"], expected["possession"])
            self.assertEqual(live["teams"], expected["teams"])
        self.assertEqual(reducer.snapshot()["players"], self.result["players"])


if __name__ == "__main__":
    unittest.main()
