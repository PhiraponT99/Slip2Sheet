from __future__ import annotations

from datetime import date
import unittest

from expense_tracker.budget import (
    calculate_spending_forecast,
    calculate_monthly_budget_health,
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

    def test_monthly_budget_health_good(self) -> None:
        health = calculate_monthly_budget_health(
            "2026-06", 50.0, 9000.0, today=date(2026, 6, 3)
        )

        self.assertEqual(health["days_in_month"], 30)
        self.assertEqual(health["current_day"], 3)
        self.assertEqual(health["expected_spend"], 900.0)
        self.assertEqual(health["actual_spend"], 50.0)
        self.assertEqual(health["variance"], -850.0)
        self.assertEqual(health["health_status"], "GOOD")
        self.assertEqual(
            health["health_message"],
            "You are spending below your planned budget.",
        )

    def test_monthly_budget_health_on_track(self) -> None:
        health = calculate_monthly_budget_health(
            "2026-06", 1000.0, 9000.0, today=date(2026, 6, 3)
        )

        self.assertEqual(health["expected_spend"], 900.0)
        self.assertEqual(health["variance"], 100.0)
        self.assertEqual(health["health_status"], "ON_TRACK")
        self.assertEqual(
            health["health_message"],
            "You are spending within your planned budget.",
        )

    def test_monthly_budget_health_overspending(self) -> None:
        health = calculate_monthly_budget_health(
            "2026-06", 1200.0, 9000.0, today=date(2026, 6, 3)
        )

        self.assertEqual(health["expected_spend"], 900.0)
        self.assertEqual(health["variance"], 300.0)
        self.assertEqual(health["health_status"], "OVERSPENDING")
        self.assertEqual(
            health["health_message"],
            "You are spending faster than your planned budget.",
        )

    def test_monthly_budget_health_empty_month(self) -> None:
        health = calculate_monthly_budget_health(
            "2026-07", 0.0, 9300.0, today=date(2026, 7, 5)
        )

        self.assertEqual(health["expected_spend"], 1500.0)
        self.assertEqual(health["actual_spend"], 0.0)
        self.assertEqual(health["variance"], -1500.0)
        self.assertEqual(health["health_status"], "GOOD")

    def test_monthly_budget_health_february_historical_and_future(self) -> None:
        historical = calculate_monthly_budget_health(
            "2024-02", 2900.0, 2900.0, today=date(2026, 6, 3)
        )
        future = calculate_monthly_budget_health(
            "2028-02", 0.0, 2900.0, today=date(2026, 6, 3)
        )

        self.assertEqual(historical["days_in_month"], 29)
        self.assertEqual(historical["current_day"], 29)
        self.assertEqual(historical["expected_spend"], 2900.0)
        self.assertEqual(future["days_in_month"], 29)
        self.assertEqual(future["current_day"], 1)
        self.assertEqual(future["expected_spend"], 100.0)

    def test_spending_forecast_under_budget(self) -> None:
        forecast = calculate_spending_forecast(
            "2026-06", 50.0, 9000.0, today=date(2026, 6, 3)
        )

        self.assertEqual(forecast["current_day"], 3)
        self.assertEqual(forecast["days_in_month"], 30)
        self.assertEqual(forecast["actual_spend"], 50.0)
        self.assertEqual(forecast["daily_average_so_far"], 16.67)
        self.assertEqual(forecast["projected_monthly_spend"], 500.0)
        self.assertEqual(forecast["projected_remaining_budget"], 8500.0)
        self.assertEqual(forecast["forecast_status"], "UNDER_BUDGET")

    def test_spending_forecast_on_track(self) -> None:
        forecast = calculate_spending_forecast(
            "2026-06", 800.0, 9000.0, today=date(2026, 6, 3)
        )

        self.assertEqual(forecast["projected_monthly_spend"], 8000.0)
        self.assertEqual(forecast["forecast_status"], "ON_TRACK")

    def test_spending_forecast_over_budget(self) -> None:
        forecast = calculate_spending_forecast(
            "2026-06", 1000.0, 9000.0, today=date(2026, 6, 3)
        )

        self.assertEqual(forecast["projected_monthly_spend"], 10000.0)
        self.assertEqual(forecast["forecast_status"], "OVER_BUDGET")

    def test_spending_forecast_empty_month(self) -> None:
        forecast = calculate_spending_forecast(
            "2026-07", 0.0, 9300.0, today=date(2026, 7, 5)
        )

        self.assertEqual(forecast["daily_average_so_far"], 0.0)
        self.assertEqual(forecast["projected_monthly_spend"], 0.0)
        self.assertEqual(forecast["projected_remaining_budget"], 9300.0)
        self.assertEqual(forecast["forecast_status"], "UNDER_BUDGET")

    def test_spending_forecast_february_historical_and_future(self) -> None:
        historical = calculate_spending_forecast(
            "2024-02", 2900.0, 2900.0, today=date(2026, 6, 4)
        )
        future = calculate_spending_forecast(
            "2028-02", 0.0, 2900.0, today=date(2026, 6, 4)
        )

        self.assertEqual(historical["days_in_month"], 29)
        self.assertEqual(historical["current_day"], 29)
        self.assertEqual(historical["daily_average_so_far"], 100.0)
        self.assertEqual(historical["projected_monthly_spend"], 2900.0)
        self.assertEqual(future["days_in_month"], 29)
        self.assertEqual(future["current_day"], 1)


if __name__ == "__main__":
    unittest.main()
