from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from expense_tracker.dashboard import (
    dashboard_payload,
    format_money,
    render_dashboard,
)
from expense_tracker.sheets import SheetsError


TODAY_REPORT = {
    "date": "2026-06-04",
    "total_expense": 50.0,
    "daily_budget": 300.0,
    "remaining_budget": 250.0,
    "budget_status": "OK",
    "category_totals": {"food": 50.0},
    "transactions": [{"merchant": "Lotus's", "amount": 50.0}],
}

MONTH_REPORT = {
    "month": "2026-06",
    "total_expense": 50.0,
    "monthly_budget": 9000.0,
    "remaining_budget": 8950.0,
    "budget_status": "OK",
    "category_totals": {"food": 50.0},
    "insights": {
        "top_category": "food",
        "top_category_amount": 50.0,
        "top_merchant": "Lotus's",
        "top_merchant_amount": 50.0,
        "transaction_count": 1,
        "average_transaction": 50.0,
    },
    "budget_health": {
        "monthly_budget": 9000.0,
        "days_in_month": 30,
        "current_day": 4,
        "expected_spend": 1200.0,
        "actual_spend": 50.0,
        "variance": -1150.0,
        "health_status": "GOOD",
        "health_message": "You are spending below your planned budget.",
    },
    "forecast": {
        "current_day": 4,
        "days_in_month": 30,
        "actual_spend": 50.0,
        "daily_average_so_far": 12.5,
        "projected_monthly_spend": 375.0,
        "monthly_budget": 9000.0,
        "projected_remaining_budget": 8625.0,
        "forecast_status": "UNDER_BUDGET",
    },
    "transactions": [{"merchant": "Lotus's", "amount": 50.0}],
}


class DashboardTest(unittest.TestCase):
    def setUp(self) -> None:
        self._budget_patch = patch.dict(
            "os.environ",
            {"DAILY_BUDGET": "300", "MONTHLY_BUDGET": "9000"},
        )
        self._budget_patch.start()

    def tearDown(self) -> None:
        self._budget_patch.stop()

    def test_dashboard_with_data(self) -> None:
        payload = dashboard_payload(
            today_fn=lambda: TODAY_REPORT,
            month_fn=lambda month: MONTH_REPORT,
            goals_fn=lambda: {
                "goals": [
                    {
                        "name": "Emergency Fund",
                        "target_amount": 50000,
                        "current_amount": 10000,
                        "progress_percent": 20.0,
                    }
                ]
            },
            current_date=date(2026, 6, 4),
        )

        rendered = render_dashboard(payload)

        self.assertEqual(payload["today"]["total_expense"], 50.0)
        self.assertEqual(payload["month"]["budget_health"]["health_status"], "GOOD")
        self.assertEqual(payload["forecast"]["forecast_status"], "UNDER_BUDGET")
        self.assertEqual(payload["goals"][0]["name"], "Emergency Fund")
        self.assertEqual(
            payload["reflection"]["message"],
            "You stayed within your daily budget today.",
        )
        self.assertIn("Slip2Sheet Dashboard", rendered)
        self.assertIn("Spent:", rendered)
        self.assertIn("50.00 THB", rendered)
        self.assertIn("Lotus's (50.00 THB)", rendered)
        self.assertIn("Transactions:", rendered)
        self.assertIn("Forecast", rendered)
        self.assertIn("375.00 THB", rendered)
        self.assertIn("Goals", rendered)
        self.assertIn("Emergency Fund", rendered)
        self.assertIn("20.0%", rendered)
        self.assertIn("Reflection", rendered)
        self.assertIn("You stayed within your daily budget today.", rendered)

    def test_dashboard_without_data(self) -> None:
        payload = dashboard_payload(
            today_fn=lambda: (_ for _ in ()).throw(SheetsError("sheet not found")),
            month_fn=lambda month: (_ for _ in ()).throw(SheetsError("sheet not found")),
            goals_fn=lambda: {"goals": []},
            current_date=date(2026, 6, 4),
        )

        rendered = render_dashboard(payload)

        self.assertEqual(payload["today"]["total_expense"], 0.0)
        self.assertEqual(payload["month"]["total_expense"], 0.0)
        self.assertEqual(payload["insights"]["transaction_count"], 0)
        self.assertEqual(payload["forecast"]["projected_monthly_spend"], 0.0)
        self.assertIn("None (0.00 THB)", rendered)
        self.assertIn("Average Spend:", rendered)
        self.assertIn("No goals yet", rendered)
        self.assertIn("No spending recorded today.", rendered)

    def test_json_payload_shape(self) -> None:
        payload = dashboard_payload(
            today_fn=lambda: TODAY_REPORT,
            month_fn=lambda month: MONTH_REPORT,
            current_date=date(2026, 6, 4),
        )

        self.assertEqual(
            set(payload),
            {"today", "month", "insights", "forecast", "goals", "reflection"},
        )
        self.assertEqual(payload["insights"]["top_category"], "food")
        self.assertEqual(payload["forecast"]["projected_monthly_spend"], 375.0)

    def test_format_money(self) -> None:
        self.assertEqual(format_money(50), "50.00 THB")
        self.assertEqual(format_money("36.5"), "36.50 THB")
        self.assertEqual(format_money(None), "0.00 THB")


if __name__ == "__main__":
    unittest.main()
