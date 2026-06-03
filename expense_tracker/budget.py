from __future__ import annotations

import os

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


def _budget_from_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value in (None, ""):
        return default
    try:
        return float(value)
    except ValueError:
        return default
