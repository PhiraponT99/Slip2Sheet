from __future__ import annotations

import unittest

from expense_tracker.reflection_markdown import render_reflection_report_markdown


REPORT = {
    "date": "2026-06-04",
    "daily": {
        "total_expense": 50.0,
        "transaction_count": 1,
        "top_category": "food",
        "top_merchant": "Lotus's",
        "budget_status": "OK",
        "message": "You stayed within your daily budget today.",
    },
    "weekly": {
        "week_start": "2026-06-01",
        "week_end": "2026-06-07",
        "total_expense": 250.0,
        "transaction_count": 5,
        "total_days_with_transactions": 3,
        "spending_day_ratio": 0.43,
        "message": "You stayed within budget on all spending days this week.",
    },
    "monthly": {
        "month": "2026-06",
        "days_in_month": 30,
        "total_expense": 1250.0,
        "transaction_count": 18,
        "total_days_with_transactions": 12,
        "spending_day_ratio": 0.4,
        "message": "You stayed within budget on most spending days this month.",
    },
    "overall_message": "Your spending is currently under control.",
}


class ReflectionMarkdownTest(unittest.TestCase):
    def test_normal_report(self) -> None:
        markdown = render_reflection_report_markdown(REPORT)

        self.assertIn("# Slip2Sheet Reflection Report", markdown)
        self.assertIn("Date: 2026-06-04", markdown)
        self.assertIn("Top Category: food", markdown)
        self.assertIn("Top Merchant: Lotus's", markdown)
        self.assertIn("Overall", markdown)

    def test_null_top_category_top_merchant(self) -> None:
        report = {
            **REPORT,
            "daily": {
                **REPORT["daily"],
                "top_category": None,
                "top_merchant": None,
            },
        }

        markdown = render_reflection_report_markdown(report)

        self.assertIn("Top Category: -", markdown)
        self.assertIn("Top Merchant: -", markdown)

    def test_no_transaction_report(self) -> None:
        report = {
            "date": "2026-06-04",
            "daily": {
                "total_expense": 0.0,
                "transaction_count": 0,
                "top_category": None,
                "top_merchant": None,
                "message": "No spending recorded today.",
            },
            "weekly": {
                "week_start": "2026-06-01",
                "week_end": "2026-06-07",
                "total_expense": 0.0,
                "transaction_count": 0,
                "total_days_with_transactions": 0,
                "spending_day_ratio": 0.0,
                "message": "No spending recorded this week.",
            },
            "monthly": {
                "month": "2026-06",
                "total_expense": 0.0,
                "transaction_count": 0,
                "total_days_with_transactions": 0,
                "spending_day_ratio": 0.0,
                "message": "No spending recorded this month.",
            },
            "overall_message": "No spending recorded yet.",
        }

        markdown = render_reflection_report_markdown(report)

        self.assertIn("Transaction Count: 0", markdown)
        self.assertIn("Message: No spending recorded today.", markdown)
        self.assertIn("No spending recorded yet.", markdown)

    def test_markdown_contains_all_required_sections(self) -> None:
        markdown = render_reflection_report_markdown(REPORT)

        for section in (
            "# Slip2Sheet Reflection Report",
            "## Daily Reflection",
            "## Weekly Reflection",
            "## Monthly Reflection",
            "## Overall",
        ):
            self.assertIn(section, markdown)


if __name__ == "__main__":
    unittest.main()
