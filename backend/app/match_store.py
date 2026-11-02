"""Ordered ingestion and immutable, evidence-backed replay snapshots."""
from bisect import bisect_right
from collections import OrderedDict
import copy
import hashlib
import json
import math
from pathlib import Path
import threading

from simulator.clock import elapsed, event_time, total_duration
from simulator.generate import validate
from simulator.statistics import calculate_statistics, MatchStatistics
from .contracts import bounded_time


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()[:20]


class MatchStore:
    """Loaded replays are queryable by prefix; live stores accept ordered events."""
    def __init__(self, metadata, events=(), *, replay=True):
        self.metadata = copy.deepcopy(metadata)
        self.events, self.times, self.identities = [], [], {}
        self.fingerprint = digest(self.metadata)
        self.chain = self.fingerprint
        self.prefix_hashes = []
        self.reducer = MatchStatistics(self.metadata)
        self.lock = threading.RLock()
        self.cache = OrderedDict()
        self.replay = replay
        if events:
            rows = list(events)
            validate(self.metadata,rows)
            for e in rows:
                self._append(e)

    @classmethod
    def load(cls,path, *, live=False):
        base=Path(path)
        metadata=json.loads((base/"metadata.json").read_text(encoding="utf-8"))
        events=[json.loads(line) for line in (base/"events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        validate(metadata,events)
        return cls(metadata,() if live else events,replay=not live)

    def _append(self,event,update=True):
        e=copy.deepcopy(event)
        event_hash=digest(e)
        if update:self.reducer.update(e)
        self.events.append(e)
        self.times.append(event_time(self.metadata,e))
        self.identities[e["event_id"]]=event_hash
        self.chain=digest([self.chain,event_hash])
        self.prefix_hashes.append(self.chain)

    def ingest(self,event):
        if self.replay:
            raise ValueError("This is a read-only replay; start with --live for event ingestion")
        if not isinstance(event,dict):
            raise ValueError("Event must be an object")
        with self.lock:
            if event.get("match_id")!=self.metadata["match_id"] or event.get("schema_version")!=self.metadata["schema_version"]:
                raise ValueError("Wrong match or event schema")
            eid=event.get("event_id")
            if not isinstance(eid,str) or not 1<=len(eid)<=120:
                raise ValueError("Invalid event ID")
            fingerprint=digest(event)
            if eid in self.identities:
                if self.identities[eid]!=fingerprint:
                    raise ValueError("Conflicting duplicate event")
                return {"accepted":False,"duplicate":True,"through_sequence":len(self.events)}
            if type(event.get("sequence")) is not int or event["sequence"]!=len(self.events)+1:
                raise ValueError("Sequence gap or out-of-order event; retry from the acknowledged sequence")
            if type(event.get("period")) is not int or event['period'] not in (1,2) or type(event.get("period_time_ms")) is not int:
                raise ValueError("Invalid event clock")
            when=event_time(self.metadata,event)
            bounded_time(when,total_duration(self.metadata))
            if self.times and when<self.times[-1]:
                raise ValueError("Event clock moved backwards")
            if event.get("match_time_ms",when)!=when or not isinstance(event.get("type"),str):
                raise ValueError("Invalid event envelope")
            actor=event.get("player_id")
            roster={p["player_id"]:p for p in self.metadata["players"]}
            if actor and (actor not in roster or roster[actor]["team_id"]!=event.get("team_id")):
                raise ValueError("Unknown player or wrong team")
            # Exercise reducers before committing; malformed action structures cannot
            # poison stored state. Full physical validation runs when the stream closes.
            rows=self.events+[event]
            try:
                if event["type"] in ("match_abandoned",) or (event["type"]=="period_end" and event["period"]==2):
                    validate(self.metadata,rows)
                self.reducer.update(event)
            except (KeyError,TypeError,ValueError,AttributeError) as error:
                self.reducer=MatchStatistics(self.metadata)
                for previous in self.events:self.reducer.update(previous)
                raise ValueError(f"Invalid event payload: {error}") from error
            self._append(event,update=False)
            self.cache.clear()
            return {"accepted":True,"duplicate":False,"through_sequence":len(self.events)}

    def rollback_last(self,event_id):
        """Undo an uncommitted live event while the application holds the lock."""
        with self.lock:
            if self.replay or not self.events or self.events[-1]['event_id']!=event_id:
                raise ValueError('Can only roll back the last live event')
            self.events.pop();self.times.pop();self.prefix_hashes.pop()
            del self.identities[event_id]
            self.chain=self.prefix_hashes[-1] if self.prefix_hashes else self.fingerprint
            self.reducer=MatchStatistics(self.metadata)
            for previous in self.events:self.reducer.update(previous)
            self.cache.clear()

    def snapshot(self,time_ms):
        t=bounded_time(time_ms,total_duration(self.metadata))
        with self.lock:
            if not self.replay and t>(self.times[-1] if self.times else 0):
                raise ValueError("Requested cutoff has not been ingested")
            key=(len(self.events),t)
            if key in self.cache:
                self.cache.move_to_end(key)
                return copy.deepcopy(self.cache[key])
            count=bisect_right(self.times,t)
            rows=self.events[:count]
            period=rows[-1]["period"] if rows else 1
            local=t-elapsed(self.metadata,period,0)
            state=calculate_statistics(self.metadata,rows,(period,local))
            result={"match_id":self.metadata["match_id"],"schema_version":self.metadata["schema_version"],
                    "snapshot_id":digest([self.prefix_hashes[count-1] if count else self.fingerprint,count,t]),
                    "as_of_match_time_ms":t,"through_sequence":count,"period":period,"period_time_ms":local,**state}
            self.cache[key]=result
            while len(self.cache)>64:self.cache.popitem(last=False)
            return copy.deepcopy(result)

    def prefix(self,time_ms):
        self.snapshot(time_ms)  # Enforce live watermark and clock validation.
        with self.lock:return copy.deepcopy(self.events[:bisect_right(self.times,int(time_ms))])

    def window(self,start,end,team):
        rows=[e for e in self.prefix(end) if start<event_time(self.metadata,e)<=end and e.get("team_id")==team and e.get("valid_for_statistics") is not False]
        shots=[e for e in rows if e["type"]=="shot"]
        passes=[e for e in rows if e["type"]=="pass"]
        from simulator.xg import shot_xg
        roster={p["player_id"]:p for p in self.metadata["players"]}
        estimates=[shot_xg(e,roster) for e in shots]
        return {"shots":len(shots),"xg":sum(round(e["value"]*1e6) for e in estimates)/1e6 if all(e is not None for e in estimates) else None,
                "passes":len(passes),"completed":sum(e.get("outcome")=="complete" for e in passes),
                "pressure":sum(e["type"]=="pressure" for e in rows),"turnovers":sum(e["type"]=="turnover" for e in rows),
                "event_ids":[e["event_id"] for e in rows]}
