from __future__ import annotations

import calendar
import os
from datetime import date

from expense_tracker.sheets import load_dotenv


DEFAULT_DAILY_BUDGET = 300.0
DEFAULT_MONTHLY_BUDGET = 9000.0


def get_daily_budget() -> float:
    load_dotenv()
    return _budget_from_env("DAILY_BUDGET", DEFAULT_DAILY_BUDGET)


def get_monthly_budget() -> float:
    load_dotenv()
    return _budget_from_env("MONTHLY_BUDGET", DEFAULT_MONTHLY_BUDGET)


def calculate_remaining_budget(total_expense: float, budget: float) -> float:
    return round(budget - total_expense, 2)


def calculate_budget_status(total_expense: float, budget: float) -> str:
    if budget <= 0:
        return "OVER_BUDGET" if total_expense > 0 else "OK"

    usage_ratio = total_expense / budget
    if usage_ratio <= 0.8:
        return "OK"
    if usage_ratio <= 1:
        return "WARNING"
    return "OVER_BUDGET"


def calculate_monthly_budget_health(
    month: str, total_expense: float, monthly_budget: float, today: date | None = None
) -> dict[str, float | int | str]:
    if today is None:
        today = date.today()

    year, month_number = _parse_month(month)
    days_in_month = calendar.monthrange(year, month_number)[1]
    current_day = _current_day_for_month(year, month_number, days_in_month, today)
    expected_spend = round((monthly_budget / days_in_month) * current_day, 2)
    actual_spend = round(total_expense, 2)
    variance = round(actual_spend - expected_spend, 2)
    health_status = calculate_budget_health_status(variance, expected_spend)

    return {
        "monthly_budget": monthly_budget,
        "days_in_month": days_in_month,
        "current_day": current_day,
        "expected_spend": expected_spend,
        "actual_spend": actual_spend,
        "variance": variance,
        "health_status": health_status,
        "health_message": budget_health_message(health_status),
    }


def calculate_spending_forecast(
    month: str, total_expense: float, monthly_budget: float, today: date | None = None
) -> dict[str, float | int | str]:
    if today is None:
        today = date.today()

    year, month_number = _parse_month(month)
    days_in_month = calendar.monthrange(year, month_number)[1]
    current_day = _current_day_for_month(year, month_number, days_in_month, today)
    actual_spend = round(total_expense, 2)
    raw_daily_average = actual_spend / current_day if current_day else 0.0
    daily_average = round(raw_daily_average, 2)
    projected_spend = round(raw_daily_average * days_in_month, 2)
    projected_remaining = round(monthly_budget - projected_spend, 2)

    return {
        "current_day": current_day,
        "days_in_month": days_in_month,
        "actual_spend": actual_spend,
        "daily_average_so_far": daily_average,
        "projected_monthly_spend": projected_spend,
        "monthly_budget": monthly_budget,
        "projected_remaining_budget": projected_remaining,
        "forecast_status": calculate_forecast_status(
            projected_spend, monthly_budget
        ),
    }


def calculate_forecast_status(projected_monthly_spend: float, monthly_budget: float) -> str:
    if monthly_budget <= 0:
        return "UNDER_BUDGET" if projected_monthly_spend <= 0 else "OVER_BUDGET"

    if projected_monthly_spend <= monthly_budget * 0.8:
        return "UNDER_BUDGET"
    if projected_monthly_spend <= monthly_budget:
        return "ON_TRACK"
    return "OVER_BUDGET"


def calculate_budget_health_status(variance: float, expected_spend: float) -> str:
    if expected_spend <= 0:
        return "GOOD" if variance <= 0 else "OVERSPENDING"

    tolerance = expected_spend * 0.2
    if variance <= -tolerance:
        return "GOOD"
    if variance <= tolerance:
        return "ON_TRACK"
    return "OVERSPENDING"


def budget_health_message(status: str) -> str:
    messages = {
        "GOOD": "You are spending below your planned budget.",
        "ON_TRACK": "You are spending within your planned budget.",
        "OVERSPENDING": "You are spending faster than your planned budget.",
    }
    return messages.get(status, messages["ON_TRACK"])


def _parse_month(month: str) -> tuple[int, int]:
    year_text, month_text = month.split("-", 1)
    return int(year_text), int(month_text)


def _current_day_for_month(
    year: int, month_number: int, days_in_month: int, today: date
) -> int:
    target_month = date(year, month_number, 1)
    current_month = date(today.year, today.month, 1)

    if target_month == current_month:
        return today.day
    if target_month < current_month:
        return days_in_month
    return 1


def _budget_from_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value in (None, ""):
        return default
    try:
        return float(value)
    except ValueError:
        return default
