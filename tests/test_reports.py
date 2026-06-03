from __future__ import annotations

import unittest
from unittest.mock import patch

from expense_tracker.reports import (
    calculate_daily_report,
    calculate_month_report,
    rows_to_transactions,
)


ROWS = [
    [
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
    ],
    [
        "2026-06-03",
        "10:00",
        "Rice Shop",
        "food",
        "65",
        "65",
        "",
        "PromptPay",
        "",
        "slip1.jpg",
        "2026-06-03T10:01:00",
        "2026-06-03|10:00|Rice Shop|65.0",
    ],
    [
        "2026-06-03",
        "14:19",
        "Cafe",
        "drink",
        "36.0",
        "45",
        "9",
        "",
        "discount",
        "slip2.jpg",
        "2026-06-03T14:20:00",
        "2026-06-03|14:19|Cafe|36.0",
    ],
    [
        "2026-06-04",
        "09:00",
        "Taxi",
        "transport",
        "120.50",
        "",
        "",
        "",
        "",
        "slip3.jpg",
        "2026-06-04T09:01:00",
        "2026-06-04|09:00|Taxi|120.5",
    ],
    [
        "2026-06-03",
        "14:19",
        "Cafe",
        "drink",
        "36.0",
        "45",
        "9",
        "",
        "DUPLICATE_SKIPPED",
        "slip2-copy.jpg",
        "2026-06-03T14:21:00",
        "2026-06-03|14:19|Cafe|36.0",
    ],
    ["2026-06-04", "10:00", "Bad", "food", "not-a-number"],
]


class ReportsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._daily_budget_patch = patch.dict(
            "os.environ",
            {"DAILY_BUDGET": "300", "MONTHLY_BUDGET": "9000"},
        )
        self._daily_budget_patch.start()

    def tearDown(self) -> None:
        self._daily_budget_patch.stop()

    def test_rows_to_transactions_maps_schema_b_rows(self) -> None:
        with patch("expense_tracker.reports.normalize_merchant", side_effect=lambda merchant: merchant):
            transactions = rows_to_transactions(ROWS)

        self.assertEqual(len(transactions), 3)
        self.assertEqual(transactions[0]["date"], "2026-06-03")
        self.assertEqual(transactions[0]["amount"], 65.0)
        self.assertEqual(transactions[0]["payment_method"], "PromptPay")
        self.assertIsNone(transactions[0]["discount"])

    def test_calculate_daily_report_filters_date_and_groups_category(self) -> None:
        with patch("expense_tracker.reports.normalize_merchant", side_effect=lambda merchant: merchant):
            report = calculate_daily_report(ROWS, "2026-06-03")

        self.assertEqual(report["date"], "2026-06-03")
        self.assertEqual(report["total_expense"], 101.0)
        self.assertEqual(report["daily_budget"], 300.0)
        self.assertEqual(report["remaining_budget"], 199.0)
        self.assertEqual(report["budget_status"], "OK")
        self.assertEqual(report["category_totals"], {"food": 65.0, "drink": 36.0})
        self.assertEqual(len(report["transactions"]), 2)

    def test_calculate_month_report_filters_month_and_groups_category(self) -> None:
        with patch("expense_tracker.reports.normalize_merchant", side_effect=lambda merchant: merchant):
            report = calculate_month_report(ROWS, "2026-06")

        self.assertEqual(report["month"], "2026-06")
        self.assertEqual(report["total_expense"], 221.5)
        self.assertEqual(report["monthly_budget"], 9000.0)
        self.assertEqual(report["remaining_budget"], 8778.5)
        self.assertEqual(report["budget_status"], "OK")
        self.assertEqual(
            report["category_totals"],
            {"food": 65.0, "drink": 36.0, "transport": 120.5},
        )
        self.assertEqual(len(report["transactions"]), 3)

    def test_rows_to_transactions_applies_merchant_aliases(self) -> None:
        rows = [
            ROWS[0],
            [
                "2026-06-03",
                "10:00",
                "CP AXTRA PUBLIC COMPANY LIMITED (HEAD)",
                "food",
                "50",
            ],
        ]

        with patch("expense_tracker.reports.normalize_merchant", return_value="Lotus's"):
            transactions = rows_to_transactions(rows)

        self.assertEqual(transactions[0]["merchant"], "Lotus's")

    def test_rows_to_transactions_uses_mapped_category_for_existing_rows(self) -> None:
        rows = [
            ROWS[0],
            [
                "2026-06-03",
                "10:00",
                "Lotus's",
                "other",
                "50",
            ],
        ]

        with (
            patch("expense_tracker.reports.normalize_merchant", side_effect=lambda merchant: merchant),
            patch("expense_tracker.reports.lookup_category", return_value="food"),
        ):
            transactions = rows_to_transactions(rows)

        self.assertEqual(transactions[0]["category"], "food")


if __name__ == "__main__":
    unittest.main()
