"""Shared event metric aggregation for team and player views."""

METRICS = (
    "pass_distance_m", "intended_pass_distance_m", "pass_difficulty_score",
    "pass_average_ball_speed_kmh", "pass_peak_segment_ball_speed_kmh",
    "shot_average_ball_speed_kmh", "shot_initial_segment_speed_kmh",
    "shot_peak_segment_speed_kmh", "ball_average_speed_kmh",
)


def distribution(values):
    return {"count": len(values), "min": round(min(values), 4),
            "mean": round(sum(values) / len(values), 2), "max": round(max(values), 4)} if values else {
                "count": 0, "min": None, "mean": None, "max": None}


def record_action_metrics(values, event):
    kind = event["type"]
    if kind not in ("pass", "shot"):
        return
    speed = event.get("ball_speed", {})
    if "average_kmh" in speed:
        values["ball_average_speed_kmh"].append(speed["average_kmh"])
        values[f"{kind}_average_ball_speed_kmh"].append(speed["average_kmh"])
    if "peak_segment_mps" in speed:
        key = "pass_peak_segment_ball_speed_kmh" if kind == "pass" else "shot_peak_segment_speed_kmh"
        values[key].append(speed["peak_segment_mps"] * 3.6)
    if kind == "pass":
        for field, metric in (("distance_m", "pass_distance_m"), ("intended_distance_m", "intended_pass_distance_m")):
            if field in event:
                values[metric].append(event[field])
        if "pass_difficulty" in event:
            values["pass_difficulty_score"].append(event["pass_difficulty"]["score"])
    elif "shot_speed" in event:
        values["shot_initial_segment_speed_kmh"].append(event["shot_speed"]["kmh"])
