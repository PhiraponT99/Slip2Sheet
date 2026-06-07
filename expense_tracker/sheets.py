from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from expense_tracker.merchant_aliases import normalize_merchant
from expense_tracker.merchant_categories import lookup_category
from expense_tracker.models import TransactionResult


SHEET_COLUMNS = [
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

SETTINGS_TAB_NAME = "Settings"
SETTINGS_COLUMNS = ["Key", "Value", "UpdatedAt"]
CURRENT_BALANCE_KEY = "current_balance"

FOOD_KEYWORDS = (
    "กะเพรา",
    "ข้าว",
    "อาหาร",
    "food",
    "cp axtra",
    "lotus",
    "lotuss",
    "lotus's",
)

DRINK_KEYWORDS = (
    "กาแฟ",
    "coffee",
    "cafe",
    "amazon",
)

PAYMENT_METHOD_KEYWORDS = {
    "พร้อมเพย์": "PromptPay",
    "promptpay": "PromptPay",
    "qr": "QR",
    "บัตรเครดิต": "Credit Card",
    "credit": "Credit Card",
    "บัตรเดบิต": "Debit Card",
    "debit": "Debit Card",
    "เงินสด": "Cash",
    "cash": "Cash",
    "truemoney": "TrueMoney",
}

DISCOUNT_NOTE_KEYWORDS = (
    "discount",
    "ส่วนลด",
    "สิทธิ",
    "ช่วยไทย",
    "พลัส",
    "โปรโมชัน",
    "โปรโมชั่น",
)


class SheetsError(RuntimeError):
    """Raised when a transaction cannot be saved to Google Sheets."""


def append_transaction_to_sheet(
    transaction: TransactionResult,
    source: str | Path,
) -> dict[str, Any]:
    load_dotenv()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if not sheet_id:
        raise SheetsError("GOOGLE_SHEET_ID is not set.")
    service = _build_sheets_service(credentials_path)
    tab_name = monthly_tab_name(transaction.date)
    _ensure_monthly_tab(service, sheet_id, tab_name)

    row = build_sheet_row(transaction, source)
    key = transaction_key(transaction)
    existing_rows = _read_monthly_rows(service, sheet_id, tab_name)

    if key in existing_transaction_keys(existing_rows):
        return {
            "saved": False,
            "duplicate": True,
            "sheet_tab": tab_name,
            "message": "Duplicate transaction detected. Skipped.",
        }

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{_quote_sheet_name(tab_name)}!A:L",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()

    return {
        "saved": True,
        "duplicate": False,
        "sheet_tab": tab_name,
    }


def save_balance_to_sheet(amount: float | int | str) -> dict[str, Any]:
    load_dotenv()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID") or os.environ.get("SPREADSHEET_ID")
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if not sheet_id:
        raise SheetsError("GOOGLE_SHEET_ID or SPREADSHEET_ID is not set.")

    balance_amount = _parse_sheet_balance_amount(amount)
    updated_at = datetime.now().isoformat(timespec="seconds")
    service = _build_sheets_service(credentials_path)
    _ensure_settings_tab(service, sheet_id)
    rows = _read_settings_rows(service, sheet_id)

    row_number = _settings_key_row_number(rows, CURRENT_BALANCE_KEY)
    if row_number is None:
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=f"{_quote_sheet_name(SETTINGS_TAB_NAME)}!A:C",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [[CURRENT_BALANCE_KEY, balance_amount, updated_at]]},
        ).execute()
    else:
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{_quote_sheet_name(SETTINGS_TAB_NAME)}!B{row_number}:C{row_number}",
            valueInputOption="USER_ENTERED",
            body={"values": [[balance_amount, updated_at]]},
        ).execute()

    return {
        "key": CURRENT_BALANCE_KEY,
        "amount": balance_amount,
        "updated_at": updated_at,
        "sheet_tab": SETTINGS_TAB_NAME,
    }


def read_balance_from_sheet() -> float | None:
    load_dotenv()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID") or os.environ.get("SPREADSHEET_ID")
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    if not sheet_id:
        raise SheetsError("GOOGLE_SHEET_ID or SPREADSHEET_ID is not set.")

    service = _build_sheets_service(credentials_path)
    _ensure_settings_tab(service, sheet_id)
    rows = _read_settings_rows(service, sheet_id)

    for row in rows[1:]:
        if not row or str(row[0]).strip() != CURRENT_BALANCE_KEY:
            continue
        if len(row) < 2:
            return None
        return _parse_sheet_balance_amount(row[1])
    return None


def monthly_tab_name(transaction_date: str | None) -> str:
    if not transaction_date:
        raise SheetsError("Transaction date is required to choose a monthly sheet tab.")
    if len(transaction_date) < 7:
        raise SheetsError(f"Invalid transaction date: {transaction_date}")
    return transaction_date[:7]


