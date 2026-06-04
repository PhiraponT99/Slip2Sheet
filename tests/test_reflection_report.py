from __future__ import annotations

from datetime import date
import unittest

from expense_tracker.reflection_report import overall_message, reflection_report


DAILY_OK = {
    "date": "2026-06-04",
    "total_expense": 50.0,
    "transaction_count": 1,
    "reflection": {
        "top_category": "food",
        "top_merchant": "Lotus's",
        "budget_status": "OK",
        "message": "You stayed within your daily budget today.",
    },
}
DAILY_OVER = {
    **DAILY_OK,
    "total_expense": 350.0,
    "reflection": {
        **DAILY_OK["reflection"],
        "budget_status": "OVER_BUDGET",
        "message": "You exceeded your daily budget today.",
    },
}
DAILY_NONE = {
    "date": "2026-06-04",
    "total_expense": 0.0,
    "transaction_count": 0,
    "reflection": {
        "top_category": None,
        "top_merchant": None,
        "budget_status": "OK",
        "message": "No spending recorded today.",
    },
}
WEEK_OK = {
    "week_start": "2026-06-01",
    "week_end": "2026-06-07",
    "total_expense": 250.0,
    "transaction_count": 5,
    "total_days_with_transactions": 3,
    "spending_day_ratio": 0.43,
    "summary": {"ok_days": 3, "over_budget_days": 0, "no_spending_days": 4},
    "message": "You stayed within budget on all spending days this week.",
}
WEEK_OVER = {
    **WEEK_OK,
    "summary": {"ok_days": 1, "over_budget_days": 2, "no_spending_days": 4},
    "message": "You exceeded your budget on several spending days this week.",
}
MONTH_OK = {
    "month": "2026-06",
    "days_in_month": 30,
    "total_expense": 1250.0,
    "transaction_count": 18,
    "total_days_with_transactions": 12,
    "spending_day_ratio": 0.4,
    "summary": {"ok_days": 10, "over_budget_days": 2, "no_spending_days": 18},
    "message": "You stayed within budget on most spending days this month.",
}
MONTH_OVER = {
    **MONTH_OK,
    "summary": {"ok_days": 2, "over_budget_days": 10, "no_spending_days": 18},
    "message": "You exceeded your budget on several spending days this month.",
}
WEEK_NONE = {
    **WEEK_OK,
    "total_expense": 0.0,
    "transaction_count": 0,
    "total_days_with_transactions": 0,
    "spending_day_ratio": 0.0,
    "summary": {"ok_days": 0, "over_budget_days": 0, "no_spending_days": 7},
    "message": "No spending recorded this week.",
}
MONTH_NONE = {
    **MONTH_OK,
    "total_expense": 0.0,
    "transaction_count": 0,
    "total_days_with_transactions": 0,
    "spending_day_ratio": 0.0,
    "summary": {"ok_days": 0, "over_budget_days": 0, "no_spending_days": 30},
    "message": "No spending recorded this month.",
}


class ReflectionReportTest(unittest.TestCase):
    def test_all_under_budget(self) -> None:
        report = reflection_report(
            current_date=date(2026, 6, 4),
            daily_fn=lambda: DAILY_OK,
            weekly_fn=lambda: WEEK_OK,
            monthly_fn=lambda: MONTH_OK,
        )

        self.assertEqual(report["date"], "2026-06-04")
        self.assertEqual(report["daily"]["top_category"], "food")
        self.assertEqual(report["weekly"]["spending_day_ratio"], 0.43)
        self.assertEqual(report["monthly"]["month"], "2026-06")
        self.assertEqual(report["overall_message"], "Your spending is currently under control.")

    def test_daily_over_budget_only(self) -> None:
        message = overall_message(
            {
                "transaction_count": 1,
                "message": "You exceeded your daily budget today.",
            },
            WEEK_OK,
            MONTH_OK,
        )

        self.assertEqual(
            message,
            "Today was over budget, but your weekly and monthly spending are still manageable.",
        )

    def test_weekly_warning(self) -> None:
        message = overall_message(
            {"transaction_count": 1, "message": "You stayed within your daily budget today."},
            WEEK_OVER,
            MONTH_OK,
        )

        self.assertEqual(
            message,
            "This week needs attention, but your monthly spending is still manageable.",
        )

    def test_monthly_over_budget(self) -> None:
        message = overall_message(
            {"transaction_count": 1, "message": "You stayed within your daily budget today."},
            WEEK_OVER,
            MONTH_OVER,
        )

        self.assertEqual(
            message,
            "Your monthly spending is over budget and needs attention.",
        )

    def test_no_transactions(self) -> None:
        report = reflection_report(
            current_date=date(2026, 6, 4),
            daily_fn=lambda: DAILY_NONE,
            weekly_fn=lambda: WEEK_NONE,
            monthly_fn=lambda: MONTH_NONE,
        )

        self.assertEqual(report["overall_message"], "No spending recorded yet.")


if __name__ == "__main__":
    unittest.main()
