"""Minimal deterministic tests for legal FPL starting XI selection."""
import unittest
from fpl_backtest_hold_baseline import choose


class LineupTests(unittest.TestCase):
    def setUp(self):
        self.positions = dict(zip(range(1, 16), [1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4]))
        self.squad = list(self.positions)

    def test_legal_xi_and_formation(self):
        points = {pid: pid for pid in self.squad}
        lineup = choose(self.squad, self.positions, points)
        self.assertEqual(len(lineup), 11)
        self.assertEqual(len(set(lineup)), 11)
        self.assertEqual(sum(self.positions[p] == 1 for p in lineup), 1)
        self.assertGreaterEqual(sum(self.positions[p] == 2 for p in lineup), 3)
        self.assertGreaterEqual(sum(self.positions[p] == 3 for p in lineup), 2)
        self.assertGreaterEqual(sum(self.positions[p] == 4 for p in lineup), 1)

    def test_deterministic_without_prior_form(self):
        self.assertEqual(choose(self.squad, self.positions, {}),
                         choose(self.squad, self.positions, {}))


if __name__ == "__main__":
    unittest.main()
