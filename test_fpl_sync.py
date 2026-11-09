"""Offline regression tests for public squad synchronization."""
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import fpl_sync


class TestPublishedPicks(unittest.TestCase):
    def test_published_gw_advances_despite_unfinished_flag(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "picks.json").write_text(json.dumps({"entry_history": {"event": 9}}))
            bootstrap = {"events": [
                {"id": 9, "deadline_time": "2026-10-01T00:00:00Z", "finished": True},
                {"id": 10, "deadline_time": "2026-11-01T00:00:00Z", "finished": False},
                {"id": 11, "deadline_time": "2099-11-21T00:00:00Z", "finished": False},
            ]}
            history = {"current": [{"event": 10, "points": 59}]}
            picks = {"entry_history": {"event": 10}, "picks": [{"element": i} for i in range(15)]}
            responses = {
                "/bootstrap-static/": bootstrap, "/fixtures/": [],
                f"/entry/{fpl_sync.ENTRY_ID}/": {},
                f"/entry/{fpl_sync.ENTRY_ID}/history/": history,
                f"/entry/{fpl_sync.ENTRY_ID}/event/10/picks/": picks,
            }
            with patch.object(fpl_sync, "OUT", directory), patch.object(
                fpl_sync, "fetch", side_effect=lambda endpoint: responses[endpoint]
            ):
                fpl_sync.main()
            self.assertEqual(json.loads((directory / "picks.json").read_text())["entry_history"]["event"], 10)
            status = json.loads((directory / "sync_status.json").read_text())
            self.assertEqual(status["last_finished_gw"], 9)
            self.assertEqual(status["latest_public_picks_gw"], 10)
            self.assertEqual(status["latest_history_gw"], 10)


if __name__ == "__main__":
    unittest.main()
