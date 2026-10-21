"""Versioned, uncalibrated match rating based only on observed player actions."""

RATING_MODEL = {
    "version": "matchlens-event-rating-v1", "scale": {"min": 1.0, "max": 10.0},
    "baseline": 6.0, "minimum_evidence_events": 5,
    "eligibility": "5 attributable events, or a goal, assist, save, or goalkeeper goal conceded",
    "assist_window_ms": 10_000,
    "limitations": ["Original heuristic, not a commercial provider rating or calibrated football model",
                    "No off-ball positioning, running distance, tackles, fouls, or unobserved mistakes scored",
                    "Goalkeeper goals conceded are contextual debits, not attribution of individual fault",
                    "Pressure observations and ordinary received passes earn no direct rating bonus"],
    "weights": {
        "goal": {"GK": 1.3, "DF": 1.2, "MF": 1.0, "FW": 0.9},
        "assist": {"GK": 0.65, "DF": 0.8, "MF": 0.85, "FW": 0.75},
        "defence_multiplier": {"GK": 0.4, "DF": 1.2, "MF": 1.0, "FW": 0.7},
        "interception": 0.07, "recovery": 0.03, "non_assist_key_pass": 0.06,
        "save": 0.15, "goalkeeper_goal_conceded": -0.12,
        "non_goal_shot_on_target": 0.05, "off_target_shot": -0.03,
        "hard_completed_pass": 0.025,
    },
    "caps": {"scoring": 3.0, "assists": 1.8, "creation": 0.6, "defence": 1.4,
             "saves": 2.0, "goals_conceded": -1.2, "shooting": 0.4,
             "misses": -0.3, "hard_passing": 0.35},
    "passing_formula": "clamp(1.2*(completed - 0.75*attempted)/max(attempted,5), -0.7, 0.3)",
}


def player_rating(stats, evidence_ids, provisional):
    role = stats["role"] if stats["role"] in ("GK", "DF", "MF", "FW") else "MF"
    weights, caps = RATING_MODEL["weights"], RATING_MODEL["caps"]
    attempts, completed = stats["passes"]["attempted"], stats["passes"]["completed"]
    components = {
        "scoring": min(caps["scoring"], stats["goals"] * weights["goal"][role]),
        "assists": min(caps["assists"], stats["assists"] * weights["assist"][role]),
        "creation": min(caps["creation"], max(0, stats["key_passes"] - stats["assists"]) * weights["non_assist_key_pass"]),
        "passing": max(-0.7, min(0.3, 1.2 * (completed - 0.75 * attempts) / max(attempts, 5))),
        "hard_passing": min(caps["hard_passing"], stats["passes"]["hard_completed"] * weights["hard_completed_pass"]),
        "defence": min(caps["defence"], weights["defence_multiplier"][role] * (
            stats["interceptions"] * weights["interception"] + stats["recoveries"] * weights["recovery"])),
        "saves": min(caps["saves"], stats["saves"] * weights["save"]),
        "goals_conceded": max(caps["goals_conceded"], stats["goals_conceded"] * weights["goalkeeper_goal_conceded"]) if role == "GK" else 0,
        "shooting": min(caps["shooting"], max(0, stats["shots"]["on_target"] - stats["goals"]) * weights["non_goal_shot_on_target"]),
        "misses": max(caps["misses"], stats["shots"]["off_target"] * weights["off_target_shot"]),
    }
    decisive = stats["goals"] + stats["assists"] + stats["saves"] + stats["goals_conceded"] > 0
    eligible = len(evidence_ids) >= RATING_MODEL["minimum_evidence_events"] or decisive
    rounded = {key: round(value, 4) for key, value in components.items()}
    unclamped = round(RATING_MODEL["baseline"] + sum(rounded.values()), 4)
    value = round(max(1, min(10, unclamped)), 1) if eligible else None
    return {"model": RATING_MODEL["version"], "value": value,
            "status": "rated" if eligible else "insufficient_evidence",
            "provisional": provisional, "baseline": RATING_MODEL["baseline"],
            "components": rounded, "unclamped_value": unclamped if eligible else None,
            "evidence_event_count": len(evidence_ids), "evidence_event_ids": sorted(evidence_ids),
            "explanation": "6.0 baseline plus displayed components, clamped to 1–10 and rounded to one decimal" if eligible else "Not enough attributable action evidence to assign a rating"}
