from __future__ import annotations

from datetime import date
from typing import Any, Callable

from expense_tracker.monthly_reflection import monthly_reflection_report
from expense_tracker.reflection import reflection_report as daily_reflection_report
from expense_tracker.weekly_reflection import weekly_reflection_report


def reflection_report(
    current_date: date | None = None,
    daily_fn: Callable[[], dict[str, Any]] = daily_reflection_report,
    weekly_fn: Callable[[], dict[str, Any]] = weekly_reflection_report,
    monthly_fn: Callable[[], dict[str, Any]] = monthly_reflection_report,
) -> dict[str, Any]:
    if current_date is None:
        current_date = date.today()

    daily = daily_fn()
    weekly = weekly_fn()
    monthly = monthly_fn()

    daily_summary = _daily_summary(daily)
    weekly_summary = _weekly_summary(weekly)
    monthly_summary = _monthly_summary(monthly)

    return {
        "date": current_date.isoformat(),
        "daily": daily_summary,
        "weekly": weekly_summary,
        "monthly": monthly_summary,
        "overall_message": overall_message(
            daily_summary,
            weekly,
            monthly,
        ),
    }


def overall_message(
    daily: dict[str, Any],
    weekly: dict[str, Any],
    monthly: dict[str, Any],
) -> str:
    total_transactions = (
        int(daily.get("transaction_count") or 0)
        + int(weekly.get("transaction_count") or 0)
        + int(monthly.get("transaction_count") or 0)
    )
    if total_transactions == 0:
        return "No spending recorded yet."

    daily_over = daily.get("message") == "You exceeded your daily budget today."
    weekly_over = _period_over_budget(weekly)
    monthly_over = _period_over_budget(monthly)

    if monthly_over:
        return "Your monthly spending is over budget and needs attention."
    if weekly_over:
        return "This week needs attention, but your monthly spending is still manageable."
    if daily_over:
        return "Today was over budget, but your weekly and monthly spending are still manageable."
    return "Your spending is currently under control."


def _daily_summary(report: dict[str, Any]) -> dict[str, Any]:
    reflection = report.get("reflection", {})
    return {
        "total_expense": report.get("total_expense", 0.0),
        "transaction_count": report.get("transaction_count", 0),
        "top_category": reflection.get("top_category"),
        "top_merchant": reflection.get("top_merchant"),
        "budget_status": reflection.get("budget_status"),
        "message": reflection.get("message"),
    }


def _weekly_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "week_start": report.get("week_start"),
        "week_end": report.get("week_end"),
        "total_expense": report.get("total_expense", 0.0),
        "transaction_count": report.get("transaction_count", 0),
        "total_days_with_transactions": report.get("total_days_with_transactions", 0),
        "spending_day_ratio": report.get("spending_day_ratio", 0.0),
        "message": report.get("message"),
    }


def _monthly_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "month": report.get("month"),
        "days_in_month": report.get("days_in_month"),
        "total_expense": report.get("total_expense", 0.0),
        "transaction_count": report.get("transaction_count", 0),
        "total_days_with_transactions": report.get("total_days_with_transactions", 0),
        "spending_day_ratio": report.get("spending_day_ratio", 0.0),
        "message": report.get("message"),
    }


def _period_over_budget(report: dict[str, Any]) -> bool:
    summary = report.get("summary", {})
    ok_days = int(summary.get("ok_days") or 0)
    over_budget_days = int(summary.get("over_budget_days") or 0)
    return over_budget_days > 0 and over_budget_days >= ok_days
