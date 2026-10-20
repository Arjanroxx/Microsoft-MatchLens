"""Basic football simulation: shared state -> action -> resolution -> metrics."""
import math
import random

from simulator.metrics import ball_speed, make_trajectory, pass_difficulty
from simulator.pitch import PitchState, distance, pass_context, point, resolve_pass
from simulator.progression import MatchProgression


SCENARIOS = ("match", "balanced", "high-press", "quiet-possession", "chaotic")


def generate(seed=42, scenario="match", minutes_per_half=45):
    if scenario not in SCENARIOS or not 1 <= minutes_per_half <= 45:
        raise ValueError("Select a known scenario and 1..45 minutes per half")
    rng = random.Random(seed)
    match_id = f"synthetic-v1.3-{scenario}-{seed}-{minutes_per_half}"
    roles = ["GK", "DF", "DF", "DF", "DF", "MF", "MF", "MF", "FW", "FW", "FW"]
    players = [{"player_id": f"{team}-{i:02}", "team_id": team,
                "name": f"{label} Player {i:02}", "shirt_number": i, "role": role,
                "passing_skill": round(rng.uniform(0.65, 0.95), 3),
                "shooting_skill": round(rng.uniform(0.55, 0.9), 3)}
               for team, label in (("home", "Northbridge"), ("away", "Southbank"))
               for i, role in enumerate(roles, 1)]
    roster = {p["player_id"]: p for p in players}
    duration = minutes_per_half * 60_000
    progression = MatchProgression(seed, duration)
    start_window = min(600_000, duration // 3)
    end_window = min(start_window + 300_000, duration - 10_000)
    metadata = {"schema_version": "1.3", "match_id": match_id, "source": "synthetic", "seed": seed,
                "pitch": {"length_m": 105, "width_m": 68},
                "coordinate_origin": "bottom-left; fixed pitch coordinates", "period_duration_ms": duration,
                "home_attacks_positive_x": {"1": True, "2": False},
                "teams": [{"team_id": "home", "name": "Northbridge FC"},
                          {"team_id": "away", "name": "Southbank FC"}], "players": players,
                "event_time_semantics": "Passes/shots emitted at arrival; snapshot and first sample are kick time",
                "simulation_model": {"player_movement_cap_mps": 4.5, "ball_sample_interval_ms": 50,
                                     "pass_context": "measured from persistent kick-time pitch state",
                                     "pass_outcome": "defender reach/interception or receiver reach",
                                     "pass_mean_speed_mps": "min(24, 8 + .28*intended_distance + 3*kick_effort)",
                                     "shot_mean_speed_mps": "20 + 12*kick_effort + 2*shooting_skill",
                                     "shot_outcome": "goal-mouth test and goalkeeper reach",
                                     "scenario_policy": "changes tactics and action selection, not metric values"},
                "limitations": ["Simplified 2D continuous-play model, no fouls/offside/stoppage time",
                                "Non-goal shots become recoveries; goal kicks/corners and rebounds are not modelled",
                                "Players move between kicks; held fixed during ball flight except receiver/interceptor",
                                "Snapshots are not a continuous player tracking feed",
                                "Skills and action choices use seeded randomness; metrics are deterministic from evidence",
                                "Difficulty and motion models are uncalibrated; no real identities or professional realism claim"]}
    events, truth, score, possession_counter = [], [], {"home": 0, "away": 0}, 0

    def emit(period, t, kind, team=None, player=None, possession=None, **fields):
        event = {"schema_version": "1.3", "match_id": match_id,
                 "event_id": f"evt-{len(events) + 1:06}", "sequence": len(events) + 1,
                 "period": period, "period_time_ms": t, "type": kind, "source": "synthetic",
                 "team_id": team, "player_id": player, "possession_id": possession, **fields}
        events.append(event)
        return event

    def behaviour(period, time_ms, possessing_team):
        other = "away" if possessing_team == "home" else "home"
        if scenario == "match":
            states = progression.states(period, time_ms)
            return (states[other] == "higher-press", states[possessing_team] == "patient",
                    states[possessing_team] == "quick-play")
        active = start_window <= time_ms < end_window
        return (scenario == "high-press" and active and other == "home",
                scenario == "quiet-possession" and active, scenario == "chaotic" and active)

    for period in (1, 2):
        pitch = PitchState(period)
        t, team, ball, restart, recoverer = 0, "home" if period == 1 else "away", point(52.5, 34), True, None
        continuing = False
        emit(period, 0, "period_start")
        if scenario == "match":
            progression.states(period, 0)
        while t < duration - 15_000:
            opponent = "away" if team == "home" else "home"
            if not continuing:
                possession_counter += 1
                possession = f"pos-{possession_counter:05}"
                if restart:
                    # Legal simulation reset at kickoff; other changes use bounded movement.
                    pitch = PitchState(period)
                    owner = f"{team}-07"
                    pitch.positions[owner] = ball.copy()
                else:
                    owner = recoverer or pitch.nearest(team, ball)
                    seconds = distance(pitch.positions[owner], ball) / pitch.RUN_SPEED_MPS
                    if t + math.ceil(seconds * 1000) >= duration - 15_000:
                        break
                    pitch.move(owner, ball, seconds + 0.001)
                    t += math.ceil(seconds * 1000)
                emit(period, t, "restart" if restart else "recovery", team, owner, possession,
                     start=ball.copy(), reason="kickoff" if restart else "opponent_turnover")
            restart, recoverer = False, None
            press, quiet, chaotic = behaviour(period, t, team)
            chain = rng.randint(8, 12) if quiet else rng.randint(1, 3) if chaotic else rng.randint(3, 8)
            progress = ball["x_m"] if pitch.direction(team) == 1 else 105 - ball["x_m"]
            shooting_area = progress > 80 and abs(ball["y_m"] - 34) < 18
            choose_shot = not quiet and shooting_area and rng.random() < .15
            if choose_shot:
                chain = 0
            ended = False
            for index in range(chain):
                press, quiet, chaotic = behaviour(period, t, team)
                hold_s = rng.uniform(2, 4) if chaotic else rng.uniform(3, 7)
                pitch.advance(hold_s, team, owner, ball, press=press, quiet=quiet)
                t += round(hold_s * 1000)
                if t >= duration - 15_000:
                    break
                direction = pitch.direction(team)
                candidates = [(pid, pos) for pid, pos in pitch.team_positions(team).items()
                              if pid != owner and 2 < distance(ball, pos) < 55]
                if not candidates:
                    break
                # Choose among actual teammates, favouring progression or safe retention.
                weights = []
                defenders = pitch.team_positions(opponent)
                for pid, target in candidates:
                    progress = direction * (target["x_m"] - ball["x_m"])
                    openness = min(distance(target, p) for p in defenders.values())
                    weights.append(max(0.1, (2 + openness / 5) / (1 + distance(ball, target) / 30)
                                       * (0.4 if quiet and progress > 8 else 1 + max(progress, 0) / 12)))
                recipient, intended = rng.choices(candidates, weights=weights, k=1)[0]
                context = pass_context(ball, intended, defenders)
                if context["under_pressure"]:
                    emit(period, t, "pressure", opponent, context["nearest_defender_id"], possession,
                         start=pitch.positions[context["nearest_defender_id"]].copy(), target_player_id=owner)
                skill = roster[owner]["passing_skill"]
                effort = round(rng.uniform(0.2, 1), 4)
                error_scale = (1 - skill) * (1 + distance(ball, intended) / 12) * (2 if context["under_pressure"] else 1)
                aimed = point(intended["x_m"] + rng.uniform(-1, 1) * error_scale,
                              intended["y_m"] + rng.uniform(-1, 1) * error_scale)
                speed_target = min(24, 8 + .28 * distance(ball, intended) + 3 * effort)
                resolved = resolve_pass(ball, aimed, intended, defenders, speed_target)
                trajectory = make_trajectory(ball, resolved["end"], t, speed_target)
                end_time = trajectory[-1]["period_time_ms"]
                if end_time >= duration - 10_000:
                    break
                snapshot = {"period_time_ms": t, "players": {pid: p.copy() for pid, p in pitch.positions.items()}}
                flight_s = (end_time - t) / 1000
                t = end_time
                complete = resolved["outcome"] == "complete"
                action = emit(period, t, "pass", team, owner, possession,
                              recipient_id=recipient if complete else None, intended_recipient_id=recipient,
                              start=ball.copy(), end=resolved["end"].copy(), intended_end=intended.copy(),
                              outcome=resolved["outcome"], outcome_reason=resolved["reason"],
                              interceptor_id=resolved["interceptor_id"], pitch_snapshot=snapshot,
                              kick={"effort": effort, "passing_skill": skill, "aimed_end": aimed,
                                    "commanded_mean_speed_mps": speed_target},
                              distance_m=round(distance(ball, resolved["end"]), 2),
                              intended_distance_m=round(distance(ball, intended), 2),
                              pressure={k: context[k] for k in ("under_pressure", "nearest_defender_m", "nearest_defender_id")},
                              difficulty_context=context,
                              pass_difficulty=pass_difficulty(ball, intended, direction, context["nearest_defender_m"], context["defenders_in_lane"]),
                              ball_trajectory=trajectory, ball_speed=ball_speed(trajectory))
                ball = action["end"].copy()
                if complete:
                    pitch.move(recipient, ball, flight_s + 0.001)
                    owner = recipient
                    progress = ball["x_m"] if direction == 1 else 105 - ball["x_m"]
                    if not quiet and progress > 80 and abs(ball["y_m"] - 34) < 18 and rng.random() < .12:
                        choose_shot = True
                        break
                else:
                    recoverer = resolved["interceptor_id"]
                    if recoverer:
                        pitch.move(recoverer, ball, flight_s + 0.001)
                    emit(period, t, "turnover", team, owner, possession, start=ball.copy())
                    ended = True
                    break
            if t >= duration - 15_000:
                break
            progress = ball["x_m"] if pitch.direction(team) == 1 else 105 - ball["x_m"]
            shoot = (not ended and progress > 80 and abs(ball["y_m"] - 34) < 18
                     and not quiet and (choose_shot or rng.random() < .08))
            if shoot:
                t += 1000
                skill, effort = roster[owner]["shooting_skill"], round(rng.uniform(0.2, 1), 4)
                goal_x = 105 if pitch.direction(team) == 1 else 0
                shot_end = point(goal_x, 34 + rng.uniform(-1, 1) * (3 + 15 * (1 - skill)))
                speed_target = 20 + 12 * effort + 2 * skill
                trajectory = make_trajectory(ball, shot_end, t, speed_target, decelerate=True)
                end_time = trajectory[-1]["period_time_ms"]
                if end_time >= duration:
                    break
                flight_s = (end_time - t) / 1000
                keeper = f"{opponent}-01"
                on_target = abs(shot_end["y_m"] - 34) <= 3.66
                saved = on_target and distance(pitch.positions[keeper], shot_end) <= 4.5 * flight_s
                goal = on_target and not saved
                speed = ball_speed(trajectory)
                shot = emit(period, end_time, "shot", team, owner, possession, start=ball.copy(), end=shot_end,
                            outcome="goal" if goal else "no_goal", outcome_reason="goal" if goal else "saved" if saved else "off_target",
                            pitch_snapshot={"period_time_ms": t, "players": {pid: p.copy() for pid, p in pitch.positions.items()}},
                            kick={"effort": effort, "shooting_skill": skill, "commanded_mean_speed_mps": speed_target},
                            ball_trajectory=trajectory, ball_speed=speed,
                            shot_speed={"source": "synthetic_trajectory", "method": "initial_segment_average",
                                        "mps": speed["initial_segment_mps"], "kmh": speed["initial_segment_kmh"],
                                        "window_ms": speed["initial_segment_duration_ms"]})
                t, ball = end_time, shot_end
                if saved:
                    pitch.move(keeper, ball, flight_s + .001)
                    recoverer = keeper
                if goal:
                    score[team] += 1
                    goal_event = emit(period, t, "goal", team, owner, possession, score=score.copy(), shot_event_id=shot["event_id"])
                    if scenario == "match":
                        progression.goal(team, period, t, goal_event["event_id"])
                    ball, restart = point(52.5, 34), True
            if not ended and not restart and not shoot:
                # A planning batch ending is not a football turnover: retain the ball.
                continuing = True
                continue
            continuing = False
            if not ended and not restart:
                emit(period, t, "turnover", team, owner, possession, start=ball.copy(), reason=shot["outcome_reason"])
            team = opponent
            t += 1000
        emit(period, duration, "period_end", score=score.copy())
    metadata["final_score"] = score
    if scenario == "match":
        metadata["simulation_model"]["progression"] = {
            "interval_min_ms": progression.minimum_interval_ms,
            "interval_max_ms": progression.maximum_interval_ms,
            "after_conceding_press_duration_ms": progression.response_duration_ms,
            "application": "next action decision; goal reactions take priority over scheduled changes",
        }
        truth.extend(progression.audit)
    else:
        truth.append({"scenario": scenario, "periods": [1, 2], "window_start_ms": start_window,
                      "window_end_ms": end_window, "purpose": "Policy window only; patterns must be measured from events, not guaranteed"})
    return metadata, events, truth
