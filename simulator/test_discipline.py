import copy
import json
import random
import unittest
from pathlib import Path

from simulator.clock import PeriodClock
from simulator.discipline import foul_restart, in_penalty_area, resolve_challenge
from simulator.engine import generate
from simulator.generate import validate
from simulator.pitch import PitchState, point, distance
from simulator.progression import MatchProgression
from simulator.simulation import Simulation
from simulator.statistics import calculate_statistics


def scenario():
    metadata, _, _ = generate(0, minutes_per_half=1)
    sim = Simulation(copy.deepcopy(metadata), random.Random(0), MatchProgression(0, 60_000), "balanced", 0, 60_000)
    sim.period, sim.t, sim.clock = 1, 1000, PeriodClock(60_000)
    sim.pitch = PitchState(1)
    sim.team, sim.owner, sim.ball = "home", "home-07", point(52.5, 34)
    sim.possession()
    sim.emit("period_start", at=0, positions_after=sim.positions())
    return sim


def incident(sim, actor="away-04", victim="home-07", location=None, effort=.85, timing=250, technique="standing_tackle", gap=.2):
    location = location or point(52.5, 34)
    sim.team, sim.owner, sim.ball = sim.roster[victim]["team_id"], victim, location.copy()
    sim.pitch.positions[victim] = location.copy()
    sim.pitch.positions[actor] = point(location["x_m"]+.1, location["y_m"]+gap)
    controls = {"effort": effort, "timing_error_ms": timing, "technique": technique}
    decision = resolve_challenge(sim.ball, sim.pitch.positions[actor], **controls)
    return sim.emit("tackle", sim.roster[actor]["team_id"], actor, victim_id=victim, location=location.copy(),
                    outcome=decision["outcome"], controls=controls, decision=decision,
                    challenge_snapshot={"period_time_ms": sim.t, "players": sim.positions()})


class FoulRuleTests(unittest.TestCase):
    def test_clean_miss_careless_reckless_and_excessive_follow_evidence(self):
        ball, near = point(30, 30), point(30.2, 30)
        self.assertEqual(resolve_challenge(ball, near, .6, 0, "standing_tackle")["outcome"], "won")
        self.assertEqual(resolve_challenge(ball, point(35, 30), 1, 350, "standing_tackle")["outcome"], "missed")
        self.assertIsNone(resolve_challenge(ball, near, .6, 180, "standing_tackle")["card"])
        self.assertEqual(resolve_challenge(ball, near, .85, 250, "standing_tackle")["card"], "yellow")
        self.assertEqual(resolve_challenge(ball, near, .99, 350, "standing_tackle")["card"], "red")

    def test_indirect_is_not_a_penalty_even_inside_the_area(self):
        for period, offender, x, defending in ((1, "home", 10, True), (1, "away", 94, True), (2, "home", 94, True), (2, "away", 10, True)):
            location = point(x, 34)
            self.assertTrue(in_penalty_area(location, offender, period))
            self.assertEqual(foul_restart(location, offender, period, "late_contact_challenge")["type"], "penalty")
            self.assertEqual(foul_restart(location, offender, period, "dangerous_play_without_contact")["type"], "indirect_free_kick")
        self.assertEqual(foul_restart(point(50, 34), "away", 1, "late_contact_challenge")["type"], "direct_free_kick")

    def test_penalty_area_lines_and_goal_area_indirect_placement(self):
        self.assertTrue(in_penalty_area(point(16.5, 13.84), "home", 1))
        self.assertFalse(in_penalty_area(point(16.6, 34), "home", 1))
        award = foul_restart(point(2, 34), "home", 1, "dangerous_play_without_contact")
        self.assertEqual(award["location"], point(5.5, 34))

    def test_dangerous_no_contact_can_be_cautioned_if_reckless(self):
        decision = resolve_challenge(point(20, 20), point(21.2, 20), .95, 0, "raised_boot")
        self.assertEqual(decision["offence"], "dangerous_play_without_contact")
        self.assertEqual(decision["card"], "yellow")


