from __future__ import annotations

import unittest
from unittest.mock import patch

from expense_tracker.summary import (
    build_budget_overview,
    build_summary_values,
    calculate_summary,
    is_month_tab,
)


class SummaryTest(unittest.TestCase):
    def test_month_tab_detection(self) -> None:
        self.assertTrue(is_month_tab("2026-06"))
        self.assertFalse(is_month_tab("Summary"))
        self.assertFalse(is_month_tab("2026-6"))
        self.assertFalse(is_month_tab("2026-06-extra"))

    def test_calculate_summary_from_monthly_rows(self) -> None:
        rows_by_month = {
            "2026-06": [
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
                ],
                ["2026-06-01", "08:00", "Cafe", "food", "45", "", "", "", "", "", ""],
                ["2026-06-02", "09:00", "Taxi", "transport", "120.50", "", "", "", "", "", ""],
                ["2026-06-03", "10:00", "Water", "utilities", "30", "", "", "", "", "", ""],
                ["2026-06-04", "11:00", "Book", "other", "99", "", "", "", "", "", ""],
                ["2026-06-05", "12:00", "Tea", "drink", "40", "", "", "", "", "", ""],
                ["2026-06-05", "12:30", "Tea", "drink", "40", "", "", "", "DUPLICATE_SKIPPED", "", ""],
            ],
            "2026-07": [
                ["Date", "Time", "Merchant", "Category", "Amount"],
                ["2026-07-01", "08:00", "Rice", "food", "60"],
                ["2026-07-02", "08:00", "Bad", "food", "not-a-number"],
            ],
        }

        summary = calculate_summary(rows_by_month)

        self.assertEqual(summary["total_expense"], 394.5)
        self.assertEqual(summary["category_totals"]["food"], 105.0)
        self.assertEqual(summary["category_totals"]["transport"], 120.5)
        self.assertEqual(summary["category_totals"]["utilities"], 30.0)
        self.assertEqual(summary["category_totals"]["other"], 139.0)
        self.assertEqual(summary["monthly_totals"], {
            "2026-06": 334.5,
            "2026-07": 60.0,
        })

    def test_build_summary_values_sorts_months(self) -> None:
        summary = {
            "total_expense": 30.0,
            "category_totals": {
                "food": 10.0,
                "transport": 0.0,
                "utilities": 0.0,
                "other": 20.0,
            },
            "monthly_totals": {
                "2026-07": 20.0,
                "2026-06": 10.0,
            },
        }

        values = build_summary_values(summary)

        self.assertEqual(values[:8], [
            ["Metric", "Value"],
            ["Total Expense", 30.0],
            ["Food Expense", 10.0],
            ["Transport Expense", 0.0],
            ["Utilities Expense", 0.0],
            ["Other Expense", 20.0],
            [],
            ["Month", "Total Expense"],
        ])
        self.assertEqual(values[8:], [["2026-06", 10.0], ["2026-07", 20.0]])

    def test_budget_overview_uses_current_month_total(self) -> None:
        with patch.dict(
            "os.environ",
            {"DAILY_BUDGET": "300", "MONTHLY_BUDGET": "1000"},
        ):
            overview = build_budget_overview(
                {
                    "monthly_totals": {
                        "2026-06": 850.0,
                    }
                },
                current_month="2026-06",
            )

        self.assertEqual(overview["daily_budget"], 300.0)
        self.assertEqual(overview["monthly_budget"], 1000.0)
        self.assertEqual(overview["current_month_expense"], 850.0)
        self.assertEqual(overview["remaining_monthly_budget"], 150.0)
        self.assertEqual(overview["budget_status"], "WARNING")

    def test_build_summary_values_includes_budget_overview_when_present(self) -> None:
        summary = {
            "total_expense": 30.0,
            "category_totals": {
                "food": 10.0,
                "transport": 0.0,
                "utilities": 0.0,
                "other": 20.0,
            },
            "monthly_totals": {"2026-06": 30.0},
            "budget_overview": {
                "daily_budget": 300.0,
                "monthly_budget": 9000.0,
                "current_month_expense": 30.0,
                "remaining_monthly_budget": 8970.0,
                "budget_status": "OK",
            },
        }

        values = build_summary_values(summary)

        self.assertIn(["Budget Overview", ""], values)
        self.assertIn(["Daily Budget", 300.0], values)
        self.assertIn(["Budget Status", "OK"], values)

    def test_calculate_summary_uses_mapped_category(self) -> None:
        rows_by_month = {
            "2026-06": [
                ["Date", "Time", "Merchant", "Category", "Amount"],
                ["2026-06-01", "08:00", "Lotus's", "other", "50"],
            ],
        }

        with (
            patch("expense_tracker.summary.normalize_merchant", side_effect=lambda merchant: merchant),
            patch("expense_tracker.summary.lookup_category", return_value="food"),
        ):
            summary = calculate_summary(rows_by_month)

        self.assertEqual(summary["category_totals"]["food"], 50.0)
        self.assertEqual(summary["category_totals"]["other"], 0.0)


if __name__ == "__main__":
    unittest.main()
