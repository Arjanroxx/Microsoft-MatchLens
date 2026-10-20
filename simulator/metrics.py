"""Transparent metrics over simulated pitch-plane ball observations."""
import math


DIFFICULTY_MODEL = "heuristic-v1"


def pass_difficulty(start, end, direction, nearest_defender_m, defenders_in_lane):
    """0..100 difficulty heuristic, not a probability; excludes pass outcome."""
    if direction not in (-1, 1):
        raise ValueError("direction must be -1 or 1")
    if not math.isfinite(nearest_defender_m) or nearest_defender_m < 0:
        raise ValueError("nearest_defender_m must be finite and nonnegative")
    if not isinstance(defenders_in_lane, int) or defenders_in_lane < 0:
        raise ValueError("defenders_in_lane must be a nonnegative integer")
    dx, dy = end["x_m"] - start["x_m"], end["y_m"] - start["y_m"]
    distance = math.hypot(dx, dy)
    components = {
        "distance": min(distance / 60, 1),
        "pressure": max(0, 1 - nearest_defender_m / 5),
        "forwardness": max(0, direction * dx / distance) if distance else 0,
        "lane_congestion": min(defenders_in_lane / 3, 1),
    }
    weights = {"distance": 40, "pressure": 25, "forwardness": 20, "lane_congestion": 15}
    score = round(sum(weights[key] * value for key, value in components.items()))
    return {"model": DIFFICULTY_MODEL, "score": score,
            "rating": "easy" if score < 35 else "moderate" if score < 65 else "hard",
            "components": {k: round(v, 6) for k, v in components.items()},
            "weights": weights, "is_probability": False}


def make_trajectory(start, end, kick_time_ms, target_average_mps, decelerate=False):
    """Synthetic, straight 2D trajectory. Average target determines flight duration."""
    if not math.isfinite(target_average_mps) or target_average_mps <= 0:
        raise ValueError("target_average_mps must be finite and positive")
    distance = math.hypot(end["x_m"] - start["x_m"], end["y_m"] - start["y_m"])
    duration = max(1, math.ceil(distance / target_average_mps * 1000))
    offsets = list(range(0, duration, 50)) + [duration]
    samples = []
    for offset in offsets:
        u = offset / duration
        fraction = 1.2 * u - 0.2 * u * u if decelerate else u
        samples.append({"period_time_ms": kick_time_ms + offset,
                        "x_m": round(start["x_m"] + fraction * (end["x_m"] - start["x_m"]), 6),
                        "y_m": round(start["y_m"] + fraction * (end["y_m"] - start["y_m"]), 6)})
    return samples


def ball_speed(samples):
    """Recompute speeds from observations, rather than reporting sampled targets."""
    if len(samples) < 2:
        raise ValueError("At least two ball samples are required")
    travelled, speeds = 0.0, []
    for a, b in zip(samples, samples[1:]):
        if not all(math.isfinite(p[k]) for p in (a, b) for k in ("period_time_ms", "x_m", "y_m")):
            raise ValueError("Samples must be finite")
        dt = (b["period_time_ms"] - a["period_time_ms"]) / 1000
        if dt <= 0:
            raise ValueError("Ball sample timestamps must strictly increase")
        distance = math.hypot(b["x_m"] - a["x_m"], b["y_m"] - a["y_m"])
        travelled += distance
        speeds.append(distance / dt)
    elapsed_ms = samples[-1]["period_time_ms"] - samples[0]["period_time_ms"]
    average = travelled / (elapsed_ms / 1000)
    return {"source": "synthetic_trajectory", "dimension": "pitch_plane_2d",
            "duration_ms": elapsed_ms, "distance_m": round(travelled, 4),
            "average_mps": round(average, 4), "average_kmh": round(average * 3.6, 4),
            "peak_segment_mps": round(max(speeds), 4),
            "initial_segment_mps": round(speeds[0], 4),
            "initial_segment_kmh": round(speeds[0] * 3.6, 4),
            "initial_segment_duration_ms": samples[1]["period_time_ms"] - samples[0]["period_time_ms"]}