def load_dotenv(dotenv_path: str | Path = ".env") -> None:
    path = Path(dotenv_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def infer_category(merchant: str | None, raw_text: str | None = None) -> str:
    mapped_category = lookup_category(merchant)
    if mapped_category:
        return mapped_category

    text = f"{merchant or ''}\n{raw_text or ''}".lower()
    if any(keyword in text for keyword in FOOD_KEYWORDS):
        return "food"
    if any(keyword in text for keyword in DRINK_KEYWORDS):
        return "drink"
    return "other"


def build_sheet_row(transaction: TransactionResult, source: str | Path) -> list[Any]:
    merchant = normalize_merchant(transaction.merchant)
    return [
        transaction.date or "",
        transaction.time or "",
        merchant or "",
        infer_category(merchant, transaction.raw_text),
        _sheet_number(transaction.amount),
        _sheet_number(transaction.original_amount),
        _sheet_number(transaction.discount),
        detect_payment_method(transaction.raw_text),
        detect_note(transaction.raw_text),
        Path(source).name,
        datetime.now().isoformat(timespec="seconds"),
        transaction_key(transaction),
    ]


def transaction_key(transaction: TransactionResult) -> str:
    merchant = normalize_merchant(transaction.merchant)
    return "|".join(
        [
            transaction.date or "",
            transaction.time or "",
            merchant or "",
            str(transaction.amount) if transaction.amount is not None else "",
        ]
    )


def existing_transaction_keys(rows: list[list[Any]]) -> set[str]:
    if not rows:
        return set()

    header = [str(value).strip() for value in rows[0]]
    try:
        key_index = header.index("TransactionKey")
    except ValueError:
        return set()

    keys = set()
    for row in rows[1:]:
        if key_index >= len(row):
            continue
        key = str(row[key_index]).strip()
        if key:
            keys.add(key)
    return keys


def detect_payment_method(raw_text: str | None) -> str | None:
    text = (raw_text or "").lower()
    for keyword, payment_method in PAYMENT_METHOD_KEYWORDS.items():
        if keyword in text:
            return payment_method
    return None


def detect_note(raw_text: str | None) -> str | None:
    if not raw_text:
        return None

    for line in raw_text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if not stripped:
            continue
        if any(keyword in lowered for keyword in DISCOUNT_NOTE_KEYWORDS):
            return stripped
    return None


def _build_sheets_service(credentials_path: str | None = None):
    try:
        import google.auth
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise SheetsError(
            "Google Sheets dependencies are missing. Run: pip install -r requirements.txt"
        ) from exc

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    try:
        if credentials_path:
            if not Path(credentials_path).exists():
                raise SheetsError(
                    f"Google service account credentials file not found: {credentials_path}"
                )
            credentials = Credentials.from_service_account_file(
                credentials_path,
                scopes=scopes,
            )
        else:
            credentials, _ = google.auth.default(scopes=scopes)
    except SheetsError:
        raise
    except Exception as exc:
        raise SheetsError(f"Google Sheets authentication failed: {exc}") from exc

    return build("sheets", "v4", credentials=credentials)


def _ensure_monthly_tab(service, sheet_id: str, tab_name: str) -> None:
    metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    tabs = {
        sheet["properties"]["title"]
        for sheet in metadata.get("sheets", [])
        if "properties" in sheet
    }

    if tab_name not in tabs:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": tab_name,
                                "gridProperties": {
                                    "rowCount": 1000,
                                    "columnCount": len(SHEET_COLUMNS),
                                },
                            }
                        }
                    }
                ]
            },
        ).execute()

    _ensure_header_row(service, sheet_id, tab_name)


def _ensure_settings_tab(service, sheet_id: str) -> None:
    metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    tabs = {
        sheet["properties"]["title"]
        for sheet in metadata.get("sheets", [])
        if "properties" in sheet
    }

    if SETTINGS_TAB_NAME not in tabs:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": SETTINGS_TAB_NAME,
                                "gridProperties": {
                                    "rowCount": 100,
                                    "columnCount": len(SETTINGS_COLUMNS),
                                },
                            }
                        }
                    }
                ]
            },
        ).execute()

    _ensure_settings_header_row(service, sheet_id)


def _ensure_settings_header_row(service, sheet_id: str) -> None:
    header_range = f"{_quote_sheet_name(SETTINGS_TAB_NAME)}!A1:C1"
    response = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=header_range)
        .execute()
    )
    values = response.get("values", [])
    if values and values[0] == SETTINGS_COLUMNS:
        return

    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=header_range,
        valueInputOption="RAW",
        body={"values": [SETTINGS_COLUMNS]},
    ).execute()


def _ensure_header_row(service, sheet_id: str, tab_name: str) -> None:
    header_range = f"{_quote_sheet_name(tab_name)}!A1:L1"
    response = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=header_range)
        .execute()
    )
    values = response.get("values", [])
    if values and values[0] == SHEET_COLUMNS:
        return

    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=header_range,
        valueInputOption="RAW",
        body={"values": [SHEET_COLUMNS]},
    ).execute()


def _read_monthly_rows(service, sheet_id: str, tab_name: str) -> list[list[Any]]:
    response = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"{_quote_sheet_name(tab_name)}!A:L")
        .execute()
    )
    return response.get("values", [])


def _read_settings_rows(service, sheet_id: str) -> list[list[Any]]:
    response = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"{_quote_sheet_name(SETTINGS_TAB_NAME)}!A:C")
        .execute()
    )
    return response.get("values", [])


def _settings_key_row_number(rows: list[list[Any]], key: str) -> int | None:
    for index, row in enumerate(rows[1:], start=2):
        if row and str(row[0]).strip() == key:
            return index
    return None


def _sheet_number(value: float | None) -> float | str:
    if value is None:
        return ""
    return value


def _parse_sheet_balance_amount(amount: float | int | str | None) -> float:
    if amount is None:
        raise SheetsError("Balance amount is required.")
    if isinstance(amount, str):
        amount = amount.replace(",", "").strip()
    try:
        value = float(amount)
    except (TypeError, ValueError) as exc:
        raise SheetsError(f"Invalid balance amount: {amount}") from exc
    if value < 0:
        raise SheetsError("Balance amount cannot be negative.")
    return value


def _quote_sheet_name(name: str) -> str:
    escaped = name.replace("'", "''")
    return f"'{escaped}'"
