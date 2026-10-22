import copy
import unittest

from simulator.engine import generate
from simulator.generate import validate
from simulator.offside import contact_frame, contact_for, interference, touch_control
from simulator.pitch import point, resolve_pass
from simulator.statistics import calculate_statistics
from simulator.test_discipline import scenario


def setup_attack():
    sim = scenario()
    for pid in sim.pitch.positions:
        sim.pitch.positions[pid] = point(60, 5) if pid.startswith("home") else point(90, 60)
    sim.team, sim.owner, sim.ball = "home", "home-07", point(80, 34)
    sim.pitch.positions[sim.owner] = sim.ball.copy()
    sim.pitch.positions["home-10"] = point(96, 36)
    sim.pitch.positions["away-01"] = point(100, 34)
    sim.pitch.positions["away-03"] = point(95, 60)
    return sim


class PositionTests(unittest.TestCase):
    def test_both_directions_both_teams_and_level_is_legal(self):
        for team in ("home", "away"):
            for period in (1, 2):
                sim = setup_attack()
                d = 1 if (team == "home") == (period == 1) else -1
                enemy = "away" if team == "home" else "home"
                players = {f"{team}-07": point(80 if d == 1 else 25, 34),
                           f"{team}-10": point(96 if d == 1 else 9, 36),
                           f"{enemy}-01": point(100 if d == 1 else 5, 34),
                           f"{enemy}-03": point(95 if d == 1 else 10, 60)}
                actor, target = f"{team}-07", f"{team}-10"
                frame = contact_frame(players, players[actor], team, actor, period, sim.roster)
                self.assertIn(target, frame["candidates"])
                self.assertEqual(frame["second_last_opponent_id"], f"{enemy}-03")
                players[target]["x_m"] = frame["line_x_m"]
                self.assertNotIn(target, contact_frame(players, players[actor], team, actor, period, sim.roster)["candidates"])

    def test_ball_midline_own_half_and_goalkeeper_are_not_shortcuts(self):
        sim = setup_attack()
        self.assertIn("home-10", sim.offside_frame()["candidates"])
        sim.ball = point(97, 34)  # behind ball even though beyond second-last
        self.assertNotIn("home-10", sim.offside_frame()["candidates"])
        sim.ball = point(30, 34)
        sim.pitch.positions["home-10"] = point(52.5, 36)
        for pid in sim.pitch.team_positions("away"):
            sim.pitch.positions[pid]["x_m"] = 40
        self.assertNotIn("home-10", sim.offside_frame()["candidates"])
        sim.pitch.positions["home-10"] = point(51, 36)
        self.assertNotIn("home-10", sim.offside_frame()["candidates"])

    def test_active_opponents_only_and_second_last_need_not_be_keeper(self):
        sim = setup_attack()
        sim.pitch.positions["away-01"] = point(80, 34)
        sim.pitch.positions["away-04"] = point(102, 55)
        self.assertEqual(sim.offside_frame()["second_last_opponent_id"], "away-03")
        sim.pitch.dismiss("away-04")
        self.assertNotEqual(sim.offside_frame()["second_last_opponent_id"], "away-04")

    def test_exceptions_apply_only_to_direct_restart_contact(self):
        sim = setup_attack()
        for kind in ("throw_in", "corner_kick", "goal_kick"):
            self.assertTrue(sim.offside_frame(kind)["direct_receipt_exempt"])
            self.assertFalse(sim.offside_frame(kind)["candidates"])
        for kind in (None, "kickoff", "direct_free_kick", "indirect_free_kick"):
            self.assertIn("home-10", sim.offside_frame(kind)["candidates"])

    def test_passive_position_is_not_interference(self):
        sim = setup_attack()
        frame = sim.offside_frame()
        self.assertIn("home-10", frame["candidates"])
        self.assertIsNone(interference(frame, sim.positions(), sim.ball, "away-01"))
        sim.pitch.positions["home-10"] = point(99, 34)
        self.assertEqual(interference(sim.offside_frame(), sim.positions(), sim.ball, "away-01"), "home-10")

    def test_deliberate_play_is_controllability_not_whether_a_pass_succeeds(self):
        deliberate = touch_control(point(50, 34), point(70, 34), point(70, 34), 15)
        self.assertEqual(deliberate["classification"], "deliberate_play")
        self.assertTrue(deliberate["resets_offside"])
        reflex = touch_control(point(68, 34), point(70, 34), point(70, 34), 24)
        self.assertEqual(reflex["classification"], "deflection")
        self.assertFalse(reflex["resets_offside"])


