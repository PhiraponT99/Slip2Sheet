from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from expense_tracker.reflection_history import (
    calculate_reflection_history,
    summarize_reflection_records,
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


class ReflectionHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._budget_patch = patch.dict(
            "os.environ",
            {"DAILY_BUDGET": "300", "MONTHLY_BUDGET": "9000"},
        )
        self._budget_patch.start()

    def tearDown(self) -> None:
        self._budget_patch.stop()

    def test_multiple_ok_days(self) -> None:
        history = calculate_reflection_history(
            rows_for(
                ("2026-06-01", "Lotus's", "food", 50.0),
                ("2026-06-02", "Cafe", "drink", 60.0),
            ),
            date(2026, 6, 2),
        )

        self.assertEqual(history["summary"]["ok_days"], 2)
        self.assertEqual(history["summary"]["over_budget_days"], 0)
        self.assertEqual(history["summary"]["no_spending_days"], 0)

    def test_over_budget_days(self) -> None:
        history = calculate_reflection_history(
            rows_for(("2026-06-01", "Restaurant", "food", 350.0)),
            date(2026, 6, 1),
        )

        self.assertEqual(history["summary"]["ok_days"], 0)
        self.assertEqual(history["summary"]["over_budget_days"], 1)
        self.assertEqual(
            history["records"][0]["message"],
            "You exceeded your daily budget today.",
        )

    def test_no_transaction_days(self) -> None:
        history = calculate_reflection_history([], date(2026, 6, 3))

        self.assertEqual(len(history["records"]), 3)
        self.assertEqual(history["summary"]["no_spending_days"], 3)
        self.assertEqual(history["summary"]["total_days_with_transactions"], 0)

    def test_mixed_month_summary(self) -> None:
        history = calculate_reflection_history(
            rows_for(
                ("2026-06-01", "Lotus's", "food", 50.0),
                ("2026-06-02", "Restaurant", "food", 350.0),
                ("2026-06-04", "Cafe", "drink", 40.0),
            ),
            date(2026, 6, 4),
        )

        self.assertEqual(history["month"], "2026-06")
        self.assertEqual(history["summary"], {
            "ok_days": 2,
            "over_budget_days": 1,
            "no_spending_days": 1,
            "total_days_with_transactions": 3,
        })
        self.assertEqual(history["records"][0]["top_category"], "food")
        self.assertEqual(history["records"][2]["message"], "No spending recorded today.")

    def test_summarize_reflection_records(self) -> None:
        summary = summarize_reflection_records(
            [
                {
                    "transaction_count": 1,
                    "message": "You stayed within your daily budget today.",
                },
                {
                    "transaction_count": 1,
                    "message": "You exceeded your daily budget today.",
                },
                {"transaction_count": 0, "message": "No spending recorded today."},
            ]
        )

        self.assertEqual(summary["ok_days"], 1)
        self.assertEqual(summary["over_budget_days"], 1)
        self.assertEqual(summary["no_spending_days"], 1)
        self.assertEqual(summary["total_days_with_transactions"], 2)


if __name__ == "__main__":
    unittest.main()
