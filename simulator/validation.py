"""Schema 1.5 validation, including geometry, lifecycle, clocks and restarts."""
import math

from simulator.clock import elapsed
from simulator.metrics import ball_speed, make_trajectory, pass_difficulty
from simulator.pitch import distance, pass_context, resolve_pass
from simulator.restarts import award_restart, first_exit, resolve_shot, parry_target

ACTIONS = {"pass", "shot", "clearance", "parry", "restart_delivery"}


def validate_stream(metadata, events):
    roster = {p["player_id"]: p for p in metadata["players"]}
    active = {p: r["formation_slot"] for p, r in roster.items() if r["is_starter"]}
    ever = set(active)
    seen, by_id, score = set(), {}, {"home": 0, "away": 0}
    used = {t: 0 for t in score}
    windows = {t: set() for t in score}
    previous, ball, stopped, pending, last_touch = -1, None, False, None, None
    starts, ends, announcements = {}, {}, {}
    for index, e in enumerate(events, 1):
        def require(test, message):
            if not test:
                raise ValueError(f"Event {index}: {message}")
        kind, team, actor = e["type"], e.get("team_id"), e.get("player_id")
        period, t = e["period"], e["period_time_ms"]
        require(e["schema_version"] == "1.5" and e["match_id"] == metadata["match_id"], "wrong schema/match")
        require(e["sequence"] == index and e["event_id"] not in seen, "duplicate identity/sequence gap")
        seen.add(e["event_id"])
        require(period in (1, 2) and type(t) is int and 0 <= t <= metadata["period_actual_durations_ms"][str(period)], "invalid period clock")
        require(e["match_time_ms"] == elapsed(metadata, period, t) and e["match_time_ms"] >= previous, "invalid monotonic replay clock")
        previous = e["match_time_ms"]
        require(team in (None, "home", "away"), "invalid team")
        if actor:
            require(actor in active and roster[actor]["team_id"] == team, "inactive/wrong-team actor")
        for key in ("start", "end"):
            if key in e:
                require(all(math.isfinite(e[key][axis]) for axis in ("x_m", "y_m")), "nonfinite coordinate")
        if kind == "period_start":
            require(t == 0 and period not in starts, "invalid period start")
            if period == 2:
                require(1 in ends and ends[1] == e["match_time_ms"], "period overlap/gap")
            starts[period], ball, pending = e["match_time_ms"], None, None
        if kind == "stoppage":
            require(e["reason"] in ("ball_out", "goal_celebration", "period_interval"), "synthetic substitution break returned")
            stopped = True
        if kind == "ball_placement":
            require(stopped, "placement during open play")
            require(ball is None or e["start"] == ball, "placement starts away from ball")
            stop = by_id.get(e["stoppage_event_id"], {})
            require(stop.get("type") == "stoppage" and e["end"] == stop["restart"]["location"], "incorrect restart placement")
            ball = e["end"]
        if kind == "substitution":
            off, on = e["player_off_id"], e["player_on_id"]
            require(stopped and off in active and on in roster and on not in ever, "invalid substitution lifecycle")
            require(roster[off]["team_id"] == roster[on]["team_id"] == team, "wrong substitution team")
            require(roster[off]["role"] != "GK" and roster[off]["position_group"] == roster[on]["position_group"], "invalid substitute position")
            require(e["formation_slot"] == active[off], "formation slot changed")
            require(not e["halftime"] or (period == 2 and t == 0), "invalid halftime substitution")
            stop = by_id.get(e["stoppage_event_id"], {})
            require(stop.get("type") == "stoppage" and stop.get("reason") in ("ball_out", "goal_celebration", "period_interval"), "missing natural opportunity")
            active[on] = active.pop(off)
            ever.add(on)
            used[team] += 1
            if not e["halftime"]:
                windows[team].add(e["window_id"])
            require(used[team] <= 5 and len(windows[team]) <= 3, "substitution limits exceeded")
        if "positions_after" in e:
            require(set(e["positions_after"]) == set(active), "incorrect active positions")
        if kind == "restart":
            require(stopped and e["start"] == ball, "restart without placement/stoppage")
            require(e["reason"] in ("throw_in", "corner_kick", "goal_kick", "kickoff"), "unknown restart")
            if pending:
                require(team == pending["team_id"] and e["reason"] == pending["type"] and e["start"] == pending["location"], "restart disagrees with award")
            pending = None
            stop = by_id.get(e["stoppage_event_id"], {})
            require(stop.get("restart", {}).get("team_id") == team and stop["restart"]["type"] == e["reason"], "restart not supported by stoppage")
            if e.get("ball_in_play"):
                stopped = False
            last_touch = (team, actor)
        if kind == "resume":
            require(stopped, "resume without dead ball")
            stopped = False
        if kind == "recovery":
            require(not stopped and e["start"] == ball, "recovery teleported ball / occurred out of play")
        if kind in ACTIONS:
            require(not stopped and e["start"] == ball, "open-play ball discontinuity")
            snapshot, samples = e["pitch_snapshot"], e["ball_trajectory"]
            require(set(snapshot["players"]) == set(active), "inactive player snapshot")
            # A ball centre can extend just outside a line while part of the
            # ball remains in play; the on-field actor may contact its edge.
            edge = not (0 <= e["start"]["x_m"] <= 105 and 0 <= e["start"]["y_m"] <= 68)
            require(distance(snapshot["players"][actor], e["start"]) <= (.111 if edge else .001), "actor is not at the ball")
            require(snapshot["period_time_ms"] == samples[0]["period_time_ms"] and samples[-1]["period_time_ms"] == t, "trajectory clock mismatch")
            for intervening in reversed(events[:index-1]):
                if intervening["period"] != period or intervening["period_time_ms"] <= snapshot["period_time_ms"]:
                    break
                require(intervening["type"] == "added_time", "flight overlaps a football action")
            for p in snapshot["players"].values():
                require(0 <= p["x_m"] <= 105 and 0 <= p["y_m"] <= 68, "player outside pitch")
            require(all(-.110001 <= p["x_m"] <= 105.110001 and -.110001 <= p["y_m"] <= 68.110001 for p in samples), "ball continued beyond first crossing")
            speed = e.get("kick", {}).get("commanded_mean_speed_mps", e.get("commanded_mean_speed_mps"))
            require(samples == make_trajectory(e["start"], e["end"], snapshot["period_time_ms"], speed, kind == "shot"), "trajectory not supported by command")
            require(e["ball_speed"] == ball_speed(samples), "incorrect ball speed")
            if kind == "pass":
                target = e["intended_recipient_id"]
                require(target in active and roster[target]["team_id"] == team and target != actor, "invalid recipient")
                require(e["intended_end"] == snapshot["players"][target], "target does not match snapshot")
                defenders = {p: v for p, v in snapshot["players"].items() if roster[p]["team_id"] != team}
                context = pass_context(e["start"], e["intended_end"], defenders)
                require(context == e["difficulty_context"], "incorrect pass context")
                require(e["pressure"] == {k: context[k] for k in ("under_pressure", "nearest_defender_m", "nearest_defender_id")}, "incorrect pressure")
                direction = 1 if (team == "home") == (period == 1) else -1
                require(e["pass_difficulty"] == pass_difficulty(e["start"], e["intended_end"], direction, context["nearest_defender_m"], context["defenders_in_lane"]), "incorrect difficulty")
                require(abs(speed - min(24, 8 + .28*distance(e["start"], e["intended_end"]) + 3*e["kick"]["effort"])) < 1e-9, "incorrect pass command")
                result = resolve_pass(e["start"], e["kick"]["aimed_end"], e["intended_end"], defenders, speed, stop_at_boundary=True)
                crossing = first_exit(e["start"], e["kick"]["aimed_end"]) if result["reason"] == "out_of_play" else None
                if crossing:
                    result.update(end=crossing["location"], outcome="incomplete", reason="out_of_play", interceptor_id=None)
                require(e["end"] == result["end"] and e["outcome"] == result["outcome"] and e["outcome_reason"] == result["reason"] and e["interceptor_id"] == result["interceptor_id"], "invalid pass resolution")
                require(e["recipient_id"] == (target if result["outcome"] == "complete" else None), "wrong completed recipient")
                require(e["distance_m"] == round(distance(e["start"], e["end"]), 2), "incorrect pass distance")
            if kind == "shot":
                require(abs(speed-(20+12*e["kick"]["effort"]+2*e["kick"]["shooting_skill"])) < 1e-9, "incorrect shot command")
                keeper = e["goalkeeper_id"]
                require(keeper in active and roster[keeper]["team_id"] != team and roster[keeper]["role"] == "GK", "invalid keeper")
                result = resolve_shot(e["start"], e["kick"]["aimed_end"], snapshot["players"][keeper], speed)
                require(e["end"] == result["end"] and e["outcome_reason"] == result["outcome_reason"] and e["save_outcome"] == result["save_outcome"], "shot not supported by contact geometry")
                require(e["outcome"] == ("goal" if result["outcome_reason"] == "goal" else "no_goal"), "invalid shot outcome")
                metrics = e["ball_speed"]
                require(e["shot_speed"] == {"source": "synthetic_trajectory", "method": "initial_segment_average", "mps": metrics["initial_segment_mps"], "kmh": metrics["initial_segment_kmh"], "window_ms": metrics["initial_segment_duration_ms"]}, "incorrect shot speed")
                if e.get("is_rebound"):
                    prior = by_id.get(e.get("rebound_of_shot_event_id"), {})
                    require(prior.get("save_outcome") == "parry", "rebound without parried shot")
            if kind == "clearance":
                crossing = first_exit(e["start"], e["aimed_end"])
                require(e["end"] == (crossing["location"] if crossing else e["aimed_end"]), "invalid clearance boundary")
            if kind == "parry":
                prior = by_id.get(e["shot_event_id"], {})
                require(prior.get("save_outcome") == "parry" and actor == prior.get("goalkeeper_id"), "parry without keeper save")
                require(e["start"] == prior["end"], "parry did not start at save contact")
                command = prior["kick"]["commanded_mean_speed_mps"]
                direction = 1 if (prior["team_id"] == "home") == (period == 1) else -1
                target = parry_target(prior["start"], prior["end"], prior["pitch_snapshot"]["players"][actor], direction, command)
                crossing = first_exit(e["start"], target)
                require(e["end"] == (crossing["location"] if crossing else target) and speed == max(6, command*.35), "parry not supported by shot contact")
            if kind == "restart_delivery":
                restart = by_id.get(e["restart_event_id"], {})
                require(restart.get("type") == "restart" and restart.get("reason") == e["restart_type"] and restart.get("player_id") == actor, "delivery without restart")
                target = e["intended_recipient_id"]
                require(target in active and roster[target]["team_id"] == team and target != actor, "invalid restart recipient")
                require(e["intended_end"] == snapshot["players"][target], "restart target disagrees with snapshot")
                defenders = {p: v for p, v in snapshot["players"].items() if roster[p]["team_id"] != team}
                result = resolve_pass(e["start"], e["intended_end"], e["intended_end"], defenders, speed, stop_at_boundary=True)
                require(e["end"] == result["end"] and e["outcome"] == result["outcome"] and e["interceptor_id"] == result["interceptor_id"], "restart delivery disagrees with geometry")
                require(e["recipient_id"] == (target if result["outcome"] == "complete" else None), "incorrect restart receiver")
            ball, last_touch = e["end"], (team, actor)
            if kind == "pass" and e.get("interceptor_id"):
                last_touch = (roster[e["interceptor_id"]]["team_id"], e["interceptor_id"])
        if kind == "ball_out":
            source = by_id.get(e["source_event_id"], {})
            require(source.get("type") in ACTIONS and source.get("end") == e["crossing"] == ball, "ball-out without crossing action")
            # Endpoint lies at the whole-ball boundary; source ray must cross it.
            aimed = source.get("kick", {}).get("aimed_end", source.get("aimed_end"))
            if not aimed:
                aimed = {"x_m": ball["x_m"]+(ball["x_m"]-source["start"]["x_m"]), "y_m": ball["y_m"]+(ball["y_m"]-source["start"]["y_m"])}
            crossing = first_exit(source["start"], aimed)
            require(crossing is not None and crossing["location"] == ball and crossing["boundary"] == e["boundary"], "wrong boundary crossing")
            require(last_touch == (e["last_touch_team_id"], e["last_touch_player_id"]), "incorrect last touch")
            award = award_restart(crossing, *last_touch, period)
            require(e["restart"] == award, "incorrect restart award")
            pending, stopped = award, True
        if kind == "goal":
            prior = events[index-2] if index > 1 else {}
            require(prior.get("type") == "shot" and prior.get("outcome") == "goal" and prior.get("event_id") == e["shot_event_id"], "goal without scoring shot")
            score[team] += 1
            require(e["score"] == score, "incorrect score")
        if kind == "save":
            prior = by_id.get(e["shot_event_id"], {})
            require(prior.get("outcome_reason") == "saved" and actor == prior.get("goalkeeper_id") and e["outcome"] == prior.get("save_outcome"), "invalid save attribution")
        if kind == "added_time":
            require(t == metadata["period_duration_ms"] and period not in announcements, "invalid added-time announcement")
            require(e["minimum_added_ms"] >= e["lost_time_ms"], "added time below recorded losses")
            announcements[period] = e
        if kind == "time_lost":
            require(0 <= e["start_ms"] < e["end_ms"] <= t and e["duration_ms"] == e["end_ms"]-e["start_ms"], "invalid lost-time interval")
            require(e["source_event_id"] in by_id, "missing time-loss source")
        if kind == "period_end":
            require(period in announcements, "half ended before added time announced")
            require(t >= metadata["period_duration_ms"] + announcements[period]["minimum_added_ms"], "half ended too early")
            ledger = e["lost_time_ledger"]
            logged = [x for x in events[:index] if x["period"] == period and x["type"] == "time_lost"]
            require(sum(r["duration_ms"] for r in ledger) == e["lost_time_ms"] == sum(x["duration_ms"] for x in logged), "lost-time ledger mismatch")
            require(e["actual_added_ms"] == t-metadata["period_duration_ms"], "incorrect actual added time")
            ends[period], stopped = e["match_time_ms"], True
        by_id[e["event_id"]] = e
    if score != metadata["final_score"] or set(starts) != {1, 2} or set(ends) != {1, 2}:
        raise ValueError("Incomplete match/final score mismatch")
    if ends[2] != metadata["match_duration_ms"]:
        raise ValueError("Incorrect match duration")
