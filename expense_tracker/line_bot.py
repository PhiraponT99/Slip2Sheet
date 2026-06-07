from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import is_dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from expense_tracker.balance import read_balance, save_balance
from expense_tracker.ocr import run_ocr
from expense_tracker.parser import extract_transaction
from expense_tracker.parser_diagnostics import log_parser_investigation
from expense_tracker.reports import today_report
from expense_tracker.sheets import (
    SheetsError,
    append_transaction_to_sheet,
    infer_category,
    load_dotenv,
    read_balance_from_sheet,
    save_balance_to_sheet,
)


LINE_REPLY_ENDPOINT = "https://api.line.me/v2/bot/message/reply"
LINE_CONTENT_ENDPOINT = "https://api-data.line.me/v2/bot/message/{message_id}/content"
DEFAULT_REPLY_TEXT = "Hello from Slip2Sheet"
DAILY_SUMMARY_COMMANDS = {"\u0e2a\u0e23\u0e38\u0e1b\u0e27\u0e31\u0e19\u0e19\u0e35\u0e49", "summary today"}
BALANCE_COMMAND_PREFIXES = (
    "\u0e15\u0e31\u0e49\u0e07\u0e22\u0e2d\u0e14\u0e40\u0e07\u0e34\u0e19",
    "\u0e22\u0e2d\u0e14\u0e40\u0e07\u0e34\u0e19",
    "\u0e40\u0e07\u0e34\u0e19\u0e04\u0e07\u0e40\u0e2b\u0e25\u0e37\u0e2d",
)
INVALID_BALANCE_TEXT = (
    "\u0e23\u0e30\u0e1a\u0e38\u0e22\u0e2d\u0e14\u0e40\u0e07\u0e34\u0e19"
    "\u0e44\u0e21\u0e48\u0e16\u0e39\u0e01\u0e15\u0e49\u0e2d\u0e07 "
    "\u0e40\u0e0a\u0e48\u0e19 "
    "\u0e15\u0e31\u0e49\u0e07\u0e22\u0e2d\u0e14\u0e40\u0e07\u0e34\u0e19 9737.90"
)
IMAGE_REPLY_TEXT = "Image received by Slip2Sheet"
IMAGE_DOWNLOAD_SUCCESS_TEXT = "Slip image received."
IMAGE_DOWNLOAD_FAILURE_TEXT = "Failed to download image."
OCR_FAILURE_TEXT = "OCR failed."
PARSE_FAILURE_TEXT = "OCR completed, but transaction parsing failed."
SAVE_FAILURE_TEXT = "Transaction detected, but save failed."
DATE_PARSE_FAILURE_TEXT = "Transaction detected, but date could not be parsed."
DEFAULT_LINE_IMAGE_DIR = Path("incoming") / "line"
DEFAULT_LINE_DUPLICATES_PATH = Path("processed") / "line_duplicates.json"
LINE_LOCAL_TIMEZONE = ZoneInfo("Asia/Bangkok")
PROCESSED_LINE_EVENT_KEYS: set[str] = set()


class LineBotError(Exception):
    pass


def get_line_config() -> dict[str, str]:
    return {
        "channel_secret": os.environ.get("LINE_CHANNEL_SECRET", ""),
        "channel_access_token": os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", ""),
    }


def verify_line_signature(
    body: bytes,
    signature: str | None,
    channel_secret: str,
) -> bool:
    signature = signature.strip() if signature else None

    expected_signature = (
        generate_line_signature(body, channel_secret) if channel_secret else ""
    )

    return bool(signature and channel_secret) and hmac.compare_digest(
        expected_signature,
        signature,
    )


