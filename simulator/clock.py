"""Separate period clocks (including added time) from the monotonic replay clock."""
import math


def period_offset(metadata, period):
    return metadata.get("period_offsets_ms", {}).get(str(period), (period - 1) * metadata["period_duration_ms"])


def elapsed(metadata, period, time_ms):
    return period_offset(metadata, period) + time_ms


def event_time(metadata, event):
    return event.get("match_time_ms", elapsed(metadata, event["period"], event["period_time_ms"]))


def total_duration(metadata):
    return metadata.get("match_duration_ms", 2 * metadata["period_duration_ms"])


class PeriodClock:
    """Explicit lost-time ledger. Normal restart preparation is not all added back.

    Announce a minimum at regulation end; recover subsequent qualifying losses
    as well. Finishing an in-flight action can extend the whistle slightly.
    """
    def __init__(self, regulation_ms):
        self.regulation = regulation_ms
        self.quantum = max(1000, round(60_000 * regulation_ms / 2_700_000))
        self.losses = []
        self.announced = None
        self.loss_at_announcement = 0

    def lost(self, start, end, reason, source_id):
        if end > start:
            self.losses.append({"start_ms": start, "end_ms": end, "duration_ms": end - start,
                                "reason": reason, "source_event_id": source_id})

    @property
    def lost_ms(self):
        return sum(row["duration_ms"] for row in self.losses)

    def announce(self):
        self.loss_at_announcement = self.lost_ms
        self.announced = math.ceil(self.lost_ms / self.quantum) * self.quantum
        return self.announced

    @property
    def end(self):
        return self.regulation + (self.announced or 0) + (self.lost_ms - self.loss_at_announcement if self.announced is not None else 0)
