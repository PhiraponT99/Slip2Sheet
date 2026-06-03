from __future__ import annotations

import os
from typing import Any

from expense_tracker.reports import rows_to_transactions, summarize_transactions
from expense_tracker.sheets import (
    SheetsError,
    _build_sheets_service,
    _quote_sheet_name,
    load_dotenv,
)
from expense_tracker.summary import is_month_tab


def trend_report() -> dict[str, Any]:
    rows_by_month = read_all_month_rows()
    return calculate_trend_report(rows_by_month)


def read_all_month_rows() -> dict[str, list[list[Any]]]:
    load_dotenv()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if not sheet_id:
        raise SheetsError("GOOGLE_SHEET_ID is not set.")
    if not credentials_path:
        raise SheetsError("GOOGLE_APPLICATION_CREDENTIALS is not set.")

    service = _build_sheets_service(credentials_path)
    metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    month_tabs = sorted(
        sheet["properties"]["title"]
        for sheet in metadata.get("sheets", [])
        if "properties" in sheet and is_month_tab(sheet["properties"].get("title", ""))
    )

    rows_by_month: dict[str, list[list[Any]]] = {}
    for month in month_tabs:
        response = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=f"{_quote_sheet_name(month)}!A:L")
            .execute()
        )
        rows_by_month[month] = response.get("values", [])

    return rows_by_month


def calculate_trend_report(rows_by_month: dict[str, list[list[Any]]]) -> dict[str, Any]:
    months = []
    for month in sorted(rows_by_month):
        transactions = [
            transaction
            for transaction in rows_to_transactions(rows_by_month[month])
            if str(transaction["date"]).startswith(f"{month}-")
        ]
        summary = summarize_transactions(transactions)
        months.append(
            {
                "month": month,
                "total_expense": summary["total_expense"],
            }
        )

    return {
        "months": months,
        "trend": calculate_trend(months),
    }


def calculate_trend(months: list[dict[str, Any]]) -> dict[str, Any]:
    if len(months) < 2:
        return {
            "direction": "STABLE",
            "change_percent": 0.0,
            "message": "Not enough monthly data to calculate a trend.",
        }

    previous = float(months[-2]["total_expense"])
    latest = float(months[-1]["total_expense"])

    if previous == 0:
        change_percent = 0.0 if latest == 0 else 100.0
    else:
        change_percent = round(((latest - previous) / previous) * 100, 1)

    direction = _trend_direction(change_percent)
    return {
        "direction": direction,
        "change_percent": change_percent,
        "message": _trend_message(direction),
    }


def _trend_direction(change_percent: float) -> str:
    if abs(change_percent) < 5:
        return "STABLE"
    if change_percent > 0:
        return "UP"
    return "DOWN"


def _trend_message(direction: str) -> str:
    messages = {
        "UP": "Spending increased compared to previous month.",
        "DOWN": "Spending decreased compared to previous month.",
        "STABLE": "Spending is stable compared to previous month.",
    }
    return messages[direction]
