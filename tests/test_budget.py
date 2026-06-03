from __future__ import annotations

import unittest

from expense_tracker.budget import (
    calculate_budget_status,
    calculate_remaining_budget,
)


class BudgetTest(unittest.TestCase):
    def test_under_budget_status(self) -> None:
        self.assertEqual(calculate_budget_status(80.0, 100.0), "OK")
        self.assertEqual(calculate_remaining_budget(80.0, 100.0), 20.0)

    def test_near_budget_status(self) -> None:
        self.assertEqual(calculate_budget_status(80.01, 100.0), "WARNING")
        self.assertEqual(calculate_budget_status(100.0, 100.0), "WARNING")

    def test_over_budget_status(self) -> None:
        self.assertEqual(calculate_budget_status(100.01, 100.0), "OVER_BUDGET")
        self.assertEqual(calculate_remaining_budget(100.01, 100.0), -0.01)


if __name__ == "__main__":
    unittest.main()
