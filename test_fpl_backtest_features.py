import unittest
from fpl_backtest_features import build


class LaggedFeaturesTest(unittest.TestCase):
    def test_future_fixture_does_not_change_past(self):
        original = {"1": [
            {"gw": 1, "fixture": 1, "minutes": 90, "total_points": 6},
            {"gw": 2, "fixture": 2, "minutes": 90, "total_points": 3},
        ]}
        modified = {"1": original["1"] + [
            {"gw": 5, "fixture": 5, "minutes": 90, "total_points": 50}
        ]}
        a = build(original)
        b = build(modified)
        for gw in range(1, 6):
            self.assertEqual(a["1"][str(gw)], b["1"][str(gw)])
        self.assertEqual(a["1"]["1"]["prior_fixture_rows"], 0)
        self.assertEqual(a["1"]["2"]["prior_points"], 6)
        self.assertEqual(a["1"]["3"]["prior_points"], 9)

    def test_same_gw_double_fixture_excluded(self):
        records = {"1": [
            {"gw": 3, "fixture": 31, "minutes": 90, "total_points": 8},
            {"gw": 3, "fixture": 32, "minutes": 90, "total_points": 7},
        ]}
        f = build(records)
        self.assertEqual(f["1"]["3"]["prior_points"], 0)
        self.assertEqual(f["1"]["4"]["prior_points"], 15)
        self.assertIsNone(f["1"]["4"]["price_before_deadline"])


if __name__ == "__main__":
    unittest.main()
