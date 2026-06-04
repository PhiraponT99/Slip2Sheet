from __future__ import annotations

import calendar
from datetime import date
from typing import Any

from expense_tracker.reflection import calculate_reflection
from expense_tracker.reflection_history import summarize_reflection_records
from expense_tracker.reports import calculate_daily_report, read_month_rows
from expense_tracker.sheets import SheetsError


def monthly_reflection_report(current_date: date | None = None) -> dict[str, Any]:
    if current_date is None:
        current_date = date.today()

    month = current_date.isoformat()[:7]
    try:
        rows = read_month_rows(month)
    except SheetsError:
        rows = []

    return calculate_monthly_reflection(rows, current_date)


def calculate_monthly_reflection(
    rows: list[list[Any]],
    current_date: date,
) -> dict[str, Any]:
    month = current_date.isoformat()[:7]
    days_in_month = calendar.monthrange(current_date.year, current_date.month)[1]
    records = []
    total_expense = 0.0
    transaction_count = 0
    category_totals: dict[str, float] = {}
    merchant_totals: dict[str, float] = {}

    for day in range(1, days_in_month + 1):
        target_date = f"{month}-{day:02d}"
        daily_report = calculate_daily_report(rows, target_date)
        reflection = calculate_reflection(daily_report)
        records.append(_history_record(reflection))

        total_expense += float(daily_report.get("total_expense") or 0.0)
        transactions = daily_report.get("transactions", [])
        transaction_count += len(transactions)
        _add_totals(category_totals, daily_report.get("category_totals", {}))
        _add_merchant_totals(merchant_totals, transactions)

    summary = summarize_reflection_records(records)
    total_days_with_transactions = summary["total_days_with_transactions"]

    return {
        "month": month,
        "days_in_month": days_in_month,
        "total_expense": round(total_expense, 2),
        "transaction_count": transaction_count,
        "top_category": _top_name(category_totals),
        "top_merchant": _top_name(merchant_totals),
        "total_days_with_transactions": total_days_with_transactions,
        "spending_day_ratio": round(total_days_with_transactions / days_in_month, 2),
        "summary": {
            "ok_days": summary["ok_days"],
            "over_budget_days": summary["over_budget_days"],
            "no_spending_days": summary["no_spending_days"],
        },
        "message": monthly_message(
            transaction_count,
            summary["ok_days"],
            summary["over_budget_days"],
            total_days_with_transactions,
        ),
    }


def monthly_message(
    transaction_count: int,
    ok_days: int,
    over_budget_days: int,
    total_days_with_transactions: int,
) -> str:
    if transaction_count == 0:
        return "No spending recorded this month."
    if over_budget_days == 0 and total_days_with_transactions > 0:
        return "You stayed within budget on all spending days this month."
    if ok_days > over_budget_days:
        return "You stayed within budget on most spending days this month."
    return "You exceeded your budget on several spending days this month."


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
