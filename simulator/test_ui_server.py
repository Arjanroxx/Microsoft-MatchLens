import functools
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from simulator.statistics import calculate_statistics
from simulator.ui_server import Handler, MatchView


class UIStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.view = MatchView(Path(__file__).resolve().parents[1]/"data/examples/offside-match")

    def test_state_is_a_prefix_and_rewinds_without_future_score(self):
        view = self.view
        full = view.state(view.metadata["match_duration_ms"])
        start = view.state(0)
        self.assertEqual(start["teams"]["home"]["goals"], 0)
        self.assertEqual(start["teams"]["away"]["goals"], 0)
        self.assertEqual(start["players"]["home-07"]["minutes_played_ms"], 0)
        self.assertEqual(full["teams"], calculate_statistics(view.metadata, view.events)["teams"])
        self.assertGreater(full["through_sequence"], start["through_sequence"])
        self.assertEqual(view.state(0), start)

    def test_api_and_reducer_match_at_offside_and_substitution_boundaries(self):
        for event in self.view.events:
            if event["type"] not in ("offside", "substitution", "period_start"):
                continue
            when = event["match_time_ms"]
            for time in (max(0, when-1), when):
                state = self.view.state(time)
                expected = calculate_statistics(self.view.metadata, self.view.events,
                                                (state["period"], state["period_time_ms"]))
                self.assertEqual(state["players"], expected["players"])
                self.assertEqual(state["lineups"], expected["lineups"])

    def test_unknown_and_nonfinite_times_fail(self):
        for invalid in (-1, float("inf"), float("nan"), self.view.metadata["match_duration_ms"]+1):
            with self.assertRaises(ValueError): self.view.state(invalid)

    def test_legacy_matches_without_actual_duration_still_support_live_state(self):
        base = Path(__file__).resolve().parents[1]/"data/examples"
        for name in ("short-match", "substitutions-match"):
            view = MatchView(base/name)
            self.assertEqual(view.state(0)["teams"]["home"]["goals"], 0)
            final = view.state(view.metadata["period_duration_ms"]*2)
            self.assertEqual(final["player_rating_model"]["version"], "matchlens-event-rating-v1")

    def test_http_routes_and_invalid_request(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, view=self.view))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(root+"/api/state?time_ms=0") as response:
                self.assertEqual(json.load(response)["match_id"], self.view.metadata["match_id"])
            with urlopen(root+"/data/metadata.json") as response:
                self.assertEqual(json.load(response), self.view.metadata)
            with urlopen(root+"/") as response:
                self.assertIn(b"MatchLens", response.read())
            for route, status in (("/api/state", 400), ("/api/state?time_ms=nan", 400),
                                  ("/api/state?time_ms=1&time_ms=2", 400), ("/api/unknown", 404)):
                with self.assertRaises(HTTPError) as error: urlopen(root+route)
                self.assertEqual(error.exception.code, status)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