class ConnectedOffsideTests(unittest.TestCase):
    def test_receipt_has_no_completion_received_assist_or_goal_credit(self):
        sim = setup_attack()
        sim.rng.choices = lambda *a, **kw: [("home-10", sim.pitch.positions["home-10"])]
        sim.pass_ball()
        action = next(e for e in sim.events if e["type"] == "pass")
        offence = next(e for e in sim.events if e["type"] == "offside")
        self.assertEqual(action["outcome_reason"], "offside")
        self.assertIsNone(action["recipient_id"])
        self.assertEqual(offence["source_event_id"], action["event_id"])
        p = sim.players.players
        self.assertEqual(p["home-10"]["passes_received"], 0)
        self.assertEqual(p["home-10"]["offsides"], 1)
        self.assertEqual(p["home-07"]["passes"]["completed"], 0)
        self.assertEqual(p["home-07"]["assists"], 0)
        self.assertEqual(sim.score, {"home": 0, "away": 0})
        stop = next(e for e in sim.events if e["type"] == "stoppage")
        self.assertEqual(stop["reason"], "offside")
        self.assertEqual(stop["restart"]["team_id"], "away")

    def test_interfering_attack_is_invalid_before_any_stat_credit(self):
        sim = setup_attack()
        sim.pitch.positions["home-10"] = point(99, 34)
        sim.shoot()
        shot = next(e for e in sim.events if e["type"] == "shot")
        self.assertFalse(shot["valid_for_statistics"])
        self.assertEqual(shot["outcome_reason"], "offside")
        self.assertFalse(any(e["type"] in ("goal", "save") for e in sim.events))
        stats = calculate_statistics(sim.metadata, sim.events)
        self.assertEqual(stats["teams"]["home"]["shots"]["total"], 0)
        self.assertEqual(stats["teams"]["away"]["saves"], 0)
        self.assertEqual(stats["players"]["home-07"]["shots"]["total"], 0)
        self.assertEqual(stats["players"]["home-07"]["key_passes"], 0)

    def test_deliberate_save_preserves_source_and_prevents_offside_rebound(self):
        sim = setup_attack()
        sim.rng.uniform = lambda a, b: 1 if a == .2 else 0
        sim.shoot()
        shot = next(e for e in sim.events if e["type"] == "shot")
        self.assertEqual(shot["save_outcome"], "parry")
        offence = next(e for e in sim.events if e["type"] == "offside")
        self.assertEqual(offence["involvement"], "gain_advantage_save")
        self.assertEqual(offence["source_event_id"], shot["event_id"])
        self.assertEqual(offence["contact"], contact_for(shot, sim.roster))
        self.assertFalse(any(e["type"] == "recovery" and e["player_id"] == "home-10" for e in sim.events))
        self.assertEqual(sim.players.players["home-10"]["shots"]["total"], 0)

    def test_deflection_preserves_phase_but_controlled_opponent_play_resets(self):
        for speed in (15, 22):
            sim = setup_attack()
            sim.pitch.positions["away-02"] = point(90, 34)
            intended = sim.pitch.positions["home-10"].copy()
            result = resolve_pass(sim.ball, intended, intended, sim.pitch.team_positions("away"), speed)
            self.assertEqual(result["interceptor_id"], "away-02")
            action = sim.flight("restart_delivery", result["end"], speed,
                                restart_type="indirect_free_kick", intended_recipient_id="home-10",
                                intended_end=intended, outcome="incomplete", recipient_id=None,
                                commanded_mean_speed_mps=speed,
                                interceptor_id="away-02" if speed == 15 else None,
                                deflector_id="away-02" if speed == 22 else None)
            sim.opponent_contact(action, "away-02")
            if speed == 15:
                self.assertFalse(any(e["type"] in ("offside", "deflection") for e in sim.events))
                self.assertEqual(sim.owner, "away-02")
            else:
                offence = next(e for e in sim.events if e["type"] == "offside")
                self.assertEqual(offence["involvement"], "gain_advantage_deflection")
                self.assertEqual(offence["contact"], contact_for(action, sim.roster))

    def test_restart_is_at_involvement_even_in_offenders_own_half(self):
        sim = setup_attack()
        source = sim.flight("clearance", point(49, 36), 20, commanded_mean_speed_mps=20)
        source_frame = contact_for(source, sim.roster)
        sim.pitch.positions["away-03"] = point(104, 60)  # later positions cannot revise source
        sim.whistle_offside(source, "home-10", "touch", location=point(49, 36))
        offence = next(e for e in sim.events if e["type"] == "offside")
        self.assertEqual(offence["restart"]["location"], point(49, 36))
        self.assertEqual(offence["contact"], source_frame)

    def test_stream_rejects_changed_line_source_restart_and_missing_decision(self):
        metadata, events, _ = generate(42, minutes_per_half=5)
        validate(metadata, events)
        self.assertTrue(any(e["type"] == "offside" for e in events))
        for field in ("line", "source", "restart", "involvement"):
            changed = copy.deepcopy(events)
            e = next(e for e in changed if e["type"] == "offside")
            if field == "line": e["contact"]["line_x_m"] += 2
            elif field == "source": e["source_event_id"] = events[0]["event_id"]
            elif field == "restart": e["restart"]["team_id"] = e["team_id"]
            else: e["involvement"] = "position_only"
            with self.assertRaises(ValueError): validate(metadata, changed)
        changed = copy.deepcopy(events)
        decision = next(e for e in changed if e["type"] == "offside")
        # Preserve sequence/clock to isolate a deleted decision's consequence.
        decision["type"] = "loose_ball"
        with self.assertRaises(ValueError): validate(metadata, changed)
        stats = calculate_statistics(metadata, events)
        for team in ("home", "away"):
            self.assertEqual(stats["teams"][team]["offsides"],
                             sum(p["offsides"] for p in stats["players"].values() if p["team_id"] == team))


if __name__ == "__main__":
    unittest.main()
