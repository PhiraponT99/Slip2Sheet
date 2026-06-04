from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from expense_tracker.weekly_reflection import (
    calculate_weekly_reflection,
    week_bounds,
    weekly_message,
)


HEADER = [
    "Date",
    "Time",
    "Merchant",
    "Category",
    "Amount",
    "OriginalAmount",
    "Discount",
    "PaymentMethod",
    "Note",
    "SourceImage",
    "CreatedAt",
    "TransactionKey",
]


def rows_for(*entries: tuple[str, str, str, float]) -> list[list[str]]:
    rows = [HEADER]
    for entry_date, merchant, category, amount in entries:
        rows.append(
            [
                entry_date,
                "10:00",
                merchant,
                category,
                str(amount),
                "",
                "",
                "",
                "",
                "slip.jpg",
                "",
                f"{entry_date}|10:00|{merchant}|{amount}",
            ]
        )
    return rows


class WeeklyReflectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._budget_patch = patch.dict(
            "os.environ",
            {"DAILY_BUDGET": "300", "MONTHLY_BUDGET": "9000"},
        )
        self._budget_patch.start()

    def tearDown(self) -> None:
        self._budget_patch.stop()

    def test_all_days_under_budget(self) -> None:
        report = calculate_weekly_reflection(
            {
                "2026-06": rows_for(
                    ("2026-06-01", "Lotus's", "food", 50.0),
                    ("2026-06-03", "Cafe", "drink", 40.0),
                )
            },
            date(2026, 6, 4),
        )

        self.assertEqual(report["week_start"], "2026-06-01")
        self.assertEqual(report["week_end"], "2026-06-07")
        self.assertEqual(report["total_expense"], 90.0)
        self.assertEqual(report["transaction_count"], 2)
        self.assertEqual(report["top_category"], "food")
        self.assertEqual(report["top_merchant"], "Lotus's")
        self.assertEqual(report["total_days_with_transactions"], 2)
        self.assertEqual(report["spending_day_ratio"], 0.29)
        self.assertEqual(report["summary"], {
            "ok_days": 2,
            "over_budget_days": 0,
            "no_spending_days": 5,
        })
        self.assertEqual(
            report["message"],
            "You stayed within budget on all spending days this week.",
        )

    def test_one_spending_day_under_budget(self) -> None:
        report = calculate_weekly_reflection(
            {
                "2026-06": rows_for(
                    ("2026-06-01", "Lotus's", "food", 50.0),
                )
            },
            date(2026, 6, 4),
        )

        self.assertEqual(report["total_days_with_transactions"], 1)
        self.assertEqual(report["spending_day_ratio"], 0.14)
        self.assertEqual(report["summary"]["ok_days"], 1)
        self.assertEqual(report["summary"]["no_spending_days"], 6)
        self.assertEqual(
            report["message"],
            "You stayed within budget on all spending days this week.",
        )

    def test_mixed_budget_status(self) -> None:
        report = calculate_weekly_reflection(
            {
                "2026-06": rows_for(
                    ("2026-06-01", "Lotus's", "food", 50.0),
                    ("2026-06-02", "Restaurant", "food", 350.0),
                    ("2026-06-03", "Cafe", "drink", 40.0),
                )
            },
            date(2026, 6, 4),
        )

        self.assertEqual(report["summary"]["ok_days"], 2)
        self.assertEqual(report["summary"]["over_budget_days"], 1)
        self.assertEqual(report["total_days_with_transactions"], 3)
        self.assertEqual(report["spending_day_ratio"], 0.43)
        self.assertEqual(
            report["message"],
            "You stayed within budget for most spending days this week.",
        )

    def test_mostly_over_budget(self) -> None:
        report = calculate_weekly_reflection(
            {
                "2026-06": rows_for(
                    ("2026-06-01", "Lotus's", "food", 50.0),
                    ("2026-06-02", "Restaurant", "food", 350.0),
                    ("2026-06-03", "Market", "food", 400.0),
                )
            },
            date(2026, 6, 4),
        )

        self.assertEqual(report["summary"]["ok_days"], 1)
        self.assertEqual(report["summary"]["over_budget_days"], 2)
        self.assertEqual(
            report["message"],
            "You exceeded your budget on several spending days this week.",
        )

    def test_no_transactions(self) -> None:
        report = calculate_weekly_reflection({"2026-06": []}, date(2026, 6, 4))

        self.assertEqual(report["total_expense"], 0.0)
        self.assertEqual(report["transaction_count"], 0)
        self.assertIsNone(report["top_category"])
        self.assertIsNone(report["top_merchant"])
        self.assertEqual(report["total_days_with_transactions"], 0)
        self.assertEqual(report["spending_day_ratio"], 0.0)
        self.assertEqual(report["summary"]["no_spending_days"], 7)
        self.assertEqual(report["message"], "No spending recorded this week.")

    def test_week_bounds(self) -> None:
        self.assertEqual(week_bounds(date(2026, 6, 4)), (
            date(2026, 6, 1),
            date(2026, 6, 7),
        ))

    def test_weekly_message(self) -> None:
        self.assertEqual(weekly_message(0, 0, 0, 0), "No spending recorded this week.")
        self.assertEqual(
            weekly_message(2, 2, 0, 2),
            "You stayed within budget on all spending days this week.",
        )
        self.assertEqual(
            weekly_message(3, 2, 1, 3),
            "You stayed within budget for most spending days this week.",
        )
        self.assertEqual(
            weekly_message(3, 1, 2, 3),
            "You exceeded your budget on several spending days this week.",
        )


if __name__ == "__main__":
    unittest.main()
