from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from expense_tracker.reflection import calculate_reflection
from expense_tracker.reflection_history import summarize_reflection_records
from expense_tracker.reports import calculate_daily_report, read_month_rows
from expense_tracker.sheets import SheetsError


def weekly_reflection_report(current_date: date | None = None) -> dict[str, Any]:
    if current_date is None:
        current_date = date.today()

    week_start, week_end = week_bounds(current_date)
    rows_by_month = {}
    for month in _months_between(week_start, week_end):
        try:
            rows_by_month[month] = read_month_rows(month)
        except SheetsError:
            rows_by_month[month] = []

    return calculate_weekly_reflection(rows_by_month, current_date)


def calculate_weekly_reflection(
    rows_by_month: dict[str, list[list[Any]]],
    current_date: date,
) -> dict[str, Any]:
    week_start, week_end = week_bounds(current_date)
    records = []
    total_expense = 0.0
    transaction_count = 0
    category_totals: dict[str, float] = {}
    merchant_totals: dict[str, float] = {}

    day = week_start
    while day <= week_end:
        day_text = day.isoformat()
        month = day_text[:7]
        daily_report = calculate_daily_report(rows_by_month.get(month, []), day_text)
        reflection = calculate_reflection(daily_report)
        reflection_record = _history_record(reflection)
        records.append(reflection_record)

        total_expense += float(daily_report.get("total_expense") or 0.0)
        transaction_count += len(daily_report.get("transactions", []))
        _add_totals(category_totals, daily_report.get("category_totals", {}))
        _add_merchant_totals(merchant_totals, daily_report.get("transactions", []))

        day += timedelta(days=1)

    summary = summarize_reflection_records(records)
    top_category = _top_name(category_totals)
    top_merchant = _top_name(merchant_totals)

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "total_expense": round(total_expense, 2),
        "transaction_count": transaction_count,
        "top_category": top_category,
        "top_merchant": top_merchant,
        "total_days_with_transactions": summary["total_days_with_transactions"],
        "spending_day_ratio": round(summary["total_days_with_transactions"] / 7, 2),
        "summary": {
            "ok_days": summary["ok_days"],
            "over_budget_days": summary["over_budget_days"],
            "no_spending_days": summary["no_spending_days"],
        },
        "message": weekly_message(
            transaction_count,
            summary["ok_days"],
            summary["over_budget_days"],
            summary["total_days_with_transactions"],
        ),
    }


def weekly_message(
    transaction_count: int,
    ok_days: int,
    over_budget_days: int,
    total_days_with_transactions: int,
) -> str:
    if transaction_count == 0:
        return "No spending recorded this week."
    if over_budget_days == 0 and total_days_with_transactions > 0:
        return "You stayed within budget on all spending days this week."
    if ok_days > over_budget_days:
        return "You stayed within budget for most spending days this week."
    return "You exceeded your budget on several spending days this week."


def week_bounds(current_date: date) -> tuple[date, date]:
    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def _months_between(start: date, end: date) -> list[str]:
    months = []
    cursor = date(start.year, start.month, 1)
    final = date(end.year, end.month, 1)
    while cursor <= final:
        months.append(cursor.isoformat()[:7])
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return months


def _history_record(reflection: dict[str, Any]) -> dict[str, Any]:
    detail = reflection["reflection"]
    return {
        "date": reflection["date"],
        "total_expense": reflection["total_expense"],
        "transaction_count": reflection["transaction_count"],
        "top_category": detail["top_category"],
        "top_merchant": detail["top_merchant"],
        "budget_status": detail["budget_status"],
        "message": detail["message"],
    }


def _add_totals(target: dict[str, float], source: dict[str, Any]) -> None:
    for name, amount in source.items():
        target[name] = round(target.get(name, 0.0) + float(amount or 0.0), 2)


def _add_merchant_totals(
    merchant_totals: dict[str, float],
    transactions: list[dict[str, Any]],
) -> None:
    for transaction in transactions:
        merchant = str(transaction.get("merchant") or "")
        if not merchant:
            continue
        merchant_totals[merchant] = round(
            merchant_totals.get(merchant, 0.0)
            + float(transaction.get("amount") or 0.0),
            2,
        )


def _top_name(totals: dict[str, float]) -> str | None:
    if not totals:
        return None
    return max(totals.items(), key=lambda item: item[1])[0]
