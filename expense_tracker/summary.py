from __future__ import annotations

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


SUMMARY_SHEET_NAME = "Summary"
SUMMARY_COLUMNS = ("Metric", "Value")
MONTHLY_COLUMNS = ("Month", "Total Expense")
TRACKED_CATEGORIES = ("food", "transport", "utilities")
MONTH_TAB_PATTERN = re.compile(r"^\d{4}-\d{2}$")
DUPLICATE_NOTE = "DUPLICATE_SKIPPED"


def update_summary_sheet() -> dict[str, Any]:
    import os

    load_dotenv()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if not sheet_id:
        raise SheetsError("GOOGLE_SHEET_ID is not set.")

    service = _build_sheets_service(credentials_path)
    metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheet_titles = [
        sheet["properties"]["title"]
        for sheet in metadata.get("sheets", [])
        if "properties" in sheet
    ]
    month_tabs = sorted(title for title in sheet_titles if is_month_tab(title))

    rows_by_month: dict[str, list[list[Any]]] = {}
    for month in month_tabs:
        response = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=f"{_quote_sheet_name(month)}!A:K")
            .execute()
        )
        rows_by_month[month] = response.get("values", [])

    summary = calculate_summary(rows_by_month)
    summary["budget_overview"] = build_budget_overview(summary)
    _ensure_summary_tab(service, sheet_id, sheet_titles)
    values = build_summary_values(summary)

    service.spreadsheets().values().clear(
        spreadsheetId=sheet_id,
        range=f"{_quote_sheet_name(SUMMARY_SHEET_NAME)}!A:B",
        body={},
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{_quote_sheet_name(SUMMARY_SHEET_NAME)}!A1:B{len(values)}",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()

    return {
        "summary_sheet": SUMMARY_SHEET_NAME,
        "months": month_tabs,
    }


def calculate_summary(rows_by_month: dict[str, list[list[Any]]]) -> dict[str, Any]:
    category_totals = {
        "food": 0.0,
        "transport": 0.0,
        "utilities": 0.0,
        "other": 0.0,
    }
    monthly_totals: dict[str, float] = {}

    for month in sorted(rows_by_month):
        month_total = 0.0
        for row in _data_rows(rows_by_month[month]):
            if _is_duplicate_marked(row):
                continue

            amount = _parse_amount(_cell(row, 4))
            if amount is None:
                continue

            category = _normalize_category(_cell(row, 3), _cell(row, 2))
            category_totals[category] += amount
            month_total += amount

        monthly_totals[month] = round(month_total, 2)

    total_expense = round(sum(monthly_totals.values()), 2)
    return {
        "total_expense": total_expense,
        "category_totals": {
            category: round(total, 2) for category, total in category_totals.items()
        },
        "monthly_totals": monthly_totals,
    }


def build_summary_values(summary: dict[str, Any]) -> list[list[Any]]:
    category_totals = summary["category_totals"]
    budget_overview = summary.get("budget_overview")
    values: list[list[Any]] = [
        list(SUMMARY_COLUMNS),
        ["Total Expense", summary["total_expense"]],
        ["Food Expense", category_totals["food"]],
        ["Transport Expense", category_totals["transport"]],
        ["Utilities Expense", category_totals["utilities"]],
        ["Other Expense", category_totals["other"]],
        [],
        list(MONTHLY_COLUMNS),
    ]

    for month, total in sorted(summary["monthly_totals"].items()):
        values.append([month, total])

    if budget_overview:
        values.extend(
            [
                [],
                ["Budget Overview", ""],
                list(SUMMARY_COLUMNS),
                ["Daily Budget", budget_overview["daily_budget"]],
                ["Monthly Budget", budget_overview["monthly_budget"]],
                ["Current Month Expense", budget_overview["current_month_expense"]],
                [
                    "Remaining Monthly Budget",
                    budget_overview["remaining_monthly_budget"],
                ],
                ["Budget Status", budget_overview["budget_status"]],
            ]
        )

    return values


def build_budget_overview(
    summary: dict[str, Any], current_month: str | None = None
) -> dict[str, Any]:
    if current_month is None:
        current_month = date.today().isoformat()[:7]

    monthly_budget = get_monthly_budget()
    current_month_expense = summary["monthly_totals"].get(current_month, 0.0)
    return {
        "daily_budget": get_daily_budget(),
        "monthly_budget": monthly_budget,
        "current_month_expense": current_month_expense,
        "remaining_monthly_budget": calculate_remaining_budget(
            current_month_expense, monthly_budget
        ),
        "budget_status": calculate_budget_status(
            current_month_expense, monthly_budget
        ),
    }


def is_month_tab(name: str) -> bool:
    return bool(MONTH_TAB_PATTERN.fullmatch(name))


def _ensure_summary_tab(service, sheet_id: str, sheet_titles: list[str]) -> None:
    if SUMMARY_SHEET_NAME in sheet_titles:
        return

    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": SUMMARY_SHEET_NAME,
                            "gridProperties": {
                                "rowCount": 1000,
                                "columnCount": 2,
                            },
                        }
                    }
                }
            ]
        },
    ).execute()


def _data_rows(rows: list[list[Any]]) -> list[list[Any]]:
    if not rows:
        return []
    first_cell = str(_cell(rows[0], 0)).strip().lower()
    if first_cell == "date":
        return rows[1:]
    return rows


def _normalize_category(category: Any, merchant: Any = None) -> str:
    normalized_merchant = normalize_merchant(str(merchant)) if merchant else None
    mapped_category = lookup_category(normalized_merchant)
    normalized = str(mapped_category or category or "").strip().lower()
    if normalized in TRACKED_CATEGORIES:
        return normalized
    return "other"


def _parse_amount(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _is_duplicate_marked(row: list[Any]) -> bool:
    return str(_cell(row, 8)).strip() == DUPLICATE_NOTE


def _cell(row: list[Any], index: int) -> Any:
    if index >= len(row):
        return ""
    return row[index]
