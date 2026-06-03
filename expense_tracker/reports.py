from __future__ import annotations

import os
import re
from datetime import date
from typing import Any

from expense_tracker.budget import (
    calculate_budget_status,
    calculate_remaining_budget,
    get_daily_budget,
    get_monthly_budget,
)
from expense_tracker.merchant_aliases import normalize_merchant
from expense_tracker.merchant_categories import lookup_category
from expense_tracker.sheets import (
    SheetsError,
    _build_sheets_service,
    _quote_sheet_name,
    load_dotenv,
)


MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")
REPORT_COLUMNS = [
    "Date",
    "Time",
    "Merchant",
    "Category",
    "Amount",
    "OriginalAmount",
    "Discount",
    "PaymentMethod",
    "Note",
    "SourceImage",
    "CreatedAt",
    "TransactionKey",
]
DUPLICATE_NOTE = "DUPLICATE_SKIPPED"


def today_report() -> dict[str, Any]:
    today = date.today().isoformat()
    month = today[:7]
    rows = read_month_rows(month)
    return calculate_daily_report(rows, today)


def month_report(month: str) -> dict[str, Any]:
    if not MONTH_PATTERN.fullmatch(month):
        raise SheetsError(f"Invalid month format: {month}. Expected YYYY-MM.")

    rows = read_month_rows(month)
    return calculate_month_report(rows, month)


def read_month_rows(month: str) -> list[list[Any]]:
    load_dotenv()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if not sheet_id:
        raise SheetsError("GOOGLE_SHEET_ID is not set.")
    if not credentials_path:
        raise SheetsError("GOOGLE_APPLICATION_CREDENTIALS is not set.")

    service = _build_sheets_service(credentials_path)
    response = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"{_quote_sheet_name(month)}!A:L")
        .execute()
    )
    return response.get("values", [])


def calculate_daily_report(rows: list[list[Any]], target_date: str) -> dict[str, Any]:
    transactions = [
        transaction
        for transaction in rows_to_transactions(rows)
        if transaction["date"] == target_date
    ]
    summary = summarize_transactions(transactions)
    daily_budget = get_daily_budget()
    return {
        "date": target_date,
        "total_expense": summary["total_expense"],
        "daily_budget": daily_budget,
        "remaining_budget": calculate_remaining_budget(
            summary["total_expense"], daily_budget
        ),
        "budget_status": calculate_budget_status(
            summary["total_expense"], daily_budget
        ),
        "category_totals": summary["category_totals"],
        "transactions": transactions,
    }


def calculate_month_report(rows: list[list[Any]], month: str) -> dict[str, Any]:
    transactions = [
        transaction
        for transaction in rows_to_transactions(rows)
        if str(transaction["date"]).startswith(f"{month}-")
    ]
    summary = summarize_transactions(transactions)
    monthly_budget = get_monthly_budget()
    return {
        "month": month,
        "total_expense": summary["total_expense"],
        "monthly_budget": monthly_budget,
        "remaining_budget": calculate_remaining_budget(
            summary["total_expense"], monthly_budget
        ),
        "budget_status": calculate_budget_status(
            summary["total_expense"], monthly_budget
        ),
        "category_totals": summary["category_totals"],
        "transactions": transactions,
    }


def summarize_transactions(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    category_totals: dict[str, float] = {}
    total = 0.0

    for transaction in transactions:
        amount = transaction["amount"]
        if amount is None:
            continue

        category = transaction["category"] or "other"
        category_totals[category] = round(category_totals.get(category, 0.0) + amount, 2)
        total += amount

    return {
        "total_expense": round(total, 2),
        "category_totals": category_totals,
    }


def rows_to_transactions(rows: list[list[Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []

    data_rows = rows[1:] if _is_header_row(rows[0]) else rows
    transactions = []

    for row in data_rows:
        if _is_duplicate_marked(row):
            continue

        amount = _parse_amount(_cell(row, 4))
        if amount is None:
            continue

        merchant = normalize_merchant(str(_cell(row, 2)))
        category = lookup_category(merchant) or str(_cell(row, 3) or "other")
        transactions.append(
            {
                "date": str(_cell(row, 0)),
                "time": str(_cell(row, 1)),
                "merchant": merchant or "",
                "category": category,
                "amount": amount,
                "original_amount": _parse_amount(_cell(row, 5)),
                "discount": _parse_amount(_cell(row, 6)),
                "payment_method": _none_if_blank(_cell(row, 7)),
                "note": _none_if_blank(_cell(row, 8)),
                "source_image": _none_if_blank(_cell(row, 9)),
                "created_at": _none_if_blank(_cell(row, 10)),
                "transaction_key": _none_if_blank(_cell(row, 11)),
            }
        )

    return transactions


def _is_header_row(row: list[Any]) -> bool:
    return str(_cell(row, 0)).strip().lower() == "date"


def _parse_amount(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _none_if_blank(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _is_duplicate_marked(row: list[Any]) -> bool:
    return str(_cell(row, 8)).strip() == DUPLICATE_NOTE


def _cell(row: list[Any], index: int) -> Any:
    if index >= len(row):
        return ""
    return row[index]
