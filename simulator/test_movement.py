import copy
import unittest

from simulator.engine import generate
from simulator.generate import validate
from simulator.movement import advance, passing_options
from simulator.pitch import PitchState, point, distance, resolve_pass
from simulator.statistics import calculate_statistics
from simulator.test_discipline import scenario


class MovementTests(unittest.TestCase):
    def test_acceleration_and_speed_are_bounded_for_free_steering(self):
        pitch = PitchState(1)
        owner, ball = "home-07", pitch.positions["home-07"].copy()
        original = copy.deepcopy(pitch.positions)
        advance(pitch,200,"home",owner,ball,0,carry=True)
        for pid,pos in pitch.positions.items():
            self.assertLessEqual(distance(original[pid],pos), .1002)
        velocities = pitch.velocities.copy()
        advance(pitch,200,"away","away-07",pitch.positions["away-07"],200,carry=True)
        for pid,(vx,vy) in pitch.velocities.items():
            self.assertLessEqual((vx*vx+vy*vy)**.5,4.5001)
            ox,oy = velocities[pid]
            self.assertLessEqual(((vx-ox)**2+(vy-oy)**2)**.5,.5001)

    def test_carrier_and_support_move_from_generated_state(self):
        pitch = PitchState(1)
        owner, ball = "home-07", pitch.positions["home-07"].copy()
        original = copy.deepcopy(pitch.positions)
        samples,end = advance(pitch,2200,"home",owner,ball,1000,carry=True)
        self.assertGreater(distance(ball,end),1)
        self.assertGreater(sum(distance(original[p],q)>.2 for p,q in pitch.positions.items()),10)
        self.assertEqual(samples[0]["period_time_ms"],1000)
        self.assertEqual(samples[-1]["period_time_ms"],3200)
        self.assertTrue(all(s["ball"] == s["players"][owner] for s in samples))

    def test_lead_target_uses_receiver_velocity_and_closed_lane_is_disfavoured(self):
        pitch = PitchState(1)
        pitch.positions["home-07"] = point(20,34)
        pitch.positions["home-10"] = point(50,34)
        for pid in pitch.team_positions("away"):
            pitch.positions[pid] = point(104,66)
        pitch.velocities = {"home-10":(2.,1.)}
        options = passing_options(pitch,"home-07",point(20,34))
        forward = next(o for o in options if o["player_id"] == "home-10")
        self.assertEqual(forward["target"],point(51.2,34.6))
        pitch.positions["away-03"] = point(35,34.3)
        blocked = next(o for o in passing_options(pitch,"home-07",point(20,34)) if o["player_id"] == "home-10")
        self.assertIsNotNone(blocked["predicted_interceptor_id"])
        self.assertLess(blocked["score"],forward["score"]*.2)

    def test_receiver_must_reach_target_and_defender_has_reaction_delay(self):
        result = resolve_pass(point(20,34),point(30,34),point(30,34),{},16,
                              reaction_s=.25,receiver_start=point(25,34))
        self.assertEqual(result["reason"],"missed_target")
        near = {"away-03":point(22,34.3)}
        self.assertEqual(resolve_pass(point(20,34),point(30,34),point(30,34),near,20)["reason"],"intercepted")
        self.assertEqual(resolve_pass(point(20,34),point(30,34),point(30,34),near,20,reaction_s=.25)["outcome"],"complete")

    def test_compressed_goal_restart_records_bounded_return_paths_and_extra_time(self):
        sim = scenario()
        sim.ball = point(105,34)
        sim.dead_ball({"type":"kickoff","team_id":"away","location":point(52.5,34)},sim.events[0]["event_id"],goal=True)
        path = next(e for e in sim.events if e["type"] == "reposition" and e["reason"] == "return_for_kickoff")
        for a,b in zip(path["player_motion"],path["player_motion"][1:]):
            for pid in a["players"]:
                self.assertLessEqual(distance(a["players"][pid],b["players"][pid]),4.5*(b["period_time_ms"]-a["period_time_ms"])/1000+.003)
        self.assertEqual(path["start"],path["end"])
        self.assertTrue(any(e["type"] == "time_lost" and e["reason"] == "restart_repositioning" for e in sim.events))


class MovementStreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata,cls.events,_ = generate(42,minutes_per_half=1)

    def test_motion_exists_during_control_and_pass_flight_without_fake_stats(self):
        validate(self.metadata,self.events)
        moves = [e for e in self.events if e["type"] == "movement"]
        self.assertTrue(moves)
        action = next(e for e in self.events if e["type"] == "pass")
        frames = action["player_motion"]
        self.assertGreater(sum(frames[0]["players"][p] != frames[-1]["players"][p] for p in frames[0]["players"]),5)
        stats = calculate_statistics(self.metadata,self.events)
        self.assertEqual(sum(t["passes"]["attempted"] for t in stats["teams"].values()),sum(e["type"] == "pass" for e in self.events))
        movement_ids = {e["event_id"] for e in moves}
        self.assertFalse(any(movement_ids.intersection(p["rating"]["evidence_event_ids"]) for p in stats["players"].values()))

    def test_corrupt_motion_or_carrier_is_rejected(self):
        for field in ("position","carrier","clock"):
            events = copy.deepcopy(self.events)
            e = next(e for e in events if e["type"] == "movement")
            if field == "position": e["player_motion"][1]["players"]["home-02"]["x_m"] = 105
            elif field == "carrier": e["carrier_id"] = "home-20"
            else: e["player_motion"][1]["period_time_ms"] = -1
            with self.assertRaises(ValueError): validate(self.metadata,events)


if __name__ == "__main__":
    unittest.main()