def generate_line_signature(body: bytes, channel_secret: str) -> str:
    digest = hmac.new(
        channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def signature_diagnostics(
    body: bytes,
    signature: str | None,
    channel_secret: str,
) -> dict[str, Any]:
    signature = signature.strip() if signature else None
    expected_signature = (
        generate_line_signature(body, channel_secret) if channel_secret else ""
    )
    return {
        "body_length": len(body),
        "signature_present": bool(signature),
        "secret_present": bool(channel_secret),
        "received_signature_prefix": signature[:8] if signature else "",
        "generated_signature_prefix": expected_signature[:8],
    }


def handle_line_webhook(
    body: bytes,
    signature: str | None,
    channel_secret: str,
    channel_access_token: str,
    reply_fn: Callable[..., None] = None,
    image_download_fn: Callable[[str, str], Path] = None,
    ocr_fn: Callable[[Path], str] = None,
    parse_fn: Callable[[str], Any] = None,
    save_transaction_fn: Callable[[Any, str | Path], dict[str, Any]] = None,
    daily_summary_fn: Callable[[], dict[str, Any]] = None,
    duplicate_store_path: Path | None = DEFAULT_LINE_DUPLICATES_PATH,
    processed_event_keys: set[str] | None = None,
) -> dict[str, Any]:
    if not verify_line_signature(body, signature, channel_secret):
        raise LineBotError("Invalid LINE signature.")

    if reply_fn is None:
        reply_fn = send_line_reply

    payload = json.loads(body.decode("utf-8") or "{}")
    events = payload.get("events", [])
    reply_count = 0
    used_reply_tokens: set[str] = set()
    if processed_event_keys is None:
        processed_event_keys = PROCESSED_LINE_EVENT_KEYS

    for event in events:
        reply_token = event.get("replyToken")
        reply_messages: list[dict[str, Any]] = []
        event_key = line_event_key(event)
        is_duplicate_event = event_key in processed_event_keys
        _log_line_event_status(event, event_key, is_duplicate_event)
        if _line_is_redelivery(event) is True:
            print(
                "[WARN] LINE redelivery event detected. Skipped processing.",
                f"event_key={event_key}",
                f"reply_token={_reply_token_prefix(reply_token)}",
                flush=True,
            )
            continue
        if is_duplicate_event:
            print(
                "[WARN] Duplicate LINE event detected. Skipped processing.",
                f"event_key={event_key}",
                f"reply_token={_reply_token_prefix(reply_token)}",
                flush=True,
            )
            continue
        processed_event_keys.add(event_key)

        if _is_text_message_event(event):
            reply_messages = _build_text_event_reply_messages(
                event,
                daily_summary_fn,
            )
        elif _is_image_message_event(event):
            reply_messages = _build_image_event_reply_messages(
                event,
                channel_access_token,
                image_download_fn,
                ocr_fn,
                parse_fn,
                save_transaction_fn,
                duplicate_store_path,
            )

        if not reply_token or not reply_messages:
            continue
        if _is_duplicate_reply_token(reply_token, used_reply_tokens):
            _log_duplicate_reply_token(reply_token, event)
            continue

        used_reply_tokens.add(reply_token)
        _send_line_reply_once(
            reply_fn,
            reply_token,
            reply_messages,
            channel_access_token,
            event,
        )
        reply_count += 1

    return {
        "status": "ok",
        "events": len(events),
        "replies": reply_count,
        
    }


def _build_text_event_reply_messages(
    event: dict[str, Any],
    daily_summary_fn: Callable[[], dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    message_text = event.get("message", {}).get("text", "")
    balance_command = parse_balance_command(message_text)
    if is_current_balance_query_command(message_text):
        current_balance = _read_line_balance()
        if current_balance is None:
            reply_text = (
                "\u0e22\u0e31\u0e07\u0e44\u0e21\u0e48"
                "\u0e44\u0e14\u0e49\u0e15\u0e31\u0e49\u0e07"
                "\u0e22\u0e2d\u0e14\u0e40\u0e07\u0e34\u0e19 "
                "\u0e1e\u0e34\u0e21\u0e1e\u0e4c: "
                "\u0e15\u0e31\u0e49\u0e07\u0e22\u0e2d\u0e14"
                "\u0e40\u0e07\u0e34\u0e19 9460.90"
            )
        else:
            reply_text = (
                "\u0e22\u0e2d\u0e14\u0e40\u0e07\u0e34\u0e19"
                "\u0e1b\u0e31\u0e08\u0e08\u0e38\u0e1a\u0e31\u0e19: "
                f"{_format_balance_baht(current_balance)} \u0e1a\u0e32\u0e17"
            )
    elif balance_command["matched"]:
        amount = balance_command["amount"]
        if amount is None:
            reply_text = INVALID_BALANCE_TEXT
        else:
            try:
                _save_line_balance(amount)
                reply_text = build_balance_saved_reply_text(amount)
            except (OSError, TypeError, ValueError, SheetsError) as exc:
                print("[ERROR] LINE balance save failed:", str(exc), flush=True)
                reply_text = INVALID_BALANCE_TEXT
    elif is_daily_summary_command(message_text):
        if daily_summary_fn is None:
            daily_summary_fn = line_daily_summary
        reply_text = build_daily_summary_reply_text(daily_summary_fn())
    else:
        reply_text = DEFAULT_REPLY_TEXT
    return [build_text_message(reply_text)]


def _build_image_event_reply_messages(
    event: dict[str, Any],
    channel_access_token: str,
    image_download_fn: Callable[[str, str], Path] = None,
    ocr_fn: Callable[[Path], str] = None,
    parse_fn: Callable[[str], Any] = None,
    save_transaction_fn: Callable[[Any, str | Path], dict[str, Any]] = None,
    duplicate_store_path: Path | None = DEFAULT_LINE_DUPLICATES_PATH,
) -> list[dict[str, Any]]:
    message_id = event.get("message", {}).get("id")
    reply_text = IMAGE_DOWNLOAD_SUCCESS_TEXT
    try:
        if not message_id:
            raise LineBotError("LINE image message id is missing.")
        if image_download_fn is None:
            image_download_fn = download_line_image
        saved_file = image_download_fn(message_id, channel_access_token)
    except Exception as exc:
        print("[ERROR] Failed to download LINE image:", str(exc))
        reply_text = IMAGE_DOWNLOAD_FAILURE_TEXT
    else:
        try:
            if ocr_fn is None:
                ocr_fn = run_ocr
            ocr_text = ocr_fn(saved_file)
            print("[INFO] LINE image message_id:", message_id)
            print("[INFO] LINE image saved_file:", str(saved_file))
            print("[INFO] LINE image ocr_success:", True)
            try:
                log_parser_investigation(ocr_text)
            except UnicodeEncodeError:
                print("[WARN] Parser investigation log skipped due to console encoding.")
        except Exception as exc:
            print("[ERROR] LINE OCR failed:", str(exc))
            print("[INFO] LINE image message_id:", message_id)
            print("[INFO] LINE image saved_file:", str(saved_file))
            print("[INFO] LINE image ocr_success:", False)
            reply_text = OCR_FAILURE_TEXT
        else:
            try:
                if parse_fn is None:
                    parse_fn = extract_transaction
                transaction = parse_fn(ocr_text)
                if not _has_parsed_transaction(transaction):
                    raise LineBotError("Transaction parsing failed.")
                transaction = _apply_event_date_fallback(transaction, event, ocr_text)
                category = infer_category(transaction.merchant, ocr_text)
                _log_parsed_transaction(transaction, category)
                if not _has_parsed_date(transaction):
                    reply_text = DATE_PARSE_FAILURE_TEXT
                    return [build_text_message(reply_text)]
                save_result = save_line_transaction(
                    transaction,
                    saved_file,
                    category,
                    save_transaction_fn,
                )
                if save_result.get("duplicate"):
                    reply_text = build_duplicate_reply_text(transaction)
                elif save_result.get("saved"):
                    reply_text = build_transaction_reply_text(
                        transaction,
                        category,
                        title="Transaction Saved",
                    )
                else:
                    reply_text = SAVE_FAILURE_TEXT
            except Exception as exc:
                print("[ERROR] LINE transaction parse failed:", str(exc))
                reply_text = PARSE_FAILURE_TEXT

    return [build_text_message(reply_text)]


def build_text_message(text: str) -> dict[str, str]:
    return {
        "type": "text",
        "text": text,
    }


def build_text_reply_payload(
    reply_token: str,
    text: str = DEFAULT_REPLY_TEXT,
) -> dict[str, Any]:
    return build_reply_payload(reply_token, [build_text_message(text)])


def build_reply_payload(
    reply_token: str,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "replyToken": reply_token,
        "messages": messages,
    }


def _send_line_reply_once(
    reply_fn: Callable[..., None],
    reply_token: str,
    messages: list[dict[str, Any]],
    channel_access_token: str,
    event: dict[str, Any],
) -> None:
    _call_reply_fn(
        reply_fn,
        reply_token,
        messages,
        channel_access_token,
        event.get("type"),
        event.get("message", {}).get("type"),
    )


def _call_reply_fn(
    reply_fn: Callable[..., None],
    reply_token: str,
    messages: list[dict[str, Any]],
    channel_access_token: str,
    event_type: str | None,
    message_type: str | None,
) -> None:
    try:
        reply_fn(
            reply_token,
            messages,
            channel_access_token,
            event_type,
            message_type,
        )
    except TypeError:
        reply_fn(reply_token, _first_text_message(messages), channel_access_token)


def _is_duplicate_reply_token(reply_token: str, used_reply_tokens: set[str]) -> bool:
    return reply_token in used_reply_tokens


def _log_duplicate_reply_token(reply_token: str, event: dict[str, Any]) -> None:
    print(
        "[WARN] Duplicate LINE replyToken detected. Skipped reply.",
        f"reply_token={_reply_token_prefix(reply_token)}",
        f"event_type={event.get('type')}",
        f"message_type={event.get('message', {}).get('type')}",
        flush=True,
    )


def line_event_key(event: dict[str, Any]) -> str:
    webhook_event_id = event.get("webhookEventId")
    if webhook_event_id:
        return f"webhook:{webhook_event_id}"

    message_id = event.get("message", {}).get("id")
    if message_id:
        return f"message:{message_id}"

    reply_token = event.get("replyToken")
    if reply_token:
        return f"reply:{reply_token}"

    return f"event:{json.dumps(event, sort_keys=True, ensure_ascii=False)}"


def _log_line_event_status(
    event: dict[str, Any],
    event_key: str,
    is_duplicate_event: bool,
) -> None:
    print(
        "[INFO] LINE event",
        f"event_key={event_key}",
        f"reply_token={_reply_token_prefix(event.get('replyToken'))}",
        f"event_type={event.get('type')}",
        f"message_type={event.get('message', {}).get('type')}",
        f"duplicate={is_duplicate_event}",
        f"is_redelivery={_line_is_redelivery(event)}",
        flush=True,
    )


def _line_is_redelivery(event: dict[str, Any]) -> Any:
    return event.get("deliveryContext", {}).get("isRedelivery")


def build_ocr_reply_text(ocr_text: str, limit: int = 500) -> str:
    text = ocr_text or ""
    if len(text) > limit:
        text = text[:limit] + "..."
    return f"OCR completed.\n\nDetected text:\n\n{text}"


def build_transaction_reply_text(
    transaction: Any,
    category: str | None = None,
    title: str = "Transaction Detected",
) -> str:
    return "\n".join(
        [
            f"\U0001f4b8 {title}",
            "",
            f"Amount: {_format_amount_value(transaction.amount)}",
            f"Date: {_format_line_value(transaction.date)}",
            f"Time: {_format_line_value(transaction.time)}",
            "",
            f"Merchant: {_format_line_value(transaction.merchant)}",
            "",
            f"Category: {_format_line_value(category)}",
        ]
    )


def build_duplicate_reply_text(transaction: Any) -> str:
    return "\n".join(
        [
            "Duplicate slip detected.",
            "",
            f"Amount: {_format_amount_value(transaction.amount)}",
            f"Date: {_format_line_value(transaction.date)}",
            f"Time: {_format_line_value(transaction.time)}",
            f"Merchant: {_format_line_value(transaction.merchant)}",
        ]
    )


def save_line_transaction(
    transaction: Any,
    source: str | Path,
    category: str | None,
    save_transaction_fn: Callable[[Any, str | Path], dict[str, Any]] = None,
) -> dict[str, Any]:
    tab_name = _line_transaction_tab_name(transaction)
    print(
        "[INFO] Google Sheet append attempt",
        f"spreadsheet_id={_spreadsheet_id_prefix(_line_spreadsheet_id())}",
        f"sheet_tab={_format_line_value(tab_name)}",
        f"date={_format_line_value(getattr(transaction, 'date', None))}",
        f"amount={_format_line_value(getattr(transaction, 'amount', None))}",
        flush=True,
    )
    try:
        if save_transaction_fn is None:
            _ensure_google_sheet_env_alias()
            result = append_transaction_to_sheet(transaction, source)
        else:
            result = save_transaction_fn(transaction, source)
    except Exception as exc:
        print(
            "[ERROR] Google Sheet append failure",
            f"sheet_tab={_format_line_value(tab_name)}",
            f"error={exc}",
            flush=True,
        )
        return {
            "saved": False,
            "error": str(exc),
        }

    print(
        "[INFO] Google Sheet append success",
        f"saved={result.get('saved')}",
        f"sheet_tab={result.get('sheet_tab', tab_name)}",
        flush=True,
    )
    return result


def _log_parsed_transaction(transaction: Any, category: str | None) -> None:
    print(
        "[INFO] LINE transaction parsed",
        f"date={_safe_log_text(_format_line_value(getattr(transaction, 'date', None)))}",
        f"time={_safe_log_text(_format_line_value(getattr(transaction, 'time', None)))}",
        f"amount={_safe_log_text(_format_line_value(getattr(transaction, 'amount', None)))}",
        f"merchant={_safe_log_text(_format_line_value(getattr(transaction, 'merchant', None)))}",
        f"category={_safe_log_text(_format_line_value(category))}",
        flush=True,
    )


def line_daily_summary() -> dict[str, Any]:
    query_date = date.today().isoformat()
    tab_name = query_date[:7]
    print(
        "[INFO] LINE daily summary query",
        f"date={query_date}",
        f"sheet_tab={tab_name}",
        flush=True,
    )
    try:
        _ensure_google_sheet_env_alias()
        summary = today_report()
    except Exception as exc:
        print(
            "[WARN] LINE daily summary read returned empty result",
            f"sheet_tab={tab_name}",
            f"error={exc}",
            flush=True,
        )
        summary = {
            "date": query_date,
            "total_expense": 0.0,
            "transaction_count": 0,
            "transactions": [],
        }
    summary["current_balance"] = _read_line_balance()
    print(
        "[INFO] LINE daily summary result",
        f"sheet_tab={tab_name}",
        f"result_count={_daily_summary_transaction_count(summary)}",
        f"total={summary.get('total_expense')}",
        flush=True,
    )
    return summary


def build_daily_summary_reply_text(summary: dict[str, Any]) -> str:
    transaction_count = _daily_summary_transaction_count(summary)
    total_expense = _number_value(summary.get("total_expense"))
    current_balance = summary.get("current_balance")
    if current_balance is None:
        current_balance = read_balance()

    if transaction_count == 0 and total_expense == 0:
        lines = [
            "วันนี้ใช้เงิน:",
            "",
            "ไม่มีรายการใช้เงินวันนี้",
        ]
        if current_balance is not None:
            lines.append(_daily_summary_balance_line(current_balance, total_expense))
        return "\n".join(lines)

    lines = ["วันนี้ใช้เงิน:"]
    for transaction in summary.get("transactions", []):
        lines.append(
            "- "
            f"{_daily_summary_item_label(transaction)} "
            f"{_format_thai_baht(transaction.get('amount'))} บาท"
        )
    lines.extend(["", f"รวม {_format_thai_baht(summary.get('total_expense'))} บาท"])

    if current_balance is not None:
        lines.append(_daily_summary_balance_line(current_balance, total_expense))

    return "\n".join(lines)


def _daily_summary_balance_line(current_balance: float, total_expense: float) -> str:
    return (
        "\u0e22\u0e2d\u0e14\u0e40\u0e07\u0e34\u0e19"
        "\u0e04\u0e07\u0e40\u0e2b\u0e25\u0e37\u0e2d: "
        f"{_format_balance_baht(current_balance)} \u0e1a\u0e32\u0e17"
    )


def _daily_summary_transaction_count(summary: dict[str, Any]) -> int:
    transactions = summary.get("transactions")
    if isinstance(transactions, list):
        return len(transactions)
    return int(_number_value(summary.get("transaction_count")))


def _daily_summary_item_label(transaction: dict[str, Any]) -> str:
    for key in ("note", "item", "merchant", "category"):
        label = _clean_daily_summary_label(
            transaction.get(key) or transaction.get(key.title())
        )
        if label and not _is_noisy_daily_summary_label(label):
            return label
    return "รายการ"


def _clean_daily_summary_label(value: Any) -> str | None:
    if value is None or value == "":
        return None

    cleaned = str(value).strip()
    cleaned = re.sub(
        r"[-−]?\s*\d+(?:,\d{3})*(?:\.\d{1,2})?\s*(?:บาท|baht|thb)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"[-−]?\s*\d+(?:,\d{3})*(?:\.\d{1,2})?",
        "",
        cleaned,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -|:：")
    return cleaned or None


def _is_noisy_daily_summary_label(value: str) -> bool:
    match_text = re.sub(r"[\s:：,./\\|\-]+", "", value.lower())
    noisy_keywords = (
        "สิทธิไทยช่วยไทยพลัส",
        "สิทธิแทยช่วยไทยพลัส",
        "ส่วนลด",
        "discount",
        "จำนวนเงินที่ชำระ",
        "จํานวนเงินที่ชําระ",
        "จำนวนเงิน",
        "จํานวนเงิน",
        "ค่าสินค้าบริการ",
        "ค่าสินค้า/บริการ",
        "บาท",
    )
    return any(
        re.sub(r"[\s:：,./\\|\-]+", "", keyword.lower()) in match_text
        for keyword in noisy_keywords
    )


def is_daily_summary_command(text: str | None) -> bool:
    return str(text or "").strip().lower() in DAILY_SUMMARY_COMMANDS


def is_current_balance_query_command(text: str | None) -> bool:
    return str(text or "").strip() == "\u0e22\u0e2d\u0e14\u0e40\u0e07\u0e34\u0e19"


def parse_balance_command(text: str | None) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", str(text or "").strip())
    for prefix in BALANCE_COMMAND_PREFIXES:
        if normalized == prefix:
            return {"matched": True, "amount": None}
        if normalized.startswith(f"{prefix} "):
            amount_text = normalized[len(prefix) :].strip(" :\uff1a")
            if not re.fullmatch(r"\d[\d,]*(?:\.\d+)?", amount_text):
                return {"matched": True, "amount": None}
            try:
                return {
                    "matched": True,
                    "amount": float(amount_text.replace(",", "")),
                }
            except ValueError:
                return {"matched": True, "amount": None}
    return {"matched": False, "amount": None}


def is_balance_command(text: str | None) -> bool:
    return bool(parse_balance_command(text)["matched"])


def build_balance_saved_reply_text(amount: float | int | str) -> str:
    return (
        "\u0e1a\u0e31\u0e19\u0e17\u0e36\u0e01"
        "\u0e22\u0e2d\u0e14\u0e40\u0e07\u0e34\u0e19"
        "\u0e41\u0e25\u0e49\u0e27: "
        f"{_format_balance_baht(amount)} \u0e1a\u0e32\u0e17"
    )


def _save_line_balance(amount: float | int | str) -> dict[str, Any]:
    try:
        _ensure_google_sheet_env_alias()
        return save_balance_to_sheet(amount)
    except Exception as exc:
        print(
            "[WARN] Google Sheet balance save failed; using local fallback.",
            f"error={exc}",
            flush=True,
        )
        return save_balance(amount, source="line")


def _read_line_balance() -> float | None:
    try:
        _ensure_google_sheet_env_alias()
        return read_balance_from_sheet()
    except Exception as exc:
        print(
            "[WARN] Google Sheet balance read failed; using local fallback.",
            f"error={exc}",
            flush=True,
        )
        return read_balance()


def _line_spreadsheet_id(required: bool = False) -> str:
    load_dotenv()
    sheet_id = os.environ.get("SPREADSHEET_ID") or os.environ.get("GOOGLE_SHEET_ID", "")
    if required and not sheet_id:
        raise SheetsError("SPREADSHEET_ID is not set.")
    return sheet_id


def _google_credentials_path() -> str:
    load_dotenv()
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not credentials_path:
        raise SheetsError("GOOGLE_APPLICATION_CREDENTIALS is not set.")
    if not Path(credentials_path).exists():
        raise SheetsError(
            f"Google service account credentials file not found: {credentials_path}"
        )
    return credentials_path


def _line_transaction_tab_name(transaction: Any) -> str | None:
    transaction_date = getattr(transaction, "date", None)
    if not transaction_date or len(str(transaction_date)) < 7:
        return None
    return str(transaction_date)[:7]


def _spreadsheet_id_prefix(sheet_id: str | None) -> str:
    if not sheet_id:
        return "-"
    return f"{sheet_id[:8]}..."


def _ensure_google_sheet_env_alias() -> None:
    load_dotenv()
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    if spreadsheet_id and not os.environ.get("GOOGLE_SHEET_ID"):
        os.environ["GOOGLE_SHEET_ID"] = spreadsheet_id


def line_duplicate_key(transaction: Any) -> str | None:
    date = getattr(transaction, "date", None)
    time = getattr(transaction, "time", None)
    amount = getattr(transaction, "amount", None)
    merchant = getattr(transaction, "merchant", None)
    if not (date and time and amount is not None and merchant):
        return None
    try:
        amount_text = f"{float(amount):.2f}"
    except (TypeError, ValueError):
        return None
    return "|".join(
        [
            str(date),
            str(time),
            amount_text,
            str(merchant),
        ]
    )


def is_duplicate_line_transaction(
    transaction: Any,
    store_path: Path | None = DEFAULT_LINE_DUPLICATES_PATH,
) -> bool:
    key = line_duplicate_key(transaction)
    if not key or store_path is None:
        return False
    return key in _load_line_duplicate_keys(store_path)


def record_line_transaction(
    transaction: Any,
    store_path: Path | None = DEFAULT_LINE_DUPLICATES_PATH,
) -> None:
    key = line_duplicate_key(transaction)
    if not key or store_path is None:
        return

    keys = _load_line_duplicate_keys(store_path)
    if key in keys:
        return

    keys.add(key)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(
        json.dumps({"keys": sorted(keys)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_line_duplicate_keys(store_path: Path) -> set[str]:
    if not store_path.exists():
        return set()
    try:
        data = json.loads(store_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if isinstance(data, dict):
        values = data.get("keys", [])
    else:
        values = data
    if not isinstance(values, list):
        return set()
    return {str(value) for value in values if str(value).strip()}


def _has_parsed_transaction(transaction: Any) -> bool:
    return bool(transaction and getattr(transaction, "amount", None) is not None)


def _has_parsed_date(transaction: Any) -> bool:
    value = getattr(transaction, "date", None)
    return _has_meaningful_date(value)


def _has_meaningful_date(value: Any) -> bool:
    return bool(value and str(value).strip() not in {"", "-"})


def _apply_event_date_fallback(
    transaction: Any,
    event: dict[str, Any],
    ocr_text: str | None,
) -> Any:
    original_date = getattr(transaction, "date", None)
    if _has_meaningful_date(original_date):
        return transaction
    if getattr(transaction, "amount", None) is None:
        return transaction

    fallback_date = _line_event_local_date(event)
    if not fallback_date:
        return transaction

    print(
        "[WARN] LINE transaction date missing; fallback to event local date.",
        f"original_date={_safe_log_text(_format_line_value(original_date))}",
        f"fallback_date={fallback_date}",
        f"event_timestamp={_format_line_value(event.get('timestamp'))}",
        flush=True,
    )
    return _transaction_with_date(transaction, fallback_date)


def _transaction_with_date(transaction: Any, fallback_date: str) -> Any:
    if is_dataclass(transaction):
        return replace(transaction, date=fallback_date)
    try:
        setattr(transaction, "date", fallback_date)
        return transaction
    except Exception:
        return transaction


def _line_event_local_date(event: dict[str, Any]) -> str | None:
    timestamp = event.get("timestamp")
    if timestamp is None:
        return None
    try:
        timestamp_seconds = int(timestamp) / 1000
    except (TypeError, ValueError):
        return None
    return (
        datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc)
        .astimezone(LINE_LOCAL_TIMEZONE)
        .date()
        .isoformat()
    )


def _has_meaningful_value(value: Any) -> bool:
    return bool(value and str(value).strip() not in {"", "-"})


def _looks_like_successful_payment_ocr(ocr_text: str | None) -> bool:
    text = str(ocr_text or "").lower()
    normalized = re.sub(r"[\s:：,./\\|\-]+", "", text)
    keywords = (
        "จ่ายบิลสำเร็จ",
        "ชำระเงินสำเร็จ",
        "ชําระเงินสําเร็จ",
        "โอนเงินสำเร็จ",
        "โอนเงินสําเร็จ",
        "payment successful",
        "success",
    )
    return any(
        re.sub(r"[\s:：,./\\|\-]+", "", keyword.lower()) in normalized
        for keyword in keywords
    )


def _format_line_value(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def _safe_log_text(value: Any) -> str:
    return str(value).encode("ascii", errors="backslashreplace").decode("ascii")


def _format_amount_value(value: Any) -> str:
    if value is None or value == "":
        return "-"
    try:
        return f"{float(value):.2f} THB"
    except (TypeError, ValueError):
        return str(value)


def _format_money_value(value: Any) -> str:
    if value is None or value == "":
        return "0.00 THB"
    try:
        return f"{float(value):.2f} THB"
    except (TypeError, ValueError):
        return f"{value} THB"


def _format_thai_baht(value: Any) -> str:
    if value is None or value == "":
        return "0"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    if amount.is_integer():
        return f"{int(amount):,}"
    return f"{amount:,.2f}"


def _format_balance_baht(value: Any) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _number_value(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _reply_token_prefix(reply_token: str | None) -> str:
    if not reply_token:
        return "-"
    return f"{str(reply_token)[:10]}..."


def _first_text_message(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return ""
    return str(messages[0].get("text") or "")


def _coerce_reply_messages(messages: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(messages, str):
        return [build_text_message(messages)]
    return messages


def _build_reply_payload_bytes(
    reply_token: str,
    messages: str | list[dict[str, Any]],
) -> bytes:
    return json.dumps(
        build_reply_payload(reply_token, _coerce_reply_messages(messages))
    ).encode("utf-8")


def send_line_reply(
    reply_token: str,
    messages: str | list[dict[str, Any]],
    channel_access_token: str,
    event_type: str | None = None,
    message_type: str | None = None,
) -> None:
    if not channel_access_token:
        raise LineBotError("LINE_CHANNEL_ACCESS_TOKEN is not set.")

    reply_messages = _coerce_reply_messages(messages)
    payload = _build_reply_payload_bytes(reply_token, reply_messages)
    print(
        "[INFO] LINE reply attempt",
        f"reply_token={_reply_token_prefix(reply_token)}",
        f"event_type={event_type}",
        f"message_type={message_type}",
        f"payload_length={len(payload)}",
        f"message_count={len(reply_messages)}",
        flush=True,
    )
    request = urllib.request.Request(
        LINE_REPLY_ENDPOINT,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {channel_access_token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            return
    except urllib.error.HTTPError as exc:
        response_body = _read_http_error_body(exc)
        print("[ERROR] LINE reply failed", flush=True)
        print(f"status={exc.code}", flush=True)
        print(f"reply_token={_reply_token_prefix(reply_token)}", flush=True)
        print(f"response={response_body}", flush=True)


def _read_http_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read()
    except Exception:
        return ""
    try:
        return body.decode("utf-8", errors="replace")
    except AttributeError:
        return str(body)


def download_line_image(
    message_id: str,
    channel_access_token: str,
    output_dir: Path = DEFAULT_LINE_IMAGE_DIR,
) -> Path:
    if not channel_access_token:
        raise LineBotError("LINE_CHANNEL_ACCESS_TOKEN is not set.")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"line_{message_id}.jpg"
    request = urllib.request.Request(
        LINE_CONTENT_ENDPOINT.format(message_id=message_id),
        headers={
            "Authorization": f"Bearer {channel_access_token}",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        output_path.write_bytes(response.read())
    return output_path


def _is_text_message_event(event: dict[str, Any]) -> bool:
    return (
        event.get("type") == "message"
        and event.get("message", {}).get("type") == "text"
    )


def _is_image_message_event(event: dict[str, Any]) -> bool:
    return (
        event.get("type") == "message"
        and event.get("message", {}).get("type") == "image"
    )
