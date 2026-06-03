from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from expense_tracker.goals import (
    add_goal,
    calculate_progress_percent,
    goals_report,
    list_goals,
    update_goal,
)


class GoalsTest(unittest.TestCase):
    def test_add_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "goals.json"

            goal = add_goal("Emergency Fund", 50000, 10000, path)

            self.assertEqual(goal["name"], "Emergency Fund")
            self.assertEqual(goal["target_amount"], 50000)
            self.assertEqual(goal["current_amount"], 10000)
            self.assertEqual(goal["progress_percent"], 20.0)
            self.assertEqual(list_goals(path), [goal])

    def test_update_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "goals.json"
            add_goal("Emergency Fund", 50000, 10000, path)

            goal = update_goal("Emergency Fund", 12000, path)

            self.assertEqual(goal["current_amount"], 12000)
            self.assertEqual(goal["progress_percent"], 24.0)

    def test_progress_calculation(self) -> None:
        self.assertEqual(calculate_progress_percent(117597, 15000), 12.76)
        self.assertEqual(calculate_progress_percent(0, 15000), 0.0)

    def test_empty_goals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "goals.json"

            self.assertEqual(goals_report(path), {"goals": []})

    def test_goals_sort_by_progress_descending(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "goals.json"
            add_goal("Debt Payoff", 100000, 10000, path)
            add_goal("Emergency Fund", 50000, 20000, path)

            goals = list_goals(path)

            self.assertEqual([goal["name"] for goal in goals], [
                "Emergency Fund",
                "Debt Payoff",
            ])


if __name__ == "__main__":
    unittest.main()
