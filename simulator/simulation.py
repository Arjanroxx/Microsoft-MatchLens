"""Connected ball/control/restart state machine for schema 1.8."""
import math
import random

from simulator.clock import PeriodClock
from simulator.metrics import ball_speed, make_trajectory, pass_difficulty
from simulator.pitch import PitchState, distance, pass_context, point, resolve_pass
from simulator.player_statistics import PlayerStatistics
from simulator.restarts import award_restart, first_exit, other, parry_target, raw_point, resolve_shot
from simulator.substitutions import SubstitutionManager
from simulator.discipline import resolve_challenge, foul_restart, separation_target, in_penalty_area
from simulator.offside import contact_frame, contact_for, interference, touch_control, deflection_target
from simulator.movement import advance as advance_movement, passing_options
from simulator.xg import MODEL as XG_MODEL, shot_xg


class Simulation:
    def __init__(self, metadata, rng, progression, scenario, start, end):
        self.metadata, self.rng, self.progression = metadata, rng, progression
        self.scenario, self.window = scenario, (start, end)
        self.duration = metadata["period_duration_ms"]
        self.scale = self.duration / 2_700_000
        self.roster = {p["player_id"]: p for p in metadata["players"]}
        self.events, self.score, self.counter = [], {"home": 0, "away": 0}, 0
        self.players = PlayerStatistics(metadata)
        self.manager = SubstitutionManager(metadata["seed"], self.duration, self.roster)
        self.offset = 0
        self.pending_cards = []
        self.abandoned = False
        self.offside_phase = None
        metadata["expected_goals_model"] = XG_MODEL.copy()
        self.previous_passer = None
        metadata["movement_model"] = {"version":"support-steering-v1", "integration_step_ms":200,
            "sample_interval_ms":500, "outfield_speed_cap_mps":4.5, "steering_acceleration_mps2":2.5,
            "carrier_speed_cap_mps":2.4, "passing":"lane-aware lead targets; 250ms defender reaction",
            "limitations":"original uncalibrated heuristics; planned contact runs and restart movement remain simplified"}
        self.modern_motion = metadata["schema_version"] in ("1.8","1.9")
        self.contact_rng = random.Random(f"{metadata['seed']}-challenges-v1")
        metadata.update(period_offsets_ms={"1": 0}, period_actual_durations_ms={},
                        clock_model="period_plus_added_time_v1")
        metadata["simulation_model"].update(ball_radius_m=.11, shot_outcome="goal-mouth / keeper contact geometry",
            restart_model="whole-ball first boundary and last touch; explicit dead-ball placement and delivery",
            added_time="qualifying lost-time ledger, rounded-up scaled minute minimum; further losses extend it")
        metadata["discipline_model"] = {"version": "challenge-contact-v1", "laws": "IFAB 2026/27 selected offences",
            "challenge_probability_per_eligible_decision": .12, "max_challenge_start_distance_m": 2.5,
            "advantage": "one bounded carry evaluation; direct careless/reckless non-penalty offences only",
            "goalkeeper_dismissal": "active outfielder becomes emergency keeper; no extra player enters"}
        metadata["offside_model"] = {"version": "law11-point-player-v1", "law": "IFAB Law 11, selected 2D involvement",
            "contact": "first teammate kick/touch; all active opponents including emergency keepers",
            "involvement": ["touch", "interfere_opponent", "gain_advantage_save", "gain_advantage_deflection"],
            "interference_proxy": "candidate between ball and keeper, within 0.35m sight corridor and 3m of keeper",
            "opponent_control": "planar-controllability-v1: >=0.5s flight, <=18m/s, >=0.2s spare running reach",
            "exempt_direct_restarts": ["throw_in", "goal_kick", "corner_kick"],
            "limitations": "point players, no body parts, aerial/visual tracking, VAR reviews, off-field defenders or goalkeeper throws"}

    def emit(self, kind, team=None, player=None, possession=None, at=None, **fields):
        stamp = self.t if at is None else at
        event = {"schema_version": self.metadata["schema_version"], "match_id": self.metadata["match_id"],
                 "event_id": f"evt-{len(self.events) + 1:06}", "sequence": len(self.events) + 1,
                 "period": self.period, "period_time_ms": stamp, "match_time_ms": self.offset + stamp,
                 "type": kind, "source": "synthetic", "team_id": team, "player_id": player,
                 "possession_id": possession, **fields}
        self.events.append(event)
        self.players.update(event)
        return event

    def offside_frame(self, restart_type=None):
        return contact_frame(self.positions(), self.ball, self.team, self.owner,
                             self.period, self.roster, restart_type)

    def whistle_offside(self, source, offender, involvement, location=None, via=None):
        """Adjudicate before recovery, shot credit or goal can be committed."""
        location = (location or self.ball).copy()
        # IFK is at involvement, including when a flagged attacker returns to
        # their own half. Point-player pitch locations are bounded.
        location = point(location["x_m"], location["y_m"])
        frame = contact_for(source, self.roster)
        if offender not in frame["candidates"]:
            raise ValueError("Offside offence without a source-position candidate")
        award = {"type": "indirect_free_kick", "team_id": other(source["team_id"]),
                 "location": location, "reason": "offside"}
        event = self.emit("offside", source["team_id"], offender,
                          source_event_id=source["event_id"], involvement=involvement,
                          location=location, via_event_id=via, contact=frame,
                          positions_after=self.positions(),
                          contact_period_time_ms=source["pitch_snapshot"]["period_time_ms"],
                          restart=award)
        self.pending_rebound = self.pending_clearance = False
        return self.dead_ball(award, event["event_id"])

    def opponent_contact(self, action, defender):
        """Deliberate play resets the phase; deflection preserves its source."""
        speed = action.get("kick", {}).get("commanded_mean_speed_mps", action.get("commanded_mean_speed_mps"))
        original = action["pitch_snapshot"]["players"][defender]
        evidence = touch_control(action["start"], self.ball, original, speed)
        self.pitch.move(defender, self.ball, action["ball_speed"]["duration_ms"]/1000+.001)
        touch = self.emit("opponent_touch", self.roster[defender]["team_id"], defender,
                          start=self.ball.copy(), source_event_id=action["event_id"], control=evidence,
                          positions_after=self.positions())
        if evidence["resets_offside"]:
            self.offside_phase = None
            self.recover(defender, "deliberate_play")
            return True
        self.offside_phase = action
        target = deflection_target(action["start"], self.ball, original)
        crossing = first_exit(self.ball, target)
        self.team, self.owner, self.possession_id = self.roster[defender]["team_id"], defender, None
        rebound = self.flight("deflection", crossing["location"] if crossing else target, max(4, speed*.3),
                              source_event_id=action["event_id"], touch_event_id=touch["event_id"],
                              commanded_mean_speed_mps=max(4, speed*.3))
        if crossing:
            return self.ball_out(crossing, self.team, defender, rebound["event_id"])
        winner = min(self.pitch.positions, key=lambda p: distance(self.pitch.positions[p], self.ball))
        if winner in contact_for(action, self.roster)["candidates"]:
            before_recovery = self.snapshot()
            travel = distance(self.pitch.positions[winner], self.ball)/4.5
            self.pitch.move(winner, self.ball, travel+.001)
            self.tick(math.ceil(travel*1000))
            self.record_reposition(before_recovery,"loose_ball_recovery")
            return self.whistle_offside(action, winner, "gain_advantage_deflection", via=rebound["event_id"])
        self.recover(winner, "deflection_loose_ball")
        self.offside_phase = None
        return True

    def tick(self, milliseconds):
        """Announce at regulation exactly, even if it falls inside a gap/flight."""
        target = self.t + milliseconds
        if self.clock.announced is None and target >= self.duration:
            self.emit("added_time", at=self.duration, minimum_added_ms=self.clock.announce(),
                      lost_time_ms=self.clock.lost_ms, rounding_quantum_ms=self.clock.quantum,
                      evidence_event_ids=[r["source_event_id"] for r in self.clock.losses])
        self.t = target

    def lost(self, start, end, reason, source):
        self.clock.lost(start, end, reason, source)
        self.emit("time_lost", reason=reason, start_ms=start, end_ms=end,
                  duration_ms=end-start, source_event_id=source)

    def possession(self):
        self.counter += 1
        self.possession_id = f"pos-{self.counter:05}"

    def behaviour(self):
        if self.scenario == "match":
            states = self.progression.states(self.period, self.t)
            return (states[other(self.team)] == "higher-press", states[self.team] == "patient",
                    states[self.team] == "quick-play")
        active = self.window[0] <= self.t < self.window[1]
        return (self.scenario == "high-press" and active and self.team == "away",
                self.scenario == "quiet-possession" and active, self.scenario == "chaotic" and active)

    def substitutions(self, stop_id, halftime=False):
        for team, plan in self.manager.due(self.period, self.t):
            if plan["halftime"] != halftime:
                continue
            current = self.players.snapshot(self.offset + self.t)
            choices, candidates = self.manager.select(team, self.pitch.positions, current, plan["count"])
            if not choices:
                continue
            window = f"subs-{team}-{self.manager.used[team] + 1:02}"
            if not halftime:
                self.manager.windows[team] += 1
            for off, on in choices:
                slot = self.pitch.slots[off]
                self.pitch.substitute(off, on)
                self.manager.used[team] += 1
                self.manager.used_players.add(on)
                self.emit("substitution", team, player_off_id=off, player_on_id=on, window_id=window,
                          halftime=halftime, stoppage_event_id=stop_id, formation_slot=slot,
                          position_group=self.roster[off]["position_group"], positions_after=self.positions(),
                          selection={"reason": "lowest_rated_eligible_outfield_starter",
                                     "rating_model": current[off]["rating"]["model"],
                                     "player_off_rating": current[off]["rating"]["value"],
                                     "eligible_candidate_ratings": candidates,
                                     "evidence_up_to_sequence": self.events[-1]["sequence"]})
            if not halftime:
                start = self.t
                self.tick(max(500, round(20_000 * self.scale)))
                self.lost(start, self.t, "substitutions", stop_id)

    def positions(self):
        return {pid: p.copy() for pid, p in self.pitch.positions.items()}

    def snapshot(self):
        return {"period_time_ms": self.t, "players": self.positions()}

    def flight(self, kind, end, speed, **fields):
        start, snapshot = self.ball.copy(), self.snapshot()
        if kind == "shot":
            fields["xg"] = shot_xg({"type":"shot","start":start,"pitch_snapshot":snapshot,
                                    "team_id":self.team,"period":self.period,**fields},self.roster)
        if kind in ("shot", "clearance", "parry"):
            self.emit("ball_release", self.team, self.owner, action_type=kind, start=start.copy())
        trajectory = make_trajectory(start, end, self.t, speed, decelerate=kind == "shot")
        motion = None
        if self.modern_motion:
            contact = fields.get("recipient_id") or fields.get("interceptor_id") or fields.get("deflector_id")
            if fields.get("outcome_reason") == "offside" and kind in ("pass", "restart_delivery"):
                contact = fields.get("intended_recipient_id")
            if kind == "shot" and fields.get("outcome_reason") == "saved":
                contact = fields["goalkeeper_id"]
            if kind == "carry":
                contact = self.owner
            motion, _ = advance_movement(self.pitch, trajectory[-1]["period_time_ms"]-self.t,
                                          self.team, None, self.ball, self.t,
                                          contacts={contact:end} if contact else None, ball_path=(start,end))
            # The ball's authoritative observations are ball_trajectory. Do
            # not export the steering planner's approximate ball references.
            motion = [{"period_time_ms":s["period_time_ms"], "players":s["players"]} for s in motion]
        self.tick(trajectory[-1]["period_time_ms"] - self.t)
        event = self.emit(kind, self.team, self.owner, self.possession_id, start=start, end=end,
                          pitch_snapshot=snapshot, ball_trajectory=trajectory, ball_speed=ball_speed(trajectory),
                          **({"player_motion": motion, "positions_after": self.positions()} if motion else {}), **fields)
        self.ball = end.copy()
        return event

    def advance_play(self, milliseconds, press=False):
        start, snapshot = self.ball.copy(), self.snapshot()
        motion, end = advance_movement(self.pitch, milliseconds, self.team, self.owner,
                                      self.ball, self.t, press=press, carry=True)
        self.tick(milliseconds)
        self.ball = end
        self.emit("movement", self.team, possession=self.possession_id, carrier_id=self.owner,
                  start=start, end=end.copy(), pitch_snapshot=snapshot, player_motion=motion,
                  positions_after=self.positions(),
                  ball_trajectory=[{"period_time_ms":s["period_time_ms"], **s["ball"]} for s in motion],
                  motion_model="support-steering-v1")

    def record_reposition(self, before, reason):
        """Expose existing bounded recovery/setup runs instead of drawing jumps."""
        if not self.modern_motion or self.t <= before["period_time_ms"]:
            return
        duration = self.t-before["period_time_ms"]
        samples = []
        for elapsed in list(range(0,duration,500))+[duration]:
            u = elapsed/duration
            samples.append({"period_time_ms":before["period_time_ms"]+elapsed,
                "players":{p:point(q["x_m"]+(self.pitch.positions[p]["x_m"]-q["x_m"])*u,
                                    q["y_m"]+(self.pitch.positions[p]["y_m"]-q["y_m"])*u)
                           for p,q in before["players"].items()}})
        self.emit("reposition", start=self.ball.copy(), end=self.ball.copy(), reason=reason,
                  pitch_snapshot=before, player_motion=samples, positions_after=self.positions(),
                  ball_trajectory=[{"period_time_ms":s["period_time_ms"],**self.ball} for s in samples])

    def recover(self, pid, reason):
        """Loose balls stay at their endpoint while the nearest eligible actor runs."""
        before = self.snapshot()
        seconds = distance(self.pitch.positions[pid], self.ball) / self.pitch.RUN_SPEED_MPS
        self.pitch.move(pid, self.ball, seconds + .001)
        self.tick(math.ceil(seconds * 1000))
        self.record_reposition(before,"loose_ball_recovery")
        self.team, self.owner = self.roster[pid]["team_id"], pid
        self.possession()
        self.emit("recovery", self.team, pid, self.possession_id, start=self.ball.copy(), reason=reason,
                  positions_after=self.positions())

    def keeper(self, team):
        return next(pid for pid, slot in self.pitch.slots.items() if slot == 1 and self.roster[pid]["team_id"] == team)

    def issue_card(self, foul, stop_id):
        actor, team, card = foul["player_id"], foul["team_id"], foul["decision"]["card"]
        if card is None or actor not in self.pitch.positions:
            return
        self.emit("card", team, actor, card=card, reason="serious_foul_play" if card == "red" else "reckless_challenge",
                  foul_event_id=foul["event_id"], stoppage_event_id=stop_id,
                  caution_number=self.players.players[actor]["yellow_cards"]+1 if card == "yellow" else None)
        second = card == "yellow" and self.players.players[actor]["yellow_cards"] == 2
        if card == "red" or second:
            was_keeper = self.pitch.slots[actor] == 1
            self.pitch.dismiss(actor)
            self.emit("dismissal", team, actor, reason="second_yellow" if second else "direct_red",
                      foul_event_id=foul["event_id"], stoppage_event_id=stop_id, positions_after=self.positions())
            if len(self.pitch.team_positions(team)) < 7:
                self.abandoned = True
                self.emit("match_abandoned", reason="fewer_than_seven_players", affected_team_id=team)
                return
            if was_keeper:
                replacement = min(self.pitch.team_positions(team), key=lambda pid: distance(self.pitch.positions[pid],
                    point(2 if self.pitch.direction(team) == 1 else 103, 34)))
                self.pitch.slots[replacement] = 1
                self.emit("goalkeeper_change", team, replacement, previous_goalkeeper_id=actor,
                          reason="emergency_after_dismissal", formation_slot=1, positions_after=self.positions())

    def flush_cards(self, stop_id):
        cards, self.pending_cards = self.pending_cards, []
        for foul in cards:
            self.issue_card(foul, stop_id)
            if self.abandoned:
                break
            start = self.t
            self.tick(max(250, round(8000*self.scale)))
            self.lost(start, self.t, "disciplinary_administration", stop_id)

    def challenge(self):
        """A reachable defender may choose a challenge; no fabricated incident."""
        if self.pitch.slots[self.owner] == 1:
            return None  # do not model challenges on a keeper holding the ball
        candidates = [p for p in self.pitch.team_positions(other(self.team))
                      if distance(self.pitch.positions[p], self.ball) <= 2.5
                      and not any(f["player_id"] == p for f in self.pending_cards)]
        if not candidates or self.contact_rng.random() >= .12:
            return None
        tackler = min(candidates, key=lambda p: distance(self.pitch.positions[p], self.ball))
        # Move for an actual 0.25s lunge. The same bounded pitch state feeds
        # the recorded contact evidence and the subsequent outcome.
        controls = {"effort": round(self.contact_rng.uniform(.2, 1), 4),
                    "timing_error_ms": self.contact_rng.randint(-120, 360),
                    "technique": "raised_boot" if self.contact_rng.random() < .08 else "standing_tackle"}
        target = self.ball
        if controls["technique"] == "raised_boot":
            # A non-contact high boot threatens the nearby carrier without
            # first lunging all the way through them as a ground tackle would.
            pos = self.pitch.positions[tackler]
            gap = distance(pos, self.ball)
            if gap > 1.2:
                target = point(self.ball["x_m"]+(pos["x_m"]-self.ball["x_m"])*1.2/gap,
                               self.ball["y_m"]+(pos["y_m"]-self.ball["y_m"])*1.2/gap)
        self.pitch.move(tackler, target, .25)
        self.tick(250)
        decision = resolve_challenge(self.ball, self.pitch.positions[tackler], **controls)
        victim, attacking = self.owner, self.team
        tackle = self.emit("tackle", other(attacking), tackler, victim_id=victim, location=self.ball.copy(),
                           outcome=decision["outcome"], controls=controls, decision=decision,
                           challenge_snapshot={"players": self.positions(), "period_time_ms": self.t})
        if decision["outcome"] == "missed":
            return None
        self.pending_rebound = self.pending_clearance = False
        if decision["outcome"] == "won":
            self.emit("turnover", attacking, victim, self.possession_id, start=self.ball.copy(), reason="clean_tackle")
            self.recover(tackler, "clean_tackle")
            return True
        return self.handle_foul(tackle)

    def handle_foul(self, tackle):
        actor, team, victim = tackle["player_id"], tackle["team_id"], tackle["victim_id"]
        decision = tackle["decision"]
        award = foul_restart(tackle["location"], team, self.period, decision["offence"])
        foul = self.emit("foul", team, actor, victim_id=victim, location=tackle["location"].copy(),
                         tackle_event_id=tackle["event_id"], decision=decision, restart=award)
        # The referee considers advantage only if an attacking continuation is
        # plausible, never for serious foul play or a pending second caution.
        progress = self.ball["x_m"] if self.pitch.direction(self.team) == 1 else 105-self.ball["x_m"]
        advantage = (award["type"] == "direct_free_kick" and decision["card"] != "red"
                     and not (decision["card"] == "yellow" and self.players.players[actor]["yellow_cards"] >= 1)
                     and progress > 50 and self.contact_rng.random() < .5)
        if advantage:
            self.emit("advantage", self.team, victim, self.possession_id, foul_event_id=foul["event_id"], outcome="pending")
            target = point(self.ball["x_m"]+self.pitch.direction(self.team)*3, self.ball["y_m"])
            # Assess the actual lane after defenders have a short reaction.
            self.pitch.advance(.5, self.team, victim, self.ball, press=True)
            self.tick(500)
            opponents = {p: pos for p, pos in self.pitch.team_positions(team).items() if p != actor}
            safe = distance(self.ball, target) >= 1 and min(distance(pos, target) for pos in opponents.values()) > 2.5
            if safe:
                carry = self.flight("carry", target, 4, foul_event_id=foul["event_id"], commanded_mean_speed_mps=4)
                self.pitch.positions[victim] = target.copy()
                self.emit("advantage", self.team, victim, self.possession_id, foul_event_id=foul["event_id"], outcome="played",
                          continuation_event_id=carry["event_id"])
                if decision["card"]:
                    self.pending_cards.append(foul)
                return True
            self.emit("advantage", self.team, victim, self.possession_id, foul_event_id=foul["event_id"], outcome="recalled")
        if decision["card"]:
            self.pending_cards.append(foul)
        return self.dead_ball(award, foul["event_id"])

    def dead_ball(self, award, source, goal=False, initial=False):
        self.offside_phase = None
        is_foul = award["type"] in ("direct_free_kick", "indirect_free_kick", "penalty")
        stop = self.emit("stoppage", reason="offside" if award.get("reason") == "offside" else "goal_celebration" if goal else "period_interval" if initial else "foul" if is_foul else "ball_out",
                         source_event_id=source, restart=award, start=self.ball.copy())
        self.flush_cards(stop["event_id"])
        if self.abandoned:
            return False
        self.substitutions(stop["event_id"], halftime=initial and self.period == 2)
        start = self.t
        preparation_before = self.snapshot()
        ranges = {"throw_in": (8000, 16000), "goal_kick": (12000, 20000), "corner_kick": (15000, 24000),
                  "direct_free_kick": (16000, 26000), "indirect_free_kick": (10000, 18000), "penalty": (35000, 50000),
                  "kickoff": (35000, 55000) if goal else (0, 0)}
        prep = round(self.rng.uniform(*ranges[award["type"]]) * self.scale)
        self.tick(prep)
        if goal:
            self.lost(start, self.t, "goal_celebration", stop["event_id"])
        else:
            # Only the excess over a transparent allowance is recovered, not
            # every ordinary second with the ball out of play.
            allowance = round(12_000 * self.scale)
            if prep > allowance:
                self.lost(start + allowance, self.t, "excess_restart_delay", stop["event_id"])
        # A half may end with a pending restart. Do not force a kick after time.
        if not initial and award["type"] != "penalty" and self.clock.announced is not None and self.t >= self.clock.end:
            return False
        self.team = award["team_id"]
        location = award["location"]
        if award["type"] == "kickoff":
            before = preparation_before if goal else self.snapshot()
            self.pitch = PitchState(self.period, self.pitch.slots)
            for pid, pos in self.pitch.positions.items():
                direction = self.pitch.direction(self.roster[pid]["team_id"])
                pos["x_m"] = min(pos["x_m"], 51) if direction == 1 else max(pos["x_m"], 54)
            if self.modern_motion and not initial:
                travel = max(distance(before["players"][p],q) for p,q in self.pitch.positions.items())/4.5
                # Returning to shape takes place during the celebration/prep
                # already on the clock. Extend only a compressed demo whose
                # preparation was shorter than the physically needed journey.
                extra = max(0, math.ceil(travel*1000)-(self.t-before["period_time_ms"]))
                extra_start = self.t
                self.tick(extra)
                self.record_reposition(before,"return_for_kickoff")
                if extra:
                    self.lost(extra_start,self.t,"restart_repositioning",stop["event_id"])
            taker = next((p for p, s in self.pitch.slots.items() if self.roster[p]["team_id"] == self.team and s == 7),
                         next(p for p in self.pitch.team_positions(self.team) if self.pitch.slots[p] != 1))
        elif award["type"] == "goal_kick":
            taker = self.keeper(self.team)
        elif award["type"] in ("penalty", "direct_free_kick"):
            taker = max((p for p in self.pitch.team_positions(self.team) if self.pitch.slots[p] != 1), key=lambda p: self.roster[p]["shooting_skill"])
        else:
            eligible = [pid for pid in self.pitch.team_positions(self.team) if self.pitch.slots[pid] != 1]
            taker = min(eligible, key=lambda p: distance(self.pitch.positions[p], location))
        # The ball is explicitly carried/placed while dead; no open-play jump.
        self.emit("ball_placement", start=self.ball.copy(), end=location.copy(), reason=award["type"],
                  stoppage_event_id=stop["event_id"], restart_team_id=self.team)
        self.ball = location.copy()
        taker_before = self.snapshot()
        travel = distance(self.pitch.positions[taker], location) / self.pitch.RUN_SPEED_MPS
        self.pitch.move(taker, location, travel + .001)
        if award["type"] != "kickoff":
            before = self.t
            self.tick(math.ceil(travel * 1000))
            self.record_reposition(taker_before,"restart_taker")
            # Set-up movement can exceed the normal allowance; account for it.
            if travel:
                self.lost(before, self.t, "restart_repositioning", stop["event_id"])
        # Planar legal set-up constraints; simultaneous movement consumes the
        # maximum travel time, never a sum of individual journeys.
        targets = {}
        for pid, pos in self.pitch.positions.items():
            if award["type"] == "penalty":
                if pid == self.keeper(other(self.team)):
                    targets[pid] = point(105 if self.pitch.direction(self.team) == 1 else 0, 34)
                elif pid != taker:
                    targets[pid] = point(min(pos["x_m"], 84) if self.pitch.direction(self.team) == 1 else max(pos["x_m"], 21), pos["y_m"])
                continue
            if self.roster[pid]["team_id"] == self.team:
                continue
            if award["type"] in ("direct_free_kick", "indirect_free_kick") and self.pitch.slots[pid] == 1:
                goal_x = 105 if self.pitch.direction(self.team) == 1 else 0
                if distance(location, point(goal_x, 34)) < 12:
                    targets[pid] = point(goal_x, max(30.5, min(37.5, pos["y_m"])))
                    continue  # own goal line, between posts, distance exception
            if award["type"] in ("throw_in", "corner_kick", "kickoff", "direct_free_kick", "indirect_free_kick"):
                minimum = 2 if award["type"] == "throw_in" else 9.15
                gap = distance(pos, location)
                if gap < minimum:
                    targets[pid] = separation_target(pos, location, minimum)
            elif award["type"] == "goal_kick":
                own_left = self.pitch.direction(self.team) == 1
                inside_x = pos["x_m"] < 16.5 if own_left else pos["x_m"] > 88.5
                if inside_x and 13.84 < pos["y_m"] < 54.16:
                    targets[pid] = point(17 if own_left else 88, pos["y_m"])
            if award["type"] in ("direct_free_kick", "indirect_free_kick") and in_penalty_area(location, self.team, self.period):
                candidate = targets.get(pid, pos)
                if in_penalty_area(candidate, self.team, self.period):
                    left = self.pitch.direction(self.team) == 1
                    targets[pid] = point(max(17, location["x_m"]+10) if left else min(88, location["x_m"]-10), candidate["y_m"])
        if award["type"] == "corner_kick":
            target = point(90 if self.pitch.direction(self.team) == 1 else 15, 34)
            mates = [p for p in self.pitch.team_positions(self.team) if p != taker and self.roster[p]["role"] != "GK"]
            recipient = min(mates, key=lambda p: distance(self.pitch.positions[p], target))
            targets[recipient] = target
        setup_seconds = max((distance(self.pitch.positions[p], target)/4.5 for p, target in targets.items()), default=0)
        before_setup = self.snapshot()
        for pid, target in targets.items():
            self.pitch.move(pid, target, setup_seconds+.001)
        if setup_seconds:
            before = self.t
            self.tick(math.ceil(setup_seconds*1000))
            self.record_reposition(before_setup,"restart_setup")
            if award["type"] != "kickoff":
                self.lost(before, self.t, "restart_repositioning", stop["event_id"])
        if not initial and award["type"] != "penalty" and self.clock.announced is not None and self.t >= self.clock.end:
            return False
        self.owner = taker
        self.possession()
        # Kickoff control is immediate. Other restarts become live at delivery
        # release, not when the award/placement is made.
        restart = self.emit("restart", self.team, taker, self.possession_id, start=self.ball.copy(),
                            reason=award["type"], ball_in_play=award["type"] == "kickoff",
                            stoppage_event_id=stop["event_id"], source_event_id=source,
                            positions_after=self.positions())
        if award["type"] != "kickoff":
            if award["type"] == "penalty" or (award["type"] == "direct_free_kick" and distance(self.ball, point(105 if self.pitch.direction(self.team) == 1 else 0, 34)) < 32 and self.rng.random() < .55):
                self.emit("resume", self.team, self.owner, self.possession_id, reason=award["type"], start=self.ball.copy())
                return self.shoot(set_piece_type=award["type"], restart_event_id=restart["event_id"])
            return self.deliver_restart(award["type"], restart["event_id"])
        return True

    def ball_out(self, crossing, last_team, last_player, source):
        award = award_restart(crossing, last_team, last_player, self.period)
        out = self.emit("ball_out", start=self.ball.copy(), boundary=crossing["boundary"],
                        crossing=crossing["location"], last_touch_team_id=last_team,
                        last_touch_player_id=last_player, source_event_id=source, restart=award)
        return self.dead_ball(award, out["event_id"])

    def deliver_restart(self, kind, restart_id):
        direction = self.pitch.direction(self.team)
        mates = [(p, v) for p, v in self.pitch.team_positions(self.team).items() if p != self.owner]
        if kind == "corner_kick":
            # Aim toward a teammate near the penalty area, never shoot a corner
            # directly in this model. Other players approach during preparation.
            target = point(90 if direction == 1 else 15, 34)
            recipient = min(mates, key=lambda row: distance(row[1], target))[0]
        else:
            recipient = min(mates, key=lambda row: distance(row[1], self.ball))[0]
        end = self.pitch.positions[recipient].copy()
        if distance(self.ball, end) < .2:
            # Distinct receiver moves a bounded amount to avoid zero-length kicks.
            end = point(end["x_m"] + direction, end["y_m"] + 1)
            self.pitch.move(recipient, end, 1)
            self.tick(1000)
        speed = 10 if kind == "throw_in" else 17
        self.emit("resume", self.team, self.owner, self.possession_id, reason=kind, start=self.ball.copy())
        result = resolve_pass(self.ball, end, end, self.pitch.team_positions(other(self.team)), speed, stop_at_boundary=True,
                              reaction_s=.25 if self.modern_motion else 0)
        frame = self.offside_frame(kind)
        flagged = result["outcome"] == "complete" and recipient in frame["candidates"]
        deflector = result["interceptor_id"] if result["interceptor_id"] and not touch_control(self.ball, result["end"], self.pitch.positions[result["interceptor_id"]], speed)["resets_offside"] else None
        delivery = self.flight("restart_delivery", result["end"], speed, restart_type=kind, restart_event_id=restart_id,
                    recipient_id=recipient if result["outcome"] == "complete" and not flagged else None,
                    intended_recipient_id=recipient, intended_end=end, interceptor_id=None if deflector else result["interceptor_id"], deflector_id=deflector,
                    outcome="incomplete" if flagged else result["outcome"],
                    outcome_reason="offside" if flagged else result["reason"], commanded_mean_speed_mps=speed)
        if flagged:
            self.pitch.positions[recipient] = point(self.ball["x_m"], self.ball["y_m"])
            return self.whistle_offside(delivery, recipient, "touch")
        if result["outcome"] == "complete":
            self.owner = recipient
            self.pitch.positions[recipient] = end.copy()
        else:
            self.emit("turnover", self.team, self.owner, self.possession_id, start=self.ball.copy(), reason="restart_intercepted")
            return self.opponent_contact(delivery, result["interceptor_id"])
        return True

    def pass_ball(self):
        opponent = other(self.team)
        press, quiet, chaotic = self.behaviour()
        mates = [(p, v) for p, v in self.pitch.team_positions(self.team).items()
                 if p != self.owner and 2 < distance(self.ball, v) < 55]
        if not mates:
            return
        defenders = self.pitch.team_positions(opponent)
        direction = self.pitch.direction(self.team)
        offside_candidates = self.offside_frame()["candidates"]
        weights = []
        for pid, target in mates:
            progress = direction * (target["x_m"] - self.ball["x_m"])
            openness = min(distance(target, v) for v in defenders.values())
            weights.append(max(.1, (2 + openness / 5) / (1 + distance(self.ball, target) / 30)
                               * (.4 if quiet and progress > 8 else 1 + max(progress, 0) / 12))
                           * (.04 if pid in offside_candidates else 1))
        recipient, intended = self.rng.choices(mates, weights=weights)[0]
        options = None
        if self.modern_motion:
            options = passing_options(self.pitch,self.owner,self.ball,quiet,self.previous_passer)
            if options:
                recipient, intended = self.rng.choices(
                    [(o["player_id"],o["target"]) for o in options],
                    weights=[o["score"]*(.04 if o["player_id"] in offside_candidates else 1) for o in options])[0]
        context = pass_context(self.ball, intended, defenders)
        if context["under_pressure"]:
            self.emit("pressure", opponent, context["nearest_defender_id"], self.possession_id,
                      start=self.pitch.positions[context["nearest_defender_id"]].copy(), target_player_id=self.owner)
        skill, effort = self.roster[self.owner]["passing_skill"], round(self.rng.uniform(.2, 1), 4)
        # Directional kick error is applied before boundary testing, never clamped.
        error = (1-skill) * (1 + distance(self.ball, intended)/12) * (2 if context["under_pressure"] else 1)
        error *= 1.45 if self.modern_motion else 1
        aimed = raw_point(intended["x_m"] + self.rng.uniform(-1, 1)*error,
                          intended["y_m"] + self.rng.uniform(-1, 1)*error)
        speed = min(24, 8 + .28*distance(self.ball, intended) + 3*effort)
        resolved = resolve_pass(self.ball, aimed, intended, defenders, speed, stop_at_boundary=True,
                                 reaction_s=.25 if self.modern_motion else 0,
                                 receiver_start=self.pitch.positions[recipient] if self.modern_motion else None)
        crossing = first_exit(self.ball, aimed) if resolved["reason"] == "out_of_play" else None
        if crossing:
            resolved.update(end=crossing["location"], outcome="incomplete", reason="out_of_play", interceptor_id=None)
        frame = self.offside_frame()
        flagged = resolved["outcome"] == "complete" and recipient in frame["candidates"]
        deflector = resolved["interceptor_id"] if resolved["interceptor_id"] and not touch_control(self.ball, resolved["end"], self.pitch.positions[resolved["interceptor_id"]], speed)["resets_offside"] else None
        # If the ball misses an in-field target it continues on the same ray
        # until a player can arrive, rather than granting the opposition control.
        action = self.flight("pass", resolved["end"], speed,
            recipient_id=recipient if resolved["outcome"] == "complete" and not flagged else None, intended_recipient_id=recipient,
            intended_end=intended.copy(), outcome="incomplete" if flagged else resolved["outcome"], outcome_reason="offside" if flagged else resolved["reason"],
            interceptor_id=None if deflector else resolved["interceptor_id"], deflector_id=deflector,
            **({"receiver_start":self.pitch.positions[recipient].copy(), "passing_options":options,
                "receiver_velocity_mps":list(getattr(self.pitch,"velocities",{}).get(recipient,(0,0))),
                "decision_model":"lane-aware-lead-pass-v1", "defender_reaction_ms":250} if self.modern_motion else {}),
            kick={"effort": effort, "passing_skill": skill, "aimed_end": aimed, "commanded_mean_speed_mps": speed},
            distance_m=round(distance(self.ball, resolved["end"]), 2), intended_distance_m=round(distance(self.ball, intended), 2),
            pressure={k: context[k] for k in ("under_pressure", "nearest_defender_m", "nearest_defender_id")},
            difficulty_context=context, pass_difficulty=pass_difficulty(self.ball, intended, direction,
                context["nearest_defender_m"], context["defenders_in_lane"]))
        if flagged:
            self.pitch.positions[recipient] = point(self.ball["x_m"], self.ball["y_m"])
            return self.whistle_offside(action, recipient, "touch")
        if resolved["outcome"] == "complete":
            self.previous_passer = self.owner
            self.owner = recipient
            self.pitch.positions[recipient] = point(self.ball["x_m"], self.ball["y_m"])
        else:
            self.emit("turnover", self.team, self.owner, self.possession_id, start=self.ball.copy(), reason=resolved["reason"])
            if crossing:
                return self.ball_out(crossing, self.team, self.owner, action["event_id"])
            recoverer = resolved["interceptor_id"] or min(self.pitch.positions, key=lambda p: distance(self.pitch.positions[p], self.ball))
            if resolved["interceptor_id"]:
                return self.opponent_contact(action, recoverer)
            if recoverer in frame["candidates"]:
                before_recovery = self.snapshot()
                travel = distance(self.pitch.positions[recoverer], self.ball)/4.5
                self.pitch.move(recoverer, self.ball, travel+.001)
                self.tick(math.ceil(travel*1000))
                self.record_reposition(before_recovery,"loose_ball_recovery")
                return self.whistle_offside(action, recoverer, "touch")
            self.recover(recoverer, "interception" if resolved["interceptor_id"] else "loose_pass")
        return True

    def clearance(self):
        direction = self.pitch.direction(self.team)
        # Clear away from the nearby attacker toward a touchline; the actual
        # segment decides whether it crosses a touchline or goal line first.
        end = raw_point(self.ball["x_m"] + direction*self.rng.uniform(12, 32),
                        -6 if self.ball["y_m"] < 34 else 74)
        aimed = end.copy()
        crossing = first_exit(self.ball, end)
        if crossing:
            end = crossing["location"]
        speed = 20
        actor, team = self.owner, self.team
        action = self.flight("clearance", end, speed, commanded_mean_speed_mps=speed,
                             aimed_end=aimed, reason="defensive_relief")
        self.emit("turnover", team, actor, self.possession_id, start=self.ball.copy(), reason="clearance")
        if crossing:
            return self.ball_out(crossing, team, actor, action["event_id"])
        self.recover(min(self.pitch.positions, key=lambda p: distance(self.pitch.positions[p], self.ball)), "clearance_loose_ball")
        return True

    def shoot(self, rebound=False, set_piece_type=None, restart_event_id=None):
        opponent, direction = other(self.team), self.pitch.direction(self.team)
        keeper = self.keeper(opponent)
        skill, effort = self.roster[self.owner]["shooting_skill"], round(self.rng.uniform(.2, 1), 4)
        aimed = raw_point(108 if direction == 1 else -3, 34 + self.rng.uniform(-1, 1)*(3+15*(1-skill)))
        if set_piece_type == "penalty":
            aimed = raw_point(108 if direction == 1 else -3, 34+self.rng.choice((-1, 1))*(2.1+self.rng.uniform(-.5, 1.2)*(1.1-skill)))
        speed = 20+12*effort+2*skill
        result = resolve_shot(self.ball, aimed, self.pitch.positions[keeper], speed)
        trajectory = make_trajectory(self.ball, result["end"], self.t, speed, decelerate=True)
        metrics = ball_speed(trajectory)
        frame = self.offside_frame()
        blocker = interference(frame, self.positions(), self.ball, keeper)
        shot = self.flight("shot", result["end"], speed,
            outcome="no_goal" if blocker else "goal" if result["outcome_reason"] == "goal" else "no_goal",
            outcome_reason="offside" if blocker else result["outcome_reason"],
            save_outcome=None if blocker else result["save_outcome"],
            valid_for_statistics=not bool(blocker), observed_outcome_reason=result["outcome_reason"],
            offside_offender_id=blocker, goalkeeper_id=keeper,
            set_piece_type=set_piece_type, restart_event_id=restart_event_id,
            is_rebound=rebound, rebound_of_shot_event_id=self.rebound_source if rebound else None,
            kick={"effort": effort, "shooting_skill": skill, "aimed_end": aimed, "commanded_mean_speed_mps": speed},
            shot_speed={"source": "synthetic_trajectory", "method": "initial_segment_average",
                        "mps": metrics["initial_segment_mps"], "kmh": metrics["initial_segment_kmh"],
                        "window_ms": metrics["initial_segment_duration_ms"]})
        # At source time the blocker interferes with the keeper; observation
        # is delivered at action completion. Never emit a goal/save afterwards.
        if blocker:
            return self.whistle_offside(shot, blocker, "interfere_opponent", location=shot["pitch_snapshot"]["players"][blocker])
        if result["outcome_reason"] == "goal":
            self.score[self.team] += 1
            goal = self.emit("goal", self.team, self.owner, self.possession_id, score=self.score.copy(), shot_event_id=shot["event_id"])
            if self.scenario == "match":
                self.progression.goal(self.team, self.period, self.t, goal["event_id"])
            return self.dead_ball({"type": "kickoff", "team_id": opponent, "location": point(52.5, 34)}, goal["event_id"], goal=True)
        if result["outcome_reason"] == "off_target":
            if set_piece_type == "penalty" and self.clock.announced is not None and self.t >= self.clock.end:
                return False
            crossing = first_exit(shot["start"], aimed)
            return self.ball_out(crossing, self.team, self.owner, shot["event_id"])
        # Save is credited once, from the shot. These explicit follow-up records
        # describe control/ball movement and do not award another save.
        self.pitch.positions[keeper] = point(self.ball["x_m"], self.ball["y_m"])
        self.emit("save", opponent, keeper, start=self.ball.copy(), shot_event_id=shot["event_id"], outcome=result["save_outcome"])
        if result["save_outcome"] == "hold":
            if set_piece_type == "penalty" and self.clock.announced is not None and self.t >= self.clock.end:
                return False
            self.team, self.owner = opponent, keeper
            self.possession()
            self.emit("recovery", opponent, keeper, self.possession_id, start=self.ball.copy(), reason="keeper_hold",
                      positions_after=self.positions())
            return True
        target = parry_target(shot["start"], self.ball, shot["pitch_snapshot"]["players"][keeper], direction, speed)
        crossing = first_exit(self.ball, target)
        self.team, self.owner = opponent, keeper
        self.possession_id = None  # a parry is a touch, not controlled possession
        parry = self.flight("parry", crossing["location"] if crossing else target, max(6, speed*.35),
                            shot_event_id=shot["event_id"], commanded_mean_speed_mps=max(6, speed*.35))
        if set_piece_type == "penalty" and self.clock.announced is not None and self.t >= self.clock.end:
            return False
        if crossing:
            return self.ball_out(crossing, opponent, keeper, parry["event_id"])
        self.emit("loose_ball", start=self.ball.copy(), reason="keeper_parry", shot_event_id=shot["event_id"])
        eligible = [p for p in self.pitch.positions if p != keeper]
        winner = min(eligible, key=lambda p: distance(self.pitch.positions[p], self.ball))
        if winner in contact_for(shot, self.roster)["candidates"]:
            before_recovery = self.snapshot()
            travel = distance(self.pitch.positions[winner], self.ball)/4.5
            self.pitch.move(winner, self.ball, travel+.001)
            self.tick(math.ceil(travel*1000))
            self.record_reposition(before_recovery,"loose_ball_recovery")
            return self.whistle_offside(shot, winner, "gain_advantage_save", via=parry["event_id"])
        self.recover(winner, "rebound")
        self.rebound_source = shot["event_id"]
        self.pending_rebound = self.team != opponent
        self.pending_clearance = self.team == opponent
        return True

    def run(self):
        slots = None
        for period in (1, 2):
            self.period, self.t, self.clock = period, 0, PeriodClock(self.duration)
            self.metadata["period_offsets_ms"][str(period)] = self.offset
            self.progression.period_offsets[period] = self.offset
            self.pitch = PitchState(period, slots)
            self.ball = point(52.5, 34)
            self.pending_rebound = self.pending_clearance = False
            start = self.emit("period_start", positions_after=self.positions())
            self.dead_ball({"type": "kickoff", "team_id": "home" if period == 1 else "away", "location": self.ball.copy()},
                           start["event_id"], initial=True)
            while self.clock.announced is None or self.t < self.clock.end:
                press, quiet, chaotic = self.behaviour()
                hold = (self.rng.uniform(.7, 1.6) if press or chaotic else self.rng.uniform(1.7, 3.4) if quiet else self.rng.uniform(1.2, 2.6)) if self.modern_motion else self.rng.uniform(2, 4) if chaotic else self.rng.uniform(3, 7)
                if self.pending_rebound:
                    hold = .4
                if self.clock.announced is not None and self.t + round(hold*1000) >= self.clock.end:
                    self.tick(self.clock.end-self.t)
                    break
                if self.modern_motion:
                    self.advance_play(round(hold*1000),press)
                else:
                    self.pitch.advance(hold, self.team, self.owner, self.ball, press=press, quiet=quiet)
                    self.tick(round(hold*1000))
                if self.clock.announced is not None and self.t >= self.clock.end:
                    break
                challenge = self.challenge()
                if challenge is not None:
                    if challenge is False:
                        break
                    continue
                progress = self.ball["x_m"] if self.pitch.direction(self.team) == 1 else 105-self.ball["x_m"]
                goal_distance = distance(self.ball,point(105 if self.pitch.direction(self.team) == 1 else 0,34))
                attacking = progress > (73 if self.modern_motion else 78) and abs(self.ball["y_m"]-34) < (19 if self.modern_motion else 22)
                if self.modern_motion:
                    attacking = attacking and goal_distance < 27
                shot_choice = (.45 if goal_distance < 12 else .28 if goal_distance < 20 else .16) if self.modern_motion else .2
                rebound, clearing = self.pending_rebound, self.pending_clearance
                self.pending_rebound = self.pending_clearance = False
                context = pass_context(self.ball, point(52.5, 34), self.pitch.team_positions(other(self.team)))
                if attacking and not quiet and (rebound or self.rng.random() < shot_choice):
                    keep_playing = self.shoot(rebound)
                elif clearing or (progress < 32 and self.roster[self.owner]["role"] != "GK"
                                  and context["nearest_defender_m"] < 6 and self.rng.random() < .28):
                    keep_playing = self.clearance()
                else:
                    keep_playing = self.pass_ball()
                if keep_playing is False:
                    break
            if self.pending_cards and not self.abandoned:
                stop = self.emit("stoppage", reason="referee_whistle", source_event_id=self.pending_cards[0]["event_id"], restart=None)
                self.flush_cards(stop["event_id"])
            self.emit("period_end", score=self.score.copy(), regulation_duration_ms=self.duration,
                      minimum_added_ms=self.clock.announced or 0, actual_added_ms=max(0, self.t-self.duration),
                      lost_time_ms=self.clock.lost_ms, lost_time_ledger=self.clock.losses.copy())
            self.metadata["period_actual_durations_ms"][str(period)] = self.t
            self.offset += self.t
            slots = self.pitch.slots.copy()
            if self.abandoned:
                break
        self.metadata["match_duration_ms"] = self.offset
        self.metadata["final_score"] = self.score.copy()
        self.metadata["match_status"] = "abandoned" if self.abandoned else "completed"
        if self.scenario == "match":
            self.metadata["simulation_model"]["progression"] = {
                "interval_min_ms": self.progression.minimum_interval_ms,
                "interval_max_ms": self.progression.maximum_interval_ms,
                "after_conceding_press_duration_ms": self.progression.response_duration_ms,
                "application": "next action decision; monotonic match clock includes added time; goal reactions take priority"}
            truth = self.progression.audit
        else:
            truth = [{"scenario": self.scenario, "periods": [1, 2], "window_start_ms": self.window[0],
                      "window_end_ms": self.window[1], "purpose": "Policy only; outcomes emerge from events"}]
        return self.metadata, self.events, truth
