from __future__ import annotations

import calendar
from datetime import date
from typing import Any

from expense_tracker.reflection import calculate_reflection
from expense_tracker.reports import calculate_daily_report, read_month_rows
from expense_tracker.sheets import SheetsError


def reflection_history_report(current_date: date | None = None) -> dict[str, Any]:
    if current_date is None:
        current_date = date.today()

    month = current_date.isoformat()[:7]
    try:
        rows = read_month_rows(month)
    except SheetsError:
        rows = []

    return calculate_reflection_history(rows, current_date)


def calculate_reflection_history(
    rows: list[list[Any]],
    current_date: date,
) -> dict[str, Any]:
    month = current_date.isoformat()[:7]
    records = []

    for day in range(1, current_date.day + 1):
        target_date = f"{month}-{day:02d}"
        daily_report = calculate_daily_report(rows, target_date)
        reflection = calculate_reflection(daily_report)
        records.append(_history_record(reflection))

    return {
        "month": month,
        "days_in_month": calendar.monthrange(current_date.year, current_date.month)[1],
        "records": records,
        "summary": summarize_reflection_records(records),
    }


def summarize_reflection_records(records: list[dict[str, Any]]) -> dict[str, int]:
    ok_days = 0
    over_budget_days = 0
    no_spending_days = 0
    total_days_with_transactions = 0

    for record in records:
        transaction_count = int(record.get("transaction_count") or 0)
        message = str(record.get("message") or "")

        if transaction_count == 0:
            no_spending_days += 1
            continue

        total_days_with_transactions += 1
        if message == "You exceeded your daily budget today.":
            over_budget_days += 1
        else:
            ok_days += 1

    return {
        "ok_days": ok_days,
        "over_budget_days": over_budget_days,
        "no_spending_days": no_spending_days,
        "total_days_with_transactions": total_days_with_transactions,
    }


def _history_record(reflection: dict[str, Any]) -> dict[str, Any]:
    reflection_detail = reflection["reflection"]
    return {
        "date": reflection["date"],
        "total_expense": reflection["total_expense"],
        "transaction_count": reflection["transaction_count"],
        "top_category": reflection_detail["top_category"],
        "top_merchant": reflection_detail["top_merchant"],
        "budget_status": reflection_detail["budget_status"],
        "message": reflection_detail["message"],
    }
