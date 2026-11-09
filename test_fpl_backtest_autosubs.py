import unittest
from fpl_backtest_autosubs import resolve


class AutoSubTests(unittest.TestCase):
    def setUp(self):
        self.positions = dict(zip(range(1, 16), [1, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 1, 2, 3, 4]))
        self.lineup = list(range(1, 16))
        self.minutes = {p: 90 for p in self.lineup}
        self.points = {p: 2 for p in self.lineup}

    def test_no_absences(self):
        r = resolve(self.lineup, self.positions, self.minutes, self.points, 9, 10)
        self.assertEqual(r["points"], 24)
        self.assertEqual(r["autosubs"], [])

    def test_goalkeeper_autosub(self):
        self.minutes[1] = 0
        r = resolve(self.lineup, self.positions, self.minutes, self.points, 9, 10)
        self.assertEqual(r["autosubs"], [{"out": 1, "in": 12}])

    def test_captain_fallback(self):
        self.minutes[9] = 0
        r = resolve(self.lineup, self.positions, self.minutes, self.points, 9, 10)
        self.assertEqual(r["captain_scoring"], 10)
        self.assertEqual(r["points"], 24)

    def test_defender_minimum(self):
        self.minutes[2] = 0
        self.minutes[3] = 0
        self.minutes[4] = 0
        r = resolve(self.lineup, self.positions, self.minutes, self.points, 9, 10)
        self.assertIn(13, r["final_xi"])
        self.assertNotIn(14, r["final_xi"])
        self.assertNotIn(15, r["final_xi"])
        self.assertEqual(len(r["final_xi"]), 9)

    def test_zero_minutes_bench_not_subbed(self):
        self.minutes[4] = 0
        self.minutes[13] = 0
        r = resolve(self.lineup, self.positions, self.minutes, self.points, 9, 10)
        self.assertNotIn(13, r["final_xi"])


if __name__ == "__main__":
    unittest.main()
