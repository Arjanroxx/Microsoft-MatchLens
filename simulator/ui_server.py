"""Local UI bridge: static Replay Studio plus authoritative prefix statistics.

Run: python -m simulator.ui_server --input data/examples/offside-match
This is a localhost development tool, not an authenticated production service.
"""
import argparse
import json
import math
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from simulator.clock import event_time, elapsed, total_duration
from simulator.generate import validate
from simulator.statistics import calculate_statistics


class MatchView:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.metadata = json.loads((self.path / "metadata.json").read_text(encoding="utf-8"))
        self.events = [json.loads(line) for line in (self.path / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        validate(self.metadata, self.events)

    def state(self, time_ms):
        if not math.isfinite(time_ms) or not 0 <= time_ms <= total_duration(self.metadata):
            raise ValueError("time_ms must be within this match's replay duration")
        time_ms = int(time_ms)
        visible = [e for e in self.events if event_time(self.metadata, e) <= time_ms]
        period = visible[-1]["period"] if visible else 1
        local = time_ms - elapsed(self.metadata, period, 0)
        statistics = calculate_statistics(self.metadata, visible, (period, local))
        return {"match_id": self.metadata["match_id"], "schema_version": self.metadata["schema_version"],
                "as_of_match_time_ms": time_ms, "through_sequence": visible[-1]["sequence"] if visible else 0,
                "period": period, "period_time_ms": local, **statistics}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, view, **kwargs):
        self.view = view
        super().__init__(*args, directory=str(Path(__file__).resolve().parents[1]/"frontend"), **kwargs)

    def payload(self, body, status=200, content_type="application/json; charset=utf-8"):
        raw = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/api/state":
            try:
                query = parse_qs(parsed.query)
                if set(query) != {"time_ms"} or len(query["time_ms"]) != 1:
                    raise ValueError("Supply exactly one time_ms parameter")
                self.payload(self.view.state(float(query["time_ms"][0])))
            except (ValueError, KeyError) as error:
                self.payload({"error": str(error)}, 400)
        elif parsed.path in ("/data/metadata.json", "/api/metadata"):
            self.payload(self.view.metadata)
        elif parsed.path in ("/data/events.jsonl", "/api/events"):
            self.payload("".join(json.dumps(e)+"\n" for e in self.view.events), content_type="application/x-ndjson; charset=utf-8")
        elif parsed.path.startswith("/api/") or parsed.path.startswith("/data/"):
            self.payload({"error": "Unknown endpoint"}, 404)
        else:
            super().do_GET()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    try:
        view = MatchView(args.input)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, view=view))
    print(f"Replay Studio and /api/state: http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
