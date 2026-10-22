"""Basic football simulation: shared state -> action -> resolution -> metrics."""
import random

from simulator.progression import MatchProgression


SCENARIOS = ("match", "balanced", "high-press", "quiet-possession", "chaotic")


def generate(seed=42, scenario="match", minutes_per_half=45):
    if scenario not in SCENARIOS or not 1 <= minutes_per_half <= 45:
        raise ValueError("Select a known scenario and 1..45 minutes per half")
    rng = random.Random(seed)
    match_id = f"synthetic-v1.8-{scenario}-{seed}-{minutes_per_half}"
    roles = ["GK", "DF", "DF", "DF", "DF", "MF", "MF", "MF", "FW", "FW", "FW",
             "GK", "DF", "DF", "DF", "MF", "MF", "MF", "FW", "FW"]
    groups = ["GK", "FB", "CB", "CB", "FB", "WM", "CM", "WM", "W", "ST", "W",
              "GK", "FB", "CB", "FB", "CM", "CM", "WM", "W", "ST"]
    players = [{"player_id": f"{team}-{i:02}", "team_id": team,
                "name": f"{label} Player {i:02}", "shirt_number": i, "role": role,
                "is_starter": i <= 11, "formation_slot": i if i <= 11 else None,
                "position_group": groups[i - 1],
                "passing_skill": round(rng.uniform(0.65, 0.95), 3),
                "shooting_skill": round(rng.uniform(0.55, 0.9), 3)}
               for team, label in (("home", "Northbridge"), ("away", "Southbank"))
               for i, role in enumerate(roles, 1)]
    duration = minutes_per_half * 60_000
    progression = MatchProgression(seed, duration)
    start_window = min(600_000, duration // 3)
    end_window = min(start_window + 300_000, duration - 10_000)
    metadata = {"schema_version": "1.8", "match_id": match_id, "source": "synthetic", "seed": seed,
                "rating_model_version": "matchlens-event-rating-v2",
                "pitch": {"length_m": 105, "width_m": 68},
                "coordinate_origin": "bottom-left; fixed pitch coordinates", "period_duration_ms": duration,
                "home_attacks_positive_x": {"1": True, "2": False},
                "teams": [{"team_id": "home", "name": "Northbridge FC"},
                          {"team_id": "away", "name": "Southbank FC"}], "players": players,
                "event_time_semantics": "Ball actions emitted at arrival; snapshot/samples are period-local; match_time_ms is monotonic including added time",
                "simulation_model": {"player_movement_cap_mps": 4.5, "ball_sample_interval_ms": 50,
                                     "pass_context": "measured from persistent kick-time pitch state",
                                     "pass_outcome": "defender reach/interception or receiver reach",
                                     "pass_mean_speed_mps": "min(24, 8 + .28*intended_distance + 3*kick_effort)",
                                     "shot_mean_speed_mps": "20 + 12*kick_effort + 2*shooting_skill",
                                     "shot_outcome": "goal-mouth test and goalkeeper reach",
                                     "scenario_policy": "changes tactics and action selection, not metric values"},
                "substitution_policy": {"max_substitutions": 5, "max_in_play_windows": 3, "bench_per_team": 9,
                                        "primary_window_minutes": [60, 70], "short_match_timing": "scaled proportionally",
                                        "selection": "lowest currently rated eligible starter with same-position-group bench cover; keeper excluded",
                                        "stoppage_model": "next natural ball-out, goal, foul or offside stoppage; halftime separately"},
                "limitations": ["Simplified 2D model; point-player offside only; no aerial play or referee countdown offences",
                                "Planar goalkeeper reach/hold/parry and restart placement are uncalibrated heuristics",
                                "Generated steering samples; selected receiving/contact runs remain simplified",
                                "Snapshots are not a continuous player tracking feed",
                                "Skills and action choices use seeded randomness; metrics are deterministic from evidence",
                                "Difficulty and motion models are uncalibrated; no real identities or professional realism claim"]}
    from simulator.simulation import Simulation
    return Simulation(metadata, rng, progression, scenario, start_window, end_window).run()
