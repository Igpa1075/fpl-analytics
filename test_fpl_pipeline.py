"""Offline smoke tests for FPL forecast and optimization pipeline."""
import unittest
from datetime import datetime, timedelta, timezone

from fpl_forecast_baseline import forecast
from fpl_transfer_scenarios import lineup_score


class PipelineSmokeTests(unittest.TestCase):
    def test_predeadline_and_deadline_guard(self):
        now = datetime.now(timezone.utc)
        snapshot = {
            "captured_at_utc": now.isoformat(),
            "next_event_id": 10,
            "next_deadline_utc": (now + timedelta(days=1)).isoformat(),
            "fixtures": [{
                "event": 10, "finished": False, "team_h": 1, "team_a": 2,
                "team_h_difficulty": 2, "team_a_difficulty": 4,
            }],
            "bootstrap": {"events": [{"id": 10, "deadline_time": (now + timedelta(days=1)).isoformat()}], "elements": [
                {"id": 1, "web_name": "Test", "team": 1, "element_type": 3,
                 "minutes": 900, "starts": 10, "points_per_game": "5",
                 "form": "6", "status": "a", "now_cost": 75},
            ]},
        }
        result = forecast(snapshot)
        self.assertEqual(result["target_gw"], 10)
        self.assertEqual(len(result["predictions"]), 1)
        self.assertGreater(result["predictions"][0]["expected_points"], 0)
        snapshot["bootstrap"]["events"][0]["deadline_time"] = (now - timedelta(seconds=1)).isoformat()
        self.assertIsNone(forecast(snapshot))

    def test_legal_formation_and_captain_double(self):
        positions = [1, 1] + [2] * 5 + [3] * 5 + [4] * 3
        squad = [
            {"player_id": i + 1, "position_id": pos, "expected_points": float(i + 1)}
            for i, pos in enumerate(positions)
        ]
        result = lineup_score(squad)
        self.assertIsNotNone(result)
        self.assertGreater(result[0], 0)
        self.assertEqual(result[1], 15)

    def test_no_valid_formation(self):
        players = [{"player_id": i, "position_id": 3, "expected_points": 5}
                   for i in range(15)]
        self.assertIsNone(lineup_score(players))


if __name__ == "__main__":
    unittest.main()
