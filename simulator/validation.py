"""Schema 1.5 validation, including geometry, lifecycle, clocks and restarts."""
import math

from simulator.clock import elapsed
from simulator.metrics import ball_speed, make_trajectory, pass_difficulty
from simulator.pitch import distance, pass_context, resolve_pass
from simulator.restarts import award_restart, first_exit, resolve_shot, parry_target
from simulator.discipline import resolve_challenge, foul_restart
from simulator.offside import contact_for, interference, touch_control, deflection_target

ACTIONS = {"pass", "shot", "clearance", "parry", "restart_delivery", "carry", "deflection"}


def validate_stream(metadata, events):
    roster = {p["player_id"]: p for p in metadata["players"]}
    active = {p: r["formation_slot"] for p, r in roster.items() if r["is_starter"]}
    ever = set(active)
    seen, by_id, score = set(), {}, {"home": 0, "away": 0}
    used = {t: 0 for t in score}
    windows = {t: set() for t in score}
    previous, ball, stopped, pending, last_touch = -1, None, False, None, None
    starts, ends, announcements = {}, {}, {}
    cautions, red_cards = {}, set()
    card_fouls, dismissed, abandoned = set(), set(), False
    foul_tackles, advantages = set(), {}
    phase_source, offside_sources, offside_stops = None, set(), set()
    for index, e in enumerate(events, 1):
        def require(test, message):
            if not test:
                raise ValueError(f"Event {index}: {message}")
        kind, team, actor = e["type"], e.get("team_id"), e.get("player_id")
        period, t = e["period"], e["period_time_ms"]
        require(e["schema_version"] == metadata["schema_version"] and e["match_id"] == metadata["match_id"], "wrong schema/match")
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
            require(e["reason"] in ("ball_out", "goal_celebration", "period_interval", "foul", "referee_whistle", "offside"), "unknown stoppage")
            if e["reason"] == "offside":
                offence = by_id.get(e["source_event_id"], {})
                require(offence.get("type") == "offside" and e["restart"] == offence["restart"], "offside stoppage without offence")
                offside_stops.add(offence["event_id"])
                pending = offence["restart"]
            if e["reason"] == "foul":
                foul = by_id.get(e["source_event_id"], {})
                require(foul.get("type") == "foul" and e["restart"] == foul["restart"], "foul stoppage without offence")
                require(advantages.get(foul["event_id"]) != "played", "foul recalled after advantage already realised")
                pending = foul["restart"]
            stopped = True
            phase_source = None
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
            require(active[off] != 1 and roster[off]["position_group"] == roster[on]["position_group"], "invalid substitute position")
            require(e["formation_slot"] == active[off], "formation slot changed")
            require(not e["halftime"] or (period == 2 and t == 0), "invalid halftime substitution")
            stop = by_id.get(e["stoppage_event_id"], {})
            require(stop.get("type") == "stoppage" and stop.get("reason") in ("ball_out", "goal_celebration", "period_interval", "foul", "offside"), "missing natural opportunity")
            active[on] = active.pop(off)
            ever.add(on)
            used[team] += 1
            if not e["halftime"]:
                windows[team].add(e["window_id"])
            require(used[team] <= 5 and len(windows[team]) <= 3, "substitution limits exceeded")
        if kind == "tackle":
            require(not stopped and e["victim_id"] in active and roster[e["victim_id"]]["team_id"] != team, "invalid tackle actors")
            require(e["location"] == ball and set(e["challenge_snapshot"]["players"]) == set(active), "disconnected challenge")
            result = resolve_challenge(ball, e["challenge_snapshot"]["players"][actor], **e["controls"])
            require(e["decision"] == result and e["outcome"] == result["outcome"], "challenge not supported by evidence")
        if kind == "foul":
            tackle = by_id.get(e["tackle_event_id"], {})
            require(tackle.get("type") == "tackle" and tackle.get("outcome") == "foul" and tackle.get("player_id") == actor and tackle.get("victim_id") == e["victim_id"], "foul without attributable challenge")
            require(e["location"] == tackle["location"] and e["decision"] == tackle["decision"], "foul evidence changed")
            require(e["tackle_event_id"] not in foul_tackles, "duplicate foul for one challenge")
            foul_tackles.add(e["tackle_event_id"])
            require(e["restart"] == foul_restart(e["location"], team, period, e["decision"]["offence"]), "incorrect foul restart")
        if kind == "advantage":
            foul = by_id.get(e["foul_event_id"], {})
            require(foul.get("type") == "foul" and foul.get("victim_id") == actor and foul["restart"]["type"] == "direct_free_kick", "invalid advantage offence")
            require(foul["decision"]["card"] != "red" and e["outcome"] in ("pending", "played", "recalled"), "invalid advantage decision")
            require((e["outcome"] == "pending" and e["foul_event_id"] not in advantages) or
                    (e["outcome"] != "pending" and advantages.get(e["foul_event_id"]) == "pending"), "advantage phase repeated or missing")
            advantages[e["foul_event_id"]] = e["outcome"]
            if e["outcome"] == "played":
                carry = by_id.get(e["continuation_event_id"], {})
                require(carry.get("type") == "carry" and carry.get("foul_event_id") == foul["event_id"], "advantage without continuation")
        if kind == "card":
            foul = by_id.get(e["foul_event_id"], {})
            require(stopped and foul.get("player_id") == actor and foul["decision"]["card"] == e["card"], "card without matching offence/stoppage")
            require(by_id.get(e["stoppage_event_id"], {}).get("type") == "stoppage", "card without stoppage reference")
            require(e["foul_event_id"] not in card_fouls, "duplicate sanction")
            card_fouls.add(e["foul_event_id"])
            if e["card"] == "yellow":
                cautions[actor] = cautions.get(actor, 0)+1
                require(cautions[actor] <= 2 and e["caution_number"] == cautions[actor], "invalid caution number")
            elif e["card"] == "red":
                red_cards.add(actor)
            else:
                require(False, "unknown card colour")
        if kind == "dismissal":
            require(stopped and actor in active and actor not in dismissed, "invalid dismissal")
            require((e["reason"] == "second_yellow" and cautions.get(actor) == 2) or (e["reason"] == "direct_red" and actor in red_cards), "dismissal without sanction")
            active.pop(actor)
            dismissed.add(actor)
        if kind == "goalkeeper_change":
            require(stopped and e["previous_goalkeeper_id"] in dismissed and actor in active, "invalid keeper reassignment")
            require(not any(s == 1 and roster[p]["team_id"] == team for p, s in active.items()), "duplicate active keeper")
            active[actor] = 1
        if kind == "match_abandoned":
            require(sum(roster[p]["team_id"] == e["affected_team_id"] for p in active) < 7, "abandonment without team-size cause")
            abandoned = True
        if "positions_after" in e:
            require(set(e["positions_after"]) == set(active), "incorrect active positions")
        if kind == "restart":
            require(stopped and e["start"] == ball, "restart without placement/stoppage")
            require(e["reason"] in ("throw_in", "corner_kick", "goal_kick", "kickoff", "direct_free_kick", "indirect_free_kick", "penalty"), "unknown restart")
            require(not abandoned and all(sum(roster[p]["team_id"] == side for p in active) >= 7 for side in ("home", "away")), "restart with too few players")
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
            if phase_source and metadata["schema_version"] in ("1.7", "1.8"):
                require(actor not in contact_for(phase_source, roster)["candidates"], "offside attacker granted control")
            phase_source = None
        if kind == "opponent_touch":
            source = by_id.get(e["source_event_id"], {})
            defender = source.get("interceptor_id") or source.get("deflector_id")
            require(source.get("type") in ("pass", "restart_delivery") and actor == defender and e["start"] == ball, "unattributed opponent touch")
            require(phase_source is not None and phase_source["event_id"] == source["event_id"] and e["match_time_ms"] == source["match_time_ms"], "stale opponent touch")
            speed = source.get("kick", {}).get("commanded_mean_speed_mps", source.get("commanded_mean_speed_mps"))
            expected = touch_control(source["start"], source["end"], source["pitch_snapshot"]["players"][actor], speed)
            require(e["control"] == expected, "unsupported deliberate-play classification")
            require(bool(source.get("deflector_id")) == (not expected["resets_offside"]), "incorrect interception credit")
            phase_source = None if expected["resets_offside"] else source
        if kind == "offside":
            source = by_id.get(e["source_event_id"], {})
            require(not stopped and source.get("type") in ("pass", "shot", "restart_delivery", "clearance"), "offside without live teammate contact")
            require(source["event_id"] not in offside_sources and source["period"] == period, "duplicate/stale offside")
            frame = contact_for(source, roster)
            require(e["contact"] == frame and actor in frame["candidates"] and team == source["team_id"], "offside position not supported by original snapshot")
            require(e["contact_period_time_ms"] == source["pitch_snapshot"]["period_time_ms"], "wrong offside contact clock")
            require(phase_source is not None and phase_source["event_id"] == source["event_id"], "offside after phase reset")
            involvement = e["involvement"]
            if involvement == "touch":
                require(source["type"] in ("pass", "restart_delivery") and distance(e["location"], ball) < .001, "touch without ball involvement")
                require(source["outcome"] == "incomplete" and source["recipient_id"] is None, "offside receipt retains success credit")
                require(distance(e["location"], source["end"]) < .112, "offside location disconnected")
                require(actor == source["intended_recipient_id"] if source["outcome_reason"] == "offside" else
                        actor == min(source.get("positions_after",source["pitch_snapshot"]["players"]), key=lambda p: distance(source.get("positions_after",source["pitch_snapshot"]["players"])[p], source["end"])), "offside player did not receive/reach ball")
            elif involvement == "interfere_opponent":
                require(source["type"] == "shot" and source.get("valid_for_statistics") is False, "invalid attack retains shot credit")
                blocker = interference(frame, source["pitch_snapshot"]["players"], source["start"], source["goalkeeper_id"])
                require(blocker == actor and e["location"] == source["pitch_snapshot"]["players"][actor], "unsupported active interference")
            elif involvement in ("gain_advantage_save", "gain_advantage_deflection"):
                via = by_id.get(e["via_event_id"], {})
                require(via.get("type") == ("parry" if involvement.endswith("save") else "deflection") and via.get("shot_event_id", via.get("source_event_id")) == source["event_id"], "rebound offside lost original phase")
                require(distance(e["location"], ball) < .001, "rebound offence away from ball")
            else:
                require(False, "unsupported offside involvement")
            require(e["restart"] == {"type": "indirect_free_kick", "team_id": "away" if team == "home" else "home", "location": e["location"], "reason": "offside"}, "incorrect offside restart")
            offside_sources.add(source["event_id"])
        if kind in ("movement","reposition") or e.get("player_motion"):
            motion = e["player_motion"]
            require(len(motion) >= 2 and motion[0]["period_time_ms"] == e["pitch_snapshot"]["period_time_ms"] and motion[-1]["period_time_ms"] == t, "invalid movement clock")
            require(motion[0]["players"] == e["pitch_snapshot"]["players"] and motion[-1]["players"] == e["positions_after"], "movement anchors disagree")
            for a, b in zip(motion,motion[1:]):
                require(a["period_time_ms"] < b["period_time_ms"] and set(a["players"]) == set(b["players"]) == set(active), "movement roster/clock mismatch")
                for pid, pos in b["players"].items():
                    require(all(math.isfinite(pos[k]) for k in ("x_m","y_m")) and 0 <= pos["x_m"] <= 105 and 0 <= pos["y_m"] <= 68, "invalid movement coordinate")
                    allowance = .8 if kind == "shot" and pid == e.get("goalkeeper_id") else .003
                    require(distance(a["players"][pid],pos) <= 4.5*(b["period_time_ms"]-a["period_time_ms"])/1000+allowance, "movement exceeds actor reach")
            if kind == "reposition":
                require(e["start"] == e["end"] == ball, "reposition changed ball location")
                require(e["ball_trajectory"] == [{"period_time_ms":r["period_time_ms"], **ball} for r in motion], "reposition ball evidence changed")
            if kind == "movement":
                require(not stopped and e["start"] == ball and e["carrier_id"] in active, "disconnected controlled movement")
                require(roster[e["carrier_id"]]["team_id"] == team and e["end"] == motion[-1]["ball"], "movement carrier mismatch")
                require(e["ball_trajectory"] == [{"period_time_ms":r["period_time_ms"], **r["ball"]} for r in motion], "movement ball evidence mismatch")
                require(all(distance(r["ball"],r["players"][e["carrier_id"]]) < (.111 if i == 0 else .001) for i,r in enumerate(motion)), "carried ball disconnected from carrier")
                ball = e["end"]
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
            if kind in ("pass", "shot", "restart_delivery", "clearance"):
                phase_source = e
            if kind == "pass":
                target = e["intended_recipient_id"]
                require(target in active and roster[target]["team_id"] == team and target != actor, "invalid recipient")
                if metadata["schema_version"] == "1.8":
                    from simulator.pitch import point
                    receiver = snapshot["players"][target]
                    vx,vy = e["receiver_velocity_mps"]
                    lead = min(.6,distance(e["start"],receiver)/16*.45)
                    require(e["receiver_start"] == receiver and e["intended_end"] == point(receiver["x_m"]+vx*lead,receiver["y_m"]+vy*lead), "lead target does not match receiver motion")
                else:
                    require(e["intended_end"] == snapshot["players"][target], "target does not match snapshot")
                defenders = {p: v for p, v in snapshot["players"].items() if roster[p]["team_id"] != team}
                context = pass_context(e["start"], e["intended_end"], defenders)
                require(context == e["difficulty_context"], "incorrect pass context")
                require(e["pressure"] == {k: context[k] for k in ("under_pressure", "nearest_defender_m", "nearest_defender_id")}, "incorrect pressure")
                direction = 1 if (team == "home") == (period == 1) else -1
                require(e["pass_difficulty"] == pass_difficulty(e["start"], e["intended_end"], direction, context["nearest_defender_m"], context["defenders_in_lane"]), "incorrect difficulty")
                require(abs(speed - min(24, 8 + .28*distance(e["start"], e["intended_end"]) + 3*e["kick"]["effort"])) < 1e-9, "incorrect pass command")
                result = resolve_pass(e["start"], e["kick"]["aimed_end"], e["intended_end"], defenders, speed, stop_at_boundary=True, reaction_s=.25 if metadata["schema_version"] == "1.8" else 0,
                                      receiver_start=e.get("receiver_start"))
                crossing = first_exit(e["start"], e["kick"]["aimed_end"]) if result["reason"] == "out_of_play" else None
                if crossing:
                    result.update(end=crossing["location"], outcome="incomplete", reason="out_of_play", interceptor_id=None)
                flagged = result["outcome"] == "complete" and target in contact_for(e, roster)["candidates"] if metadata["schema_version"] in ("1.7", "1.8") else False
                require(e["end"] == result["end"] and e["outcome"] == ("incomplete" if flagged else result["outcome"]) and e["outcome_reason"] == ("offside" if flagged else result["reason"]) and (e["interceptor_id"] or e.get("deflector_id")) == result["interceptor_id"], "invalid pass resolution")
                require(e["recipient_id"] == (target if result["outcome"] == "complete" and not flagged else None), "wrong completed recipient")
                require(e["distance_m"] == round(distance(e["start"], e["end"]), 2), "incorrect pass distance")
            if kind == "shot":
                require(abs(speed-(20+12*e["kick"]["effort"]+2*e["kick"]["shooting_skill"])) < 1e-9, "incorrect shot command")
                keeper = e["goalkeeper_id"]
                require(keeper in active and roster[keeper]["team_id"] != team and active[keeper] == 1, "invalid keeper")
                if e.get("set_piece_type"):
                    restart = by_id.get(e["restart_event_id"], {})
                    require(restart.get("reason") == e["set_piece_type"] and e["set_piece_type"] in ("penalty", "direct_free_kick") and restart.get("player_id") == actor, "illegal direct set-piece shot")
                    require(e["start"] == restart["start"], "set-piece shot moved from restart")
                result = resolve_shot(e["start"], e["kick"]["aimed_end"], snapshot["players"][keeper], speed)
                blocker = interference(contact_for(e, roster), snapshot["players"], e["start"], keeper) if metadata["schema_version"] in ("1.7", "1.8") else None
                require(e["end"] == result["end"] and e["outcome_reason"] == ("offside" if blocker else result["outcome_reason"]) and e["save_outcome"] == (None if blocker else result["save_outcome"]), "shot not supported by contact geometry")
                require(e["outcome"] == ("goal" if not blocker and result["outcome_reason"] == "goal" else "no_goal"), "invalid shot outcome")
                if metadata["schema_version"] in ("1.7", "1.8"):
                    require(e["valid_for_statistics"] == (not bool(blocker)) and e["offside_offender_id"] == blocker and e["observed_outcome_reason"] == result["outcome_reason"], "invalid shot adjudication")
                metrics = e["ball_speed"]
                require(e["shot_speed"] == {"source": "synthetic_trajectory", "method": "initial_segment_average", "mps": metrics["initial_segment_mps"], "kmh": metrics["initial_segment_kmh"], "window_ms": metrics["initial_segment_duration_ms"]}, "incorrect shot speed")
                if e.get("is_rebound"):
                    prior = by_id.get(e.get("rebound_of_shot_event_id"), {})
                    require(prior.get("save_outcome") == "parry", "rebound without parried shot")
            if kind == "clearance":
                crossing = first_exit(e["start"], e["aimed_end"])
                require(e["end"] == (crossing["location"] if crossing else e["aimed_end"]), "invalid clearance boundary")
            if kind == "carry":
                foul = by_id.get(e["foul_event_id"], {})
                require(foul.get("victim_id") == actor and speed <= 4.5, "unsupported advantage carry")
                require(advantages.get(e["foul_event_id"]) == "pending", "carry outside advantage evaluation")
                direction = 1 if (team == "home") == (period == 1) else -1
                require(1 <= direction*(e["end"]["x_m"]-e["start"]["x_m"]) <= 3.001 and abs(e["end"]["y_m"]-e["start"]["y_m"]) < .001, "invalid bounded advantage path")
                opponents = [p for pid, p in snapshot["players"].items() if roster[pid]["team_id"] != team and pid != foul["player_id"]]
                require(min(distance(p, e["end"]) for p in opponents) > 2.5, "advantage not supported by open continuation")
            if kind == "parry":
                prior = by_id.get(e["shot_event_id"], {})
                require(prior.get("save_outcome") == "parry" and actor == prior.get("goalkeeper_id"), "parry without keeper save")
                require(e["start"] == prior["end"], "parry did not start at save contact")
                command = prior["kick"]["commanded_mean_speed_mps"]
                direction = 1 if (prior["team_id"] == "home") == (period == 1) else -1
                target = parry_target(prior["start"], prior["end"], prior["pitch_snapshot"]["players"][actor], direction, command)
                crossing = first_exit(e["start"], target)
                require(e["end"] == (crossing["location"] if crossing else target) and speed == max(6, command*.35), "parry not supported by shot contact")
            if kind == "deflection":
                prior = by_id.get(e["source_event_id"], {})
                touch = by_id.get(e["touch_event_id"], {})
                require(touch.get("control", {}).get("classification") == "deflection" and touch.get("source_event_id") == prior.get("event_id") and actor == touch.get("player_id"), "deflection without uncontrolled touch")
                command = prior.get("kick", {}).get("commanded_mean_speed_mps", prior.get("commanded_mean_speed_mps"))
                target = deflection_target(prior["start"], prior["end"], prior["pitch_snapshot"]["players"][actor])
                crossing = first_exit(e["start"], target)
                require(e["end"] == (crossing["location"] if crossing else target) and speed == max(4, command*.3), "unsupported deflection geometry")
            if kind == "restart_delivery":
                restart = by_id.get(e["restart_event_id"], {})
                require(restart.get("type") == "restart" and restart.get("reason") == e["restart_type"] and restart.get("player_id") == actor, "delivery without restart")
                target = e["intended_recipient_id"]
                require(target in active and roster[target]["team_id"] == team and target != actor, "invalid restart recipient")
                require(e["intended_end"] == snapshot["players"][target], "restart target disagrees with snapshot")
                defenders = {p: v for p, v in snapshot["players"].items() if roster[p]["team_id"] != team}
                result = resolve_pass(e["start"], e["intended_end"], e["intended_end"], defenders, speed, stop_at_boundary=True, reaction_s=.25 if metadata["schema_version"] == "1.8" else 0)
                flagged = result["outcome"] == "complete" and target in contact_for(e, roster)["candidates"] if metadata["schema_version"] in ("1.7", "1.8") else False
                require(e["end"] == result["end"] and e["outcome"] == ("incomplete" if flagged else result["outcome"]) and (e["interceptor_id"] or e.get("deflector_id")) == result["interceptor_id"], "restart delivery disagrees with geometry")
                require(e["recipient_id"] == (target if result["outcome"] == "complete" and not flagged else None), "incorrect restart receiver")
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
            require(abandoned or period in announcements, "half ended before added time announced")
            require(abandoned or t >= metadata["period_duration_ms"] + announcements[period]["minimum_added_ms"], "half ended too early")
            ledger = e["lost_time_ledger"]
            logged = [x for x in events[:index] if x["period"] == period and x["type"] == "time_lost"]
            require(sum(r["duration_ms"] for r in ledger) == e["lost_time_ms"] == sum(x["duration_ms"] for x in logged), "lost-time ledger mismatch")
            require(e["actual_added_ms"] == max(0, t-metadata["period_duration_ms"]), "incorrect actual added time")
            ends[period], stopped = e["match_time_ms"], True
        by_id[e["event_id"]] = e
    if score != metadata["final_score"] or set(starts) != set(ends) or (not abandoned and set(starts) != {1, 2}):
        raise ValueError("Incomplete match/final score mismatch")
    if ends[max(ends)] != metadata["match_duration_ms"]:
        raise ValueError("Incorrect match duration")
    required = {e["event_id"] for e in events if e.get("outcome_reason") == "offside"}
    if not required <= offside_sources:
        raise ValueError("Invalidated attack lacks offside decision/restart")
    if offside_stops != {e["event_id"] for e in events if e["type"] == "offside"}:
        raise ValueError("Offside decision lacks its stoppage/restart award")