class DisciplineLifecycleTests(unittest.TestCase):
    def test_advantage_delays_reckless_booking_until_next_stoppage(self):
        sim = scenario()
        sim.contact_rng.random = lambda: 0
        sim.handle_foul(incident(sim, location=point(70, 34)))
        self.assertTrue(any(e["type"] == "advantage" and e["outcome"] == "played" for e in sim.events))
        self.assertFalse(any(e["type"] == "card" for e in sim.events))
        self.assertEqual(len(sim.pending_cards), 1)
        stop = sim.emit("stoppage", reason="referee_whistle", source_event_id=sim.pending_cards[0]["event_id"], restart=None)
        sim.flush_cards(stop["event_id"])
        self.assertEqual(sim.players.players["away-04"]["yellow_cards"], 1)
        card = next(e for e in sim.events if e["type"] == "card")
        self.assertEqual(card["stoppage_event_id"], stop["event_id"])
        self.assertTrue(any(e["type"] == "time_lost" and e["reason"] == "disciplinary_administration" for e in sim.events))

    def test_failed_advantage_recalls_original_location_without_committing_a_failed_attack(self):
        sim = scenario()
        sim.contact_rng.random = lambda: 0
        sim.pitch.positions["away-03"] = point(73, 34)
        sim.handle_foul(incident(sim, location=point(70, 34), effort=.6, timing=160))
        self.assertTrue(any(e["type"] == "advantage" and e["outcome"] == "recalled" for e in sim.events))
        self.assertFalse(any(e["type"] == "carry" for e in sim.events))
        restart = next(e for e in sim.events if e["type"] == "restart")
        self.assertEqual(restart["reason"], "direct_free_kick")
        self.assertEqual(restart["start"], point(70, 34))

    def test_yellow_keeps_eleven_and_second_yellow_removes_one(self):
        sim = scenario()
        sim.handle_foul(incident(sim))
        self.assertEqual(sim.players.players["away-04"]["yellow_cards"], 1)
        self.assertEqual(len(sim.pitch.team_positions("away")), 11)
        sim.handle_foul(incident(sim))
        self.assertNotIn("away-04", sim.pitch.positions)
        self.assertEqual(len(sim.pitch.team_positions("away")), 10)
        stats = sim.players.snapshot(sim.t)["away-04"]
        self.assertEqual((stats["yellow_cards"], stats["red_cards"], stats["second_yellow_dismissals"]), (2, 1, 1))
        self.assertEqual(stats["squad_status"], "sent_off")
        self.assertFalse(stats["rating"]["provisional"])
        later = sim.players.snapshot(sim.t+10000)["away-04"]
        self.assertEqual(later, stats)
        with self.assertRaises(ValueError):
            sim.emit("pressure", "away", "away-04")

    def test_direct_red_and_current_keeper_assignment_survive_restart(self):
        sim = scenario()
        sim.handle_foul(incident(sim, actor="away-01", location=point(100, 34), effort=.99, timing=350))
        new_keeper = sim.keeper("away")
        self.assertNotEqual(new_keeper, "away-01")
        self.assertEqual(len(sim.pitch.team_positions("away")), 10)
        self.assertEqual(sim.players.players[new_keeper]["current_role"], "GK")
        shot = next(e for e in sim.events if e["type"] == "shot")
        self.assertEqual(shot["goalkeeper_id"], new_keeper)
        self.assertEqual(shot["set_piece_type"], "penalty")
        self.assertNotIn("away-01", shot["pitch_snapshot"]["players"])
        # A future kickoff must not resurrect the sent-off keeper.
        sim.pitch = PitchState(2, sim.pitch.slots)
        self.assertEqual(sim.keeper("away"), new_keeper)
        self.assertNotIn("away-01", sim.pitch.positions)
        choices, _ = sim.manager.select("away", sim.pitch.positions, sim.players.snapshot(sim.t), 5)
        self.assertNotIn(new_keeper, [off for off, _ in choices])

    def test_careless_foul_has_no_card_and_indirect_requires_another_player(self):
        sim = scenario()
        sim.handle_foul(incident(sim, effort=.6, timing=160))
        self.assertFalse(any(e["type"] == "card" for e in sim.events))
        sim.handle_foul(incident(sim, effort=.75, timing=0, technique="raised_boot", gap=1.2))
        restart = next(e for e in reversed(sim.events) if e["type"] == "restart")
        self.assertEqual(restart["reason"], "indirect_free_kick")
        delivery = next(e for e in sim.events if e["type"] == "restart_delivery" and e["restart_event_id"] == restart["event_id"])
        self.assertNotEqual(delivery["player_id"], delivery["intended_recipient_id"])
        self.assertFalse(any(e["type"] == "shot" and e.get("restart_event_id") == restart["event_id"] for e in sim.events))

    def test_penalty_setup_distances_and_keeper_goal_line(self):
        sim = scenario()
        sim.handle_foul(incident(sim, location=point(94, 34), effort=.6, timing=160))
        restart = next(e for e in sim.events if e["type"] == "restart" and e["reason"] == "penalty")
        self.assertEqual(restart["start"], point(94, 34))
        keeper = sim.keeper("away")
        positions = restart["positions_after"]
        self.assertEqual(positions[keeper]["x_m"], 105)
        for pid, pos in positions.items():
            if pid not in (keeper, restart["player_id"]):
                self.assertFalse(in_penalty_area(pos, "away", 1))
                self.assertGreaterEqual(distance(pos, restart["start"]), 9.15)
                self.assertLess(pos["x_m"], 94)

    def test_penalty_is_completed_when_setup_crosses_the_whistle(self):
        sim = scenario()
        sim.clock.announce()
        sim.t = sim.clock.end-1
        sim.handle_foul(incident(sim, location=point(94, 34), effort=.6, timing=160))
        self.assertTrue(any(e["type"] == "shot" and e.get("set_piece_type") == "penalty" for e in sim.events))

    def test_below_seven_abandons_without_extra_substitute(self):
        sim = scenario()
        for actor in ("away-02", "away-03", "away-04", "away-05", "away-06"):
            tackle = incident(sim, actor=actor, effort=.99, timing=350)
            foul = sim.emit("foul", "away", actor, victim_id="home-07", decision=tackle["decision"], restart=foul_restart(sim.ball, "away", 1, "late_contact_challenge"), location=sim.ball.copy(), tackle_event_id=tackle["event_id"])
            stop = sim.emit("stoppage", reason="foul", source_event_id=foul["event_id"], restart=foul["restart"])
            sim.issue_card(foul, stop["event_id"])
        self.assertTrue(sim.abandoned)
        self.assertEqual(len(sim.pitch.team_positions("away")), 6)
        self.assertEqual(sim.events[-1]["type"], "match_abandoned")


class ConnectedDisciplineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matches = [generate(seed)[:2] for seed in (0, 6, 32, 54, 55)]

    def test_natural_seeds_cover_selected_fouls_restart_and_dismissal_paths(self):
        kinds, restarts, dismissals, advantages = set(), set(), set(), set()
        for metadata, events in self.matches:
            validate(metadata, events)
            kinds |= {e["type"] for e in events}
            restarts |= {e["reason"] for e in events if e["type"] == "restart"}
            dismissals |= {e["reason"] for e in events if e["type"] == "dismissal"}
            advantages |= {e["outcome"] for e in events if e["type"] == "advantage"}
        self.assertTrue(kinds >= {"tackle", "foul", "card", "dismissal", "carry"})
        self.assertTrue(restarts >= {"direct_free_kick", "indirect_free_kick", "penalty"})
        self.assertEqual(dismissals, {"direct_red", "second_yellow"})
        self.assertTrue(advantages >= {"pending", "played", "recalled"})

    def test_player_team_counts_minutes_and_v2_ratings_reconcile(self):
        keys = ("fouls_committed", "fouls_won", "yellow_cards", "red_cards", "second_yellow_dismissals",
                "free_kicks", "direct_free_kicks", "indirect_free_kicks", "penalties_won", "penalties_conceded", "penalties_taken", "penalties_scored", "penalties_missed")
        for metadata, events in self.matches:
            stats = calculate_statistics(metadata, events)
            self.assertEqual(stats["player_rating_model"]["version"], "matchlens-event-rating-v2")
            for team, aggregate in stats["teams"].items():
                players = [p for p in stats["players"].values() if p["team_id"] == team]
                for key in keys:
                    self.assertEqual(sum(p[key] for p in players), aggregate[key], key)
                for key in ("attempted", "won", "foul", "missed"):
                    self.assertEqual(sum(p["tackles"][key] for p in players), aggregate["tackles"][key])
                deficit = sum(metadata["match_duration_ms"]-e["match_time_ms"] for e in events if e["type"] == "dismissal" and e["team_id"] == team)
                self.assertEqual(sum(p["minutes_played_ms"] for p in players), 11*metadata["match_duration_ms"]-deficit)
            for e in (e for e in events if e["type"] == "dismissal"):
                off = e["player_id"]
                self.assertFalse(any(x.get("player_id") == off for x in events[e["sequence"]:]))
                self.assertFalse(any(off in x.get("pitch_snapshot", {}).get("players", {}) for x in events[e["sequence"]:]))

    def test_corrupt_penalty_card_and_inactive_actor_are_rejected(self):
        for metadata, events in self.matches:
            for kind in ("foul", "card", "dismissal"):
                if not any(e["type"] == kind for e in events):
                    continue
                changed = copy.deepcopy(events)
                event = next(e for e in changed if e["type"] == kind)
                if kind == "foul":
                    event["restart"]["team_id"] = event["team_id"]
                elif kind == "card":
                    event["card"] = "red" if event["card"] == "yellow" else "yellow"
                else:
                    following = next(e for e in changed[event["sequence"]:] if e["type"] == "pass")
                    following["team_id"], following["player_id"] = event["team_id"], event["player_id"]
                with self.assertRaises(ValueError):
                    validate(metadata, changed)

    def test_legacy_rating_model_is_preserved(self):
        base = Path(__file__).resolve().parents[1]/"data"/"examples"/"restarts-match"
        metadata = json.loads((base/"metadata.json").read_text())
        events = [json.loads(line) for line in (base/"events.jsonl").read_text().splitlines()]
        self.assertEqual(calculate_statistics(metadata, events)["player_rating_model"]["version"], "matchlens-event-rating-v1")


if __name__ == "__main__":
    unittest.main()
