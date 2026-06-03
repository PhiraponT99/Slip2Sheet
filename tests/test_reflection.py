from __future__ import annotations

import unittest

from expense_tracker.reflection import calculate_reflection


class ReflectionTest(unittest.TestCase):
    def test_under_budget_reflection(self) -> None:
        report = {
            "date": "2026-06-03",
            "total_expense": 50.0,
            "daily_budget": 300.0,
            "budget_status": "OK",
            "category_totals": {"food": 50.0},
            "transactions": [
                {"merchant": "Lotus's", "category": "food", "amount": 50.0},
            ],
        }

        reflection = calculate_reflection(report)

        self.assertEqual(reflection["date"], "2026-06-03")
        self.assertEqual(reflection["total_expense"], 50.0)
        self.assertEqual(reflection["transaction_count"], 1)
        self.assertEqual(reflection["reflection"]["top_category"], "food")
        self.assertEqual(reflection["reflection"]["top_merchant"], "Lotus's")
        self.assertEqual(reflection["reflection"]["budget_status"], "OK")
        self.assertEqual(
            reflection["reflection"]["message"],
            "You stayed within your daily budget today.",
        )

    def test_over_budget_reflection(self) -> None:
        report = {
            "date": "2026-06-03",
            "total_expense": 350.0,
            "daily_budget": 300.0,
            "budget_status": "OVER_BUDGET",
            "category_totals": {"food": 350.0},
            "transactions": [
                {"merchant": "Restaurant", "category": "food", "amount": 350.0},
            ],
        }

        reflection = calculate_reflection(report)

        self.assertEqual(
            reflection["reflection"]["message"],
            "You exceeded your daily budget today.",
        )

    def test_no_transactions_reflection(self) -> None:
        report = {
            "date": "2026-06-03",
            "total_expense": 0.0,
            "daily_budget": 300.0,
            "budget_status": "OK",
            "category_totals": {},
            "transactions": [],
        }

        reflection = calculate_reflection(report)

        self.assertEqual(reflection["transaction_count"], 0)
        self.assertIsNone(reflection["reflection"]["top_category"])
        self.assertIsNone(reflection["reflection"]["top_merchant"])
        self.assertEqual(
            reflection["reflection"]["message"],
            "No spending recorded today.",
        )


if __name__ == "__main__":
    unittest.main()
