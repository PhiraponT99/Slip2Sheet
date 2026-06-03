from __future__ import annotations

from typing import Any

from expense_tracker.reports import today_report


def reflection_report() -> dict[str, Any]:
    return calculate_reflection(today_report())


def calculate_reflection(report: dict[str, Any]) -> dict[str, Any]:
    transactions = report.get("transactions", [])
    total_expense = _number(report.get("total_expense"))
    daily_budget = _number(report.get("daily_budget"))
    transaction_count = len(transactions)
    top_category = _top_total(report.get("category_totals", {}))[0]
    top_merchant = _top_merchant(transactions)
    budget_status = str(report.get("budget_status") or "OK")

    return {
        "date": report.get("date"),
        "total_expense": total_expense,
        "transaction_count": transaction_count,
        "reflection": {
            "top_category": top_category,
            "top_merchant": top_merchant,
            "budget_status": budget_status,
            "message": reflection_message(
                total_expense,
                daily_budget,
                transaction_count,
            ),
        },
    }


def reflection_message(
    total_expense: float,
    daily_budget: float,
    transaction_count: int,
) -> str:
    if transaction_count == 0:
        return "No spending recorded today."
    if total_expense <= daily_budget:
        return "You stayed within your daily budget today."
    return "You exceeded your daily budget today."


def _top_merchant(transactions: list[dict[str, Any]]) -> str | None:
    totals: dict[str, float] = {}
    for transaction in transactions:
        merchant = str(transaction.get("merchant") or "")
        if not merchant:
            continue

        totals[merchant] = round(
            totals.get(merchant, 0.0) + _number(transaction.get("amount")),
            2,
        )

    return _top_total(totals)[0]


def _top_total(totals: dict[str, Any]) -> tuple[str | None, float | None]:
    if not totals:
        return None, None

    name, amount = max(
        ((name, _number(amount)) for name, amount in totals.items()),
        key=lambda item: item[1],
    )
    return name, round(amount, 2)


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
