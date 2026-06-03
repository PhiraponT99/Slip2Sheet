from __future__ import annotations

import os
import re
from typing import Any

from expense_tracker.sheets import (
    SheetsError,
    _build_sheets_service,
    _quote_sheet_name,
    load_dotenv,
)
from expense_tracker.summary import update_summary_sheet


MONTH_TAB_PATTERN = re.compile(r"^\d{4}-\d{2}$")
DUPLICATE_NOTE = "DUPLICATE_SKIPPED"
NOTE_COLUMN_INDEX = 8
TRANSACTION_KEY_COLUMN_INDEX = 11
REQUIRED_COLUMN_COUNT = 12


def backfill_transaction_keys() -> dict[str, Any]:
    service, sheet_id = _build_service_from_env()
    month_sheets = _monthly_sheets(service, sheet_id)
    month_tabs = [sheet["title"] for sheet in month_sheets]
    updates = []
    updated_count = 0

    for sheet in month_sheets:
        month = sheet["title"]
        _ensure_required_columns(service, sheet_id, sheet)
        rows = _read_month_rows(service, sheet_id, month)
        if needs_transaction_key_header(rows):
            updates.append(
                {
                    "range": f"{_quote_sheet_name(month)}!L1",
                    "values": [["TransactionKey"]],
                }
            )

        for row_number, row in _data_rows_with_numbers(rows):
            if _cell(row, TRANSACTION_KEY_COLUMN_INDEX):
                continue

            key = build_transaction_key_from_row(row)
            if not key:
                continue

            updates.append(
                {
                    "range": f"{_quote_sheet_name(month)}!L{row_number}",
                    "values": [[key]],
                }
            )
            updated_count += 1

    _apply_value_updates(service, sheet_id, updates)
    update_summary_sheet()
    return {
        "backfilled": updated_count,
        "months": month_tabs,
        "summary_updated": True,
    }


def dedupe_transactions() -> dict[str, Any]:
    service, sheet_id = _build_service_from_env()
    month_sheets = _monthly_sheets(service, sheet_id)
    month_tabs = [sheet["title"] for sheet in month_sheets]
    updates = []
    duplicate_count = 0

    for sheet in month_sheets:
        month = sheet["title"]
        _ensure_required_columns(service, sheet_id, sheet)
        rows = _read_month_rows(service, sheet_id, month)
        duplicate_row_numbers = duplicate_rows_to_mark(rows)
        for row_number in duplicate_row_numbers:
            updates.append(
                {
                    "range": f"{_quote_sheet_name(month)}!I{row_number}",
                    "values": [[DUPLICATE_NOTE]],
                }
            )
            duplicate_count += 1

    _apply_value_updates(service, sheet_id, updates)
    update_summary_sheet()
    return {
        "duplicates_marked": duplicate_count,
        "months": month_tabs,
        "summary_updated": True,
    }


def build_transaction_key_from_row(row: list[Any]) -> str | None:
    date = str(_cell(row, 0)).strip()
    time = str(_cell(row, 1)).strip()
    merchant = str(_cell(row, 2)).strip()
    amount = _normalize_amount(_cell(row, 4))

    if not date or not time or not merchant or amount is None:
        return None

    return f"{date}|{time}|{merchant}|{amount}"


def missing_key_updates(rows: list[list[Any]]) -> list[tuple[int, str]]:
    updates = []
    for row_number, row in _data_rows_with_numbers(rows):
        if _cell(row, TRANSACTION_KEY_COLUMN_INDEX):
            continue
        key = build_transaction_key_from_row(row)
        if key:
            updates.append((row_number, key))
    return updates


def needs_column_expansion(column_count: int | None) -> bool:
    return (column_count or 0) < REQUIRED_COLUMN_COUNT


def needs_transaction_key_header(rows: list[list[Any]]) -> bool:
    return not rows or not _is_header_row(rows[0]) or _cell(rows[0], TRANSACTION_KEY_COLUMN_INDEX) != "TransactionKey"


def duplicate_rows_to_mark(rows: list[list[Any]]) -> list[int]:
    seen_keys: set[str] = set()
    duplicate_rows = []

    for row_number, row in _data_rows_with_numbers(rows):
        if _is_duplicate_marked(row):
            continue

        key = str(_cell(row, TRANSACTION_KEY_COLUMN_INDEX)).strip()
        if not key:
            key = build_transaction_key_from_row(row) or ""
        if not key:
            continue

        if key in seen_keys:
            duplicate_rows.append(row_number)
        else:
            seen_keys.add(key)

    return duplicate_rows


def _build_service_from_env():
    load_dotenv()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if not sheet_id:
        raise SheetsError("GOOGLE_SHEET_ID is not set.")
    if not credentials_path:
        raise SheetsError("GOOGLE_APPLICATION_CREDENTIALS is not set.")

    return _build_sheets_service(credentials_path), sheet_id


def _monthly_tabs(service, sheet_id: str) -> list[str]:
    return [sheet["title"] for sheet in _monthly_sheets(service, sheet_id)]


def _monthly_sheets(service, sheet_id: str) -> list[dict[str, Any]]:
    metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    month_sheets = []

    for sheet in metadata.get("sheets", []):
        properties = sheet.get("properties", {})
        title = properties.get("title", "")
        if not MONTH_TAB_PATTERN.fullmatch(title):
            continue

        grid_properties = properties.get("gridProperties", {})
        month_sheets.append(
            {
                "title": title,
                "sheet_id": properties.get("sheetId"),
                "column_count": grid_properties.get("columnCount"),
            }
        )

    return sorted(month_sheets, key=lambda sheet: sheet["title"])


def _read_month_rows(service, sheet_id: str, month: str) -> list[list[Any]]:
    response = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"{_quote_sheet_name(month)}!A:L")
        .execute()
    )
    return response.get("values", [])


def _apply_value_updates(service, sheet_id: str, updates: list[dict[str, Any]]) -> None:
    if not updates:
        return

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=sheet_id,
        body={
            "valueInputOption": "USER_ENTERED",
            "data": updates,
        },
    ).execute()


def _ensure_required_columns(service, sheet_id: str, sheet: dict[str, Any]) -> None:
    if not needs_column_expansion(sheet.get("column_count")):
        return

    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={
            "requests": [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet["sheet_id"],
                            "gridProperties": {
                                "columnCount": REQUIRED_COLUMN_COUNT,
                            },
                        },
                        "fields": "gridProperties.columnCount",
                    }
                }
            ]
        },
    ).execute()
    sheet["column_count"] = REQUIRED_COLUMN_COUNT


def _data_rows_with_numbers(rows: list[list[Any]]) -> list[tuple[int, list[Any]]]:
    if not rows:
        return []

    start_index = 1 if _is_header_row(rows[0]) else 0
    return [
        (index + 1, row)
        for index, row in enumerate(rows[start_index:], start=start_index)
    ]


def _is_header_row(row: list[Any]) -> bool:
    return str(_cell(row, 0)).strip().lower() == "date"


def _is_duplicate_marked(row: list[Any]) -> bool:
    return str(_cell(row, NOTE_COLUMN_INDEX)).strip() == DUPLICATE_NOTE


def _normalize_amount(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        return str(float(str(value).replace(",", "")))
    except ValueError:
        return None


def _cell(row: list[Any], index: int) -> Any:
    if index >= len(row):
        return ""
    return row[index]
