from __future__ import annotations

from datetime import date
from typing import Any, Callable

from expense_tracker.goals import goals_report
from expense_tracker.reflection import calculate_reflection
from expense_tracker.reports import (
    calculate_daily_report,
    calculate_month_report,
    month_report,
    today_report,
)
from expense_tracker.sheets import SheetsError


WIDTH = 38
TITLE = "Slip2Sheet Dashboard"


def dashboard_payload(
    today_fn: Callable[[], dict[str, Any]] = today_report,
    month_fn: Callable[[str], dict[str, Any]] = month_report,
    goals_fn: Callable[[], dict[str, Any]] = goals_report,
    current_date: date | None = None,
) -> dict[str, Any]:
    if current_date is None:
        current_date = date.today()

    today_text = current_date.isoformat()
    month_text = today_text[:7]
    today_data = _load_today_report(today_fn, today_text)
    month_data = _load_month_report(month_fn, month_text)
    goals_data = goals_fn()
    reflection_data = calculate_reflection(today_data)

    return {
        "today": today_data,
        "month": month_data,
        "insights": month_data.get("insights", {}),
        "forecast": month_data.get("forecast", {}),
        "goals": goals_data.get("goals", []),
        "reflection": reflection_data.get("reflection", {}),
    }


def render_dashboard(payload: dict[str, Any]) -> str:
    today = payload["today"]
    month = payload["month"]
    insights = payload.get("insights", {})
    forecast = payload.get("forecast", month.get("forecast", {}))
    goals = payload.get("goals", [])
    reflection = payload.get("reflection", {})
    month_status = month.get("budget_health", {}).get(
        "health_status", month.get("budget_status", "OK")
    )

    lines = [
        _rule("═"),
        TITLE,
        _rule("═"),
        "",
        "Today",
        _rule("─"),
        _label_value("Spent:", format_money(today.get("total_expense"))),
        _label_value("Budget:", format_money(today.get("daily_budget"))),
        _label_value("Remaining:", format_money(today.get("remaining_budget"))),
        _label_value("Status:", str(today.get("budget_status", "OK"))),
        "",
        "Month",
        _rule("─"),
        _label_value("Spent:", format_money(month.get("total_expense"))),
        _label_value("Budget:", format_money(month.get("monthly_budget"))),
        _label_value("Remaining:", format_money(month.get("remaining_budget"))),
        _label_value("Status:", str(month_status)),
        "",
        "Top Category",
        _rule("─"),
        _named_amount(
            insights.get("top_category"),
            insights.get("top_category_amount"),
        ),
        "",
        "Top Merchant",
        _rule("─"),
        _named_amount(
            insights.get("top_merchant"),
            insights.get("top_merchant_amount"),
        ),
        "",
        "Insights",
        _rule("─"),
        _label_value("Transactions:", str(insights.get("transaction_count", 0))),
        _label_value(
            "Average Spend:",
            format_money(insights.get("average_transaction")),
        ),
        "",
        "Forecast",
        _rule("─"),
        _label_value(
            "Projected:",
            format_money(forecast.get("projected_monthly_spend")),
        ),
        _label_value(
            "Remaining:",
            format_money(forecast.get("projected_remaining_budget")),
        ),
        _label_value("Status:", str(forecast.get("forecast_status", "UNDER_BUDGET"))),
        "",
        "Goals",
        _rule("─"),
        *_goal_lines(goals),
        "",
        "Reflection",
        _rule("─"),
        str(reflection.get("message", "No spending recorded today.")),
        "",
        _rule("═"),
    ]
    return "\n".join(lines)


def format_money(value: Any) -> str:
    amount = _number(value)
    return f"{amount:.2f} THB"


def _load_today_report(
    today_fn: Callable[[], dict[str, Any]], today_text: str
) -> dict[str, Any]:
    try:
        return today_fn()
    except Exception as exc:
        if not _is_missing_sheet_error(exc):
            raise
        return calculate_daily_report([], today_text)


def _load_month_report(
    month_fn: Callable[[str], dict[str, Any]], month_text: str
) -> dict[str, Any]:
    try:
        return month_fn(month_text)
    except Exception as exc:
        if not _is_missing_sheet_error(exc):
            raise
        return calculate_month_report([], month_text)


def _is_missing_sheet_error(exc: Exception) -> bool:
    if isinstance(exc, SheetsError):
        return True

    message = str(exc).lower()
    return "unable to parse range" in message or "sheet" in message and "not found" in message


def _rule(character: str) -> str:
    return character * WIDTH


def _label_value(label: str, value: str) -> str:
    return f"{label:<14}{value:>16}"


def _named_amount(name: Any, amount: Any) -> str:
    display_name = str(name) if name else "None"
    return f"{display_name} ({format_money(amount)})"


def _goal_lines(goals: list[dict[str, Any]]) -> list[str]:
    if not goals:
        return ["No goals yet"]
    return [
        _label_value(str(goal["name"]), f"{float(goal['progress_percent']):.1f}%")
        for goal in goals
    ]


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
