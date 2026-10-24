"""Generate connected, explicitly synthetic match events (no external data)."""
import argparse
import json
import math
from pathlib import Path

from simulator.metrics import ball_speed, make_trajectory, pass_difficulty


from simulator.engine import SCENARIOS, generate
from simulator.pitch import distance, pass_context, resolve_pass
from simulator.statistics import calculate_statistics


def validate(metadata, events):
    """Validate core stream invariants; raise ValueError on the first violation."""
    if metadata.get("schema_version") in ("1.5", "1.6", "1.7", "1.8", "1.9"):
        from simulator.validation import validate_stream
        return validate_stream(metadata, events)
    roster = {p["player_id"]: p["team_id"] for p in metadata["players"]}
    player_metadata = {p["player_id"]: p for p in metadata["players"]}
    active = {pid for pid, p in player_metadata.items() if p.get("is_starter", True)}
    ever_played = active.copy()
    active_slots = {pid: p.get("formation_slot") or p.get("shirt_number") for pid, p in player_metadata.items() if pid in active}
    substitution_counts = {"home": 0, "away": 0}
    substitution_windows = {"home": set(), "away": set()}
    in_stoppage = False
    seen, previous, score = set(), (0, 0), {"home": 0, "away": 0}
    possession_team = {}
    for sequence, event in enumerate(events, 1):
        def require(condition, message):
            if not condition:
                raise ValueError(f"Event {sequence}: {message}")
        require(event["event_id"] not in seen, "duplicate event ID")
        seen.add(event["event_id"])
        require(event["sequence"] == sequence, "sequence gap")
        require(event["match_id"] == metadata["match_id"], "wrong match")
        stamp = (event["period"], event["period_time_ms"])
        require(stamp >= previous, "time moved backwards")
        require(event["period"] in (1, 2) and 0 <= stamp[1] <= metadata["period_duration_ms"], "invalid clock")
        previous = stamp
        team, actor = event["team_id"], event["player_id"]
        require(team in (None, "home", "away"), "invalid team")
        if actor:
            require(roster.get(actor) == team, "player/team mismatch")
            require(actor in active, "inactive player action")
        if event["type"] == "stoppage":
            in_stoppage = True
        if event["type"] == "resume":
            require(in_stoppage, "resume without stoppage")
            in_stoppage = False
        if event["type"] == "substitution":
            off, on = event["player_off_id"], event["player_on_id"]
            require(in_stoppage, "substitution outside a stoppage")
            require(off in active and on in roster and on not in ever_played, "invalid substitution membership")
            require(roster[off] == team and roster[on] == team, "substitution team mismatch")
            require(player_metadata[off]["role"] != "GK", "automatic goalkeeper substitution")
            require(player_metadata[off]["position_group"] == player_metadata[on]["position_group"], "incompatible substitute")
            require(event["formation_slot"] == active_slots[off], "substitute did not inherit formation slot")
            require(not event["halftime"] or (event["period"] == 2 and event["period_time_ms"] == 0), "invalid half-time window")
            active_slots[on] = active_slots.pop(off)
            active.remove(off)
            active.add(on)
            ever_played.add(on)
            substitution_counts[team] += 1
            if not event["halftime"]:
                substitution_windows[team].add(event["window_id"])
            require(substitution_counts[team] <= 5 and len(substitution_windows[team]) <= 3, "substitution limit exceeded")
            require(sum(roster[pid] == team for pid in active) == 11, "invalid active team size")
            require(set(event["positions_after"]) == active, "incorrect substitution position snapshot")
        for key in ("start", "end"):
            if key in event:
                p = event[key]
                require(0 <= p["x_m"] <= 105 and 0 <= p["y_m"] <= 68, "point outside pitch")
        possession = event["possession_id"]
        if possession and event["type"] != "pressure":
            require(possession_team.setdefault(possession, team) == team, "possession changed team without new ID")
        if event["type"] == "pass":
            recipient = event["recipient_id"]
            require(event["outcome"] in ("complete", "incomplete"), "invalid pass outcome")
            require(roster.get(recipient) == team if event["outcome"] == "complete" else recipient is None,
                    "invalid pass recipient")
            require(recipient != actor, "self pass")
            require(event["intended_recipient_id"] in active if "intended_recipient_id" in event else True, "inactive pass target")
            if event["schema_version"] in ("1.1", "1.2", "1.3", "1.4"):
                direction = 1 if (team == "home") == (event["period"] == 1) else -1
                intended = event.get("intended_end", event["end"])
                expected = pass_difficulty(event["start"], intended, direction,
                                           event["pressure"]["nearest_defender_m"],
                                           event["difficulty_context"]["defenders_in_lane"])
                require(event["pass_difficulty"] == expected, "incorrect pass difficulty")
                actual_distance = math.hypot(event["end"]["x_m"] - event["start"]["x_m"],
                                             event["end"]["y_m"] - event["start"]["y_m"])
                require(event["distance_m"] == round(actual_distance, 2), "incorrect pass distance")
        if event["type"] in ("pass", "shot") and event["schema_version"] in ("1.2", "1.3", "1.4"):
            snapshot = event["pitch_snapshot"]
            require(set(snapshot["players"]) == active, "pitch snapshot does not match active lineup")
            require(snapshot["period_time_ms"] == event["ball_trajectory"][0]["period_time_ms"], "snapshot clock mismatch")
            require(distance(snapshot["players"][actor], event["start"]) < .001, "actor is not at the ball")
            for position in snapshot["players"].values():
                require(0 <= position["x_m"] <= 105 and 0 <= position["y_m"] <= 68, "player outside pitch")
            opponent = "away" if team == "home" else "home"
            defenders = {pid: p for pid, p in snapshot["players"].items() if roster[pid] == opponent}
            if event["type"] == "pass":
                require(event["intended_recipient_id"] != actor and roster.get(event["intended_recipient_id"]) == team,
                        "invalid intended recipient")
                require(event["intended_end"] == snapshot["players"][event["intended_recipient_id"]], "target is not teammate position")
                context = pass_context(event["start"], event["intended_end"], defenders)
                require(event["difficulty_context"] == context, "context not supported by defender positions")
                require(event["pressure"] == {k: context[k] for k in ("under_pressure", "nearest_defender_m", "nearest_defender_id")},
                        "pressure not supported by pitch state")
                command = min(24, 8 + .28 * distance(event["start"], event["intended_end"]) + 3 * event["kick"]["effort"])
                require(abs(command - event["kick"]["commanded_mean_speed_mps"]) < 1e-9, "kick speed not supported by action")
                result = resolve_pass(event["start"], event["kick"]["aimed_end"], event["intended_end"], defenders, command)
                require(event["outcome"] == result["outcome"] and event["end"] == result["end"]
                        and event["outcome_reason"] == result["reason"] and event["interceptor_id"] == result["interceptor_id"],
                        "pass outcome not supported by action geometry")
                require(event["recipient_id"] == (event["intended_recipient_id"] if result["outcome"] == "complete" else None),
                        "recipient does not match resolved outcome")
            else:
                command = 20 + 12 * event["kick"]["effort"] + 2 * event["kick"]["shooting_skill"]
                require(abs(command - event["kick"]["commanded_mean_speed_mps"]) < 1e-9, "shot kick mismatch")
                flight_s = (event["period_time_ms"] - snapshot["period_time_ms"]) / 1000
                on_target = abs(event["end"]["y_m"] - 34) <= 3.66
                saved = on_target and distance(snapshot["players"][f"{opponent}-01"], event["end"]) <= 4.5 * flight_s
                reason = "goal" if on_target and not saved else "saved" if saved else "off_target"
                require(event["outcome_reason"] == reason and event["outcome"] == ("goal" if reason == "goal" else "no_goal"),
                        "shot outcome not supported by geometry")
            expected_samples = make_trajectory(event["start"], event["end"], snapshot["period_time_ms"], command,
                                               decelerate=event["type"] == "shot")
            require(event["ball_trajectory"] == expected_samples, "trajectory not supported by kick command")
        if event["type"] in ("pass", "shot") and event["schema_version"] in ("1.1", "1.2", "1.3", "1.4"):
            samples = event["ball_trajectory"]
            require(len(samples) >= 2, "missing ball observations")
            require(samples[0]["period_time_ms"] >= (events[sequence - 2]["period_time_ms"]
                    if sequence > 1 and events[sequence - 2]["period"] == event["period"] else 0),
                    "flight overlaps preceding event")
            require(samples[-1]["period_time_ms"] == event["period_time_ms"], "arrival clock mismatch")
            for sample in samples:
                require(0 <= sample["x_m"] <= 105 and 0 <= sample["y_m"] <= 68, "ball sample outside pitch")
            for sample, endpoint in ((samples[0], event["start"]), (samples[-1], event["end"])):
                require(all(abs(sample[k] - endpoint[k]) < 0.00001 for k in ("x_m", "y_m")), "trajectory endpoint mismatch")
            computed = ball_speed(samples)
            require(event["ball_speed"] == computed, "incorrect ball speed")
            if event["type"] == "shot":
                require(event["shot_speed"] == {"source": "synthetic_trajectory", "method": "initial_segment_average",
                                                "mps": computed["initial_segment_mps"],
                                                "kmh": computed["initial_segment_kmh"],
                                                "window_ms": computed["initial_segment_duration_ms"]}, "incorrect shot speed")
        if event["type"] == "goal":
            shot = events[sequence - 2] if sequence > 1 else {}
            require(shot.get("type") == "shot" and shot.get("outcome") == "goal"
                    and shot.get("event_id") == event["shot_event_id"], "goal without preceding scoring shot")
            score[team] += 1
            require(event["score"] == score, "incorrect score")
    if score != metadata["final_score"]:
        raise ValueError("Final score mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scenario", choices=SCENARIOS, default="match")
    parser.add_argument("--minutes-per-half", type=int, default=45)
    parser.add_argument("--output", type=Path, default=Path("data/generated/demo"))
    args = parser.parse_args()
    metadata, events, truth = generate(args.seed, args.scenario, args.minutes_per_half)
    validate(metadata, events)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in (("metadata.json", metadata), ("evaluation-only.json", truth)):
        (args.output / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    (args.output / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    summary = {"match_id": metadata["match_id"], "event_count": len(events),
               "final_score": metadata["final_score"], "validated": True,
               "counts": {kind: sum(e["type"] == kind for e in events) for kind in sorted({e["type"] for e in events})}}
    def distribution(values):
        return {"count": len(values), "min": min(values), "mean": round(sum(values) / len(values), 2),
                "max": max(values)} if values else {"count": 0, "min": None, "mean": None, "max": None}
    summary["synthetic_metrics"] = {
        "pass_difficulty_score": distribution([e["pass_difficulty"]["score"] for e in events if e["type"] == "pass"]),
        "pass_average_ball_speed_kmh": distribution([e["ball_speed"]["average_kmh"] for e in events if e["type"] == "pass"]),
        "shot_initial_segment_speed_kmh": distribution([e["shot_speed"]["kmh"] for e in events if e["type"] == "shot" and e.get("valid_for_statistics") is not False]),
    }
    summary["pass_accuracy"] = {}
    for team in ("home", "away"):
        passes = [e for e in events if e["type"] == "pass" and e["team_id"] == team]
        completed = sum(e["outcome"] == "complete" for e in passes)
        summary["pass_accuracy"][team] = {"attempted": len(passes), "completed": completed,
                                           "percentage": round(completed / len(passes) * 100, 2) if passes else None}
    summary.update(calculate_statistics(metadata, events))
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
