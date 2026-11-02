"""Send a validated synthetic match to a --live backend using event-time pacing."""
import argparse
import json
import math
from pathlib import Path
import time
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

from simulator.generate import validate
from simulator.clock import event_time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--url',default='http://127.0.0.1:8082')
    p.add_argument('--speed',type=float,default=1)
    p.add_argument('--no-delay',action='store_true')
    p.add_argument('--after-sequence',type=int,default=0)
    args=p.parse_args()
    if not math.isfinite(args.speed) or args.speed<=0:p.error('Speed must be positive and finite')
    metadata=json.loads((args.input/'metadata.json').read_text(encoding='utf-8'))
    rows=[json.loads(s) for s in (args.input/'events.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
    validate(metadata,rows)
    if not 0<=args.after_sequence<=len(rows):p.error('Invalid resume sequence')
    base=event_time(metadata,rows[args.after_sequence]) if args.after_sequence<len(rows) else 0
    started=time.monotonic()
    for event in rows[args.after_sequence:]:
        delay=(event_time(metadata,event)-base)/1000/args.speed-(time.monotonic()-started)
        if not args.no_delay and delay>0:time.sleep(delay)
        request=Request(args.url.rstrip('/')+'/api/events',json.dumps(event).encode(),{'Content-Type':'application/json'})
        for attempt in range(3):
            try:
                with urlopen(request,timeout=30) as r:ack=json.load(r)
                break
            except HTTPError as error:
                if error.code<500 and error.code!=429:raise
                if attempt==2:raise
                time.sleep(2**attempt)
            except URLError:
                if attempt==2:raise
                time.sleep(2**attempt)
        if event['sequence']%100==0 or event is rows[-1]:print(json.dumps(ack),flush=True)


if __name__=='__main__':main()
