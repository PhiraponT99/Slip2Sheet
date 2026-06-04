from __future__ import annotations

from typing import Any


def render_reflection_report_markdown(report: dict[str, Any]) -> str:
    daily = report.get("daily", {})
    weekly = report.get("weekly", {})
    monthly = report.get("monthly", {})

    lines = [
        "# Slip2Sheet Reflection Report",
        "",
        f"Date: {_value(report.get('date'))}",
        "",
        "## Daily Reflection",
        "",
        f"Total Expense: {_number(daily.get('total_expense'))}",
        f"Transaction Count: {int(daily.get('transaction_count') or 0)}",
        f"Top Category: {_value(daily.get('top_category'))}",
        f"Top Merchant: {_value(daily.get('top_merchant'))}",
        "",
        f"Message: {_value(daily.get('message'))}",
        "",
        "## Weekly Reflection",
        "",
        f"Week: {_value(weekly.get('week_start'))} to {_value(weekly.get('week_end'))}",
        f"Total Expense: {_number(weekly.get('total_expense'))}",
        f"Transaction Count: {int(weekly.get('transaction_count') or 0)}",
        f"Spending Days: {int(weekly.get('total_days_with_transactions') or 0)}",
        f"Spending Day Ratio: {_number(weekly.get('spending_day_ratio'))}",
        "",
        f"Message: {_value(weekly.get('message'))}",
        "",
        "## Monthly Reflection",
        "",
        f"Month: {_value(monthly.get('month'))}",
        f"Total Expense: {_number(monthly.get('total_expense'))}",
        f"Transaction Count: {int(monthly.get('transaction_count') or 0)}",
        f"Spending Days: {int(monthly.get('total_days_with_transactions') or 0)}",
        f"Spending Day Ratio: {_number(monthly.get('spending_day_ratio'))}",
        "",
        f"Message: {_value(monthly.get('message'))}",
        "",
        "## Overall",
        "",
        _value(report.get("overall_message")),
    ]
    return "\n".join(lines)


def _value(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return str(value)


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
