"""Versioned, dependency-free contracts for the local match intelligence API."""
from dataclasses import asdict, dataclass
import math

SCHEMA = "matchlens-insight-v1"


def bounded_time(value, maximum, name="time_ms"):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if not 0 <= value <= maximum:
        raise ValueError(f"{name} is outside the match")
    return int(value)


@dataclass(frozen=True)
class ViewerProfile:
    audience_mode: str = "casual"
    locale: str = "en"
    team_id: str | None = None
    player_id: str | None = None
    metric_focus: str = "all"

    @classmethod
    def parse(cls, data, metadata):
        if not isinstance(data, dict) or set(data)-set(cls.__dataclass_fields__):
            raise ValueError("Invalid viewer profile fields")
        p = cls(**data)
        if p.audience_mode not in ("casual", "analyst") or p.locale not in ("en", "hi"):
            raise ValueError("Choose casual/analyst and en/hi")
        if p.team_id not in (None, "home", "away"):
            raise ValueError("Unknown favourite team")
        roster = {p["player_id"]:p for p in metadata["players"]}
        if p.player_id is not None and p.player_id not in roster:
            raise ValueError("Unknown favourite player")
        if p.player_id and p.team_id and roster[p.player_id]["team_id"] != p.team_id:
            raise ValueError("Favourite player and team must agree")
        if p.metric_focus not in ("all", "xg", "passing", "pressure"):
            raise ValueError("Unknown metric focus")
        return p

    def dictionary(self):
        return asdict(self)


def request_context(body, metadata):
    if not isinstance(body, dict):
        raise ValueError("Request must be a JSON object")
    allowed = {"match_id","time_ms","profile","session_epoch","scope","since_ms"}
    if set(body)-allowed:
        raise ValueError("Unknown request fields")
    if body.get("match_id") != metadata["match_id"]:
        raise ValueError("Request belongs to another match")
    epoch = body.get("session_epoch", "default")
    if not isinstance(epoch,str) or not 1 <= len(epoch) <= 80:
        raise ValueError("Invalid session_epoch")
    return (bounded_time(body.get("time_ms"),metadata.get("match_duration_ms",metadata["period_duration_ms"]*2)),
            ViewerProfile.parse(body.get("profile",{}), metadata), epoch)
