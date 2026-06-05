from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import tempfile
import urllib.error
import unittest
from pathlib import Path
from unittest.mock import patch

from expense_tracker.line_bot import (
    DEFAULT_REPLY_TEXT,
    IMAGE_DOWNLOAD_FAILURE_TEXT,
    LINE_SHEET_COLUMNS,
    LineBotError,
    OCR_FAILURE_TEXT,
    PARSE_FAILURE_TEXT,
    PROCESSED_LINE_EVENT_KEYS,
    append_line_transaction_to_sheet,
    SAVE_FAILURE_TEXT,
    build_daily_summary_reply_text,
    build_duplicate_reply_text,
    build_ocr_reply_text,
    build_text_message,
    build_text_reply_payload,
    build_transaction_reply_text,
    download_line_image,
    generate_line_signature,
    handle_line_webhook,
    is_daily_summary_command,
    line_event_key,
    read_line_daily_summary,
    save_line_transaction,
    send_line_reply,
    signature_diagnostics,
    verify_line_signature,
)
from expense_tracker.models import TransactionResult
from line_webhook import has_required_line_config, load_line_config_with_debug


SECRET = "test-secret"
PRETTY_LOTUS_REPLY = "\n".join(
    [
        "\U0001f4b8 Transaction Saved",
        "",
        "Amount: 50.00 THB",
        "Date: 2026-06-03",
        "Time: 14:19",
        "",
        "Merchant: Lotus's",
        "",
        "Category: food",
    ]
)
PRETTY_CP_AXTRA_REPLY = "\n".join(
    [
        "\U0001f4b8 Transaction Saved",
        "",
        "Amount: 58.00 THB",
        "Date: 2026-06-04",
        "Time: 12:26",
        "",
        "Merchant: CP AXTRA PUBLIC COMPANY LIMITED (HEAD",
        "",
        "Category: food",
    ]
)


def sign(body: bytes) -> str:
    digest = hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def image_body(
    message_id: str = "image-id",
    reply_token: str = "reply-token",
    webhook_event_id: str | None = None,
    is_redelivery: bool | None = None,
) -> bytes:
    event = {
        "type": "message",
        "replyToken": reply_token,
        "message": {
            "type": "image",
            "id": message_id,
        },
    }
    if webhook_event_id is not None:
        event["webhookEventId"] = webhook_event_id
    if is_redelivery is not None:
        event["deliveryContext"] = {"isRedelivery": is_redelivery}
    return json.dumps({"events": [event]}).encode("utf-8")


def text_body(text: str) -> bytes:
    return json.dumps(
        {
            "events": [
                {
                    "type": "message",
                    "replyToken": "reply-token",
                    "message": {
                        "type": "text",
                        "text": text,
                    },
                }
            ]
        },
        ensure_ascii=False,
    ).encode("utf-8")


class FakeLineSheetsService:
    def __init__(self, rows: list[list[object]] | None = None, sheets: list[str] | None = None):
        self.rows = rows or []
        self.sheets = sheets or []
        self.appended_values: list[list[object]] = []
        self.updated_values: list[list[object]] = []
        self.batch_updates: list[dict[str, object]] = []

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def get(self, **kwargs):
        if "range" in kwargs:
            self._pending_result = {"values": self.rows}
        else:
            self._pending_result = {
                "sheets": [
                    {"properties": {"title": title}}
                    for title in self.sheets
                ]
            }
        return self

    def batchUpdate(self, **kwargs):
        self.batch_updates.append(kwargs.get("body", {}))
        for request in kwargs.get("body", {}).get("requests", []):
            title = request.get("addSheet", {}).get("properties", {}).get("title")
            if title and title not in self.sheets:
                self.sheets.append(title)
        self._pending_result = {}
        return self

    def update(self, **kwargs):
        values = kwargs.get("body", {}).get("values", [])
        self.updated_values.extend(values)
        self.rows = values
        self._pending_result = {}
        return self

    def append(self, **kwargs):
        values = kwargs.get("body", {}).get("values", [])
        self.appended_values.extend(values)
        self.rows.extend(values)
        self._pending_result = {}
        return self

    def execute(self):
        return getattr(self, "_pending_result", {})


class LineBotTest(unittest.TestCase):
    def setUp(self) -> None:
        PROCESSED_LINE_EVENT_KEYS.clear()

    def test_valid_signature(self) -> None:
        body = b'{"events":[]}'

        self.assertTrue(verify_line_signature(body, sign(body), SECRET))
        self.assertTrue(verify_line_signature(body, f" {sign(body)} ", SECRET))

    def test_invalid_signature(self) -> None:
        body = b'{"events":[]}'

        self.assertFalse(verify_line_signature(body, "invalid", SECRET))
        with self.assertRaises(LineBotError):
            handle_line_webhook(
                body,
                "invalid",
                SECRET,
                "access-token",
                reply_fn=lambda reply_token, text, token: None,
            )

    def test_missing_signature_fails(self) -> None:
        body = b'{"events":[]}'

        self.assertFalse(verify_line_signature(body, None, SECRET))
        with self.assertRaises(LineBotError):
            handle_line_webhook(
                body,
                None,
                SECRET,
                "access-token",
                reply_fn=lambda reply_token, text, token: None,
            )

    def test_missing_secret_fails(self) -> None:
        body = b'{"events":[]}'

        self.assertFalse(verify_line_signature(body, sign(body), ""))
        diagnostics = signature_diagnostics(body, sign(body), "")
        self.assertEqual(diagnostics["body_length"], len(body))
        self.assertTrue(diagnostics["signature_present"])
        self.assertFalse(diagnostics["secret_present"])

    def test_body_must_not_be_modified_before_verification(self) -> None:
        raw_body = b'{ "events" : [] }\n'
        modified_body = json.dumps(json.loads(raw_body.decode("utf-8"))).encode("utf-8")
        signature = generate_line_signature(raw_body, SECRET)

        self.assertTrue(verify_line_signature(raw_body, signature, SECRET))
        self.assertFalse(verify_line_signature(modified_body, signature, SECRET))

    def test_text_message_reply(self) -> None:
        body = text_body("hello")
        replies = []

        result = handle_line_webhook(
            body,
            sign(body),
            SECRET,
            "access-token",
            reply_fn=lambda reply_token, text, token: replies.append(
                {
                    "reply_token": reply_token,
                    "text": text,
                    "token": token,
                }
            ),
        )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        self.assertEqual(replies, [
            {
                "reply_token": "reply-token",
                "text": DEFAULT_REPLY_TEXT,
                "token": "access-token",
            }
        ])
        self.assertEqual(
            build_text_reply_payload("reply-token"),
            {
                "replyToken": "reply-token",
                "messages": [
                    {
                        "type": "text",
                        "text": "Hello from Slip2Sheet",
                    }
                ],
            },
        )

    def test_daily_summary_command_reply(self) -> None:
        body = text_body("summary today")
        replies = []
        summary = {
            "date": "2026-06-05",
            "transaction_count": 2,
            "total_expense": 125.5,
            "transactions": [
                {
                    "time": "12:26",
                    "merchant": "Lotus's",
                    "amount": 58.0,
                },
                {
                    "time": "14:19",
                    "merchant": "กะเพราหอม",
                    "amount": 67.5,
                },
            ],
        }

        result = handle_line_webhook(
            body,
            sign(body),
            SECRET,
            "access-token",
            reply_fn=lambda reply_token, text, token: replies.append(text),
            daily_summary_fn=lambda: summary,
        )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        self.assertEqual(replies, [build_daily_summary_reply_text(summary)])
        self.assertIn("Total: 125.50 THB", replies[0])
        self.assertIn("Transactions: 2", replies[0])
        self.assertIn("1. 12:26 Lotus's 58.00 THB", replies[0])

    def test_thai_daily_summary_command_reply(self) -> None:
        body = text_body("สรุปวันนี้")
        replies = []

        result = handle_line_webhook(
            body,
            sign(body),
            SECRET,
            "access-token",
            reply_fn=lambda reply_token, text, token: replies.append(text),
            daily_summary_fn=lambda: {
                "date": "2026-06-05",
                "transaction_count": 1,
                "total_expense": 50.0,
                "transactions": [
                    {
                        "time": "12:26",
                        "merchant": "Lotus's",
                        "amount": 50.0,
                    }
                ],
            },
        )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        self.assertIn("Daily Summary", replies[0])
        self.assertTrue(is_daily_summary_command(" สรุปวันนี้ "))

    def test_daily_summary_no_spending_reply(self) -> None:
        reply = build_daily_summary_reply_text(
            {
                "date": "2026-06-05",
                "transaction_count": 0,
                "total_expense": 0.0,
                "transactions": [],
            }
        )

        self.assertEqual(
            reply,
            "\n".join(
                [
                    "\U0001f4ca Daily Summary",
                    "",
                    "No spending recorded today.",
                ]
            ),
        )

    def test_duplicate_reply_token_is_skipped_in_same_webhook(self) -> None:
        body = json.dumps(
            {
                "events": [
                    {
                        "type": "message",
                        "replyToken": "same-reply-token",
                        "message": {
                            "type": "text",
                            "id": "text-1",
                            "text": "hello",
                        },
                    },
                    {
                        "type": "message",
                        "replyToken": "same-reply-token",
                        "message": {
                            "type": "text",
                            "id": "text-2",
                            "text": "summary today",
                        },
                    },
                ]
            }
        ).encode("utf-8")
        replies = []

        with patch("builtins.print") as print_mock:
            result = handle_line_webhook(
                body,
                sign(body),
                SECRET,
                "access-token",
                reply_fn=lambda reply_token, text, token: replies.append(
                    {
                        "reply_token": reply_token,
                        "text": text,
                        "token": token,
                    }
                ),
                daily_summary_fn=lambda: {
                    "date": "2026-06-05",
                    "transaction_count": 1,
                    "total_expense": 50.0,
                    "transactions": [
                        {
                            "time": "12:26",
                            "merchant": "Lotus's",
                            "amount": 50.0,
                        }
                    ],
                },
            )

        self.assertEqual(result, {"status": "ok", "events": 2, "replies": 1})
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["text"], DEFAULT_REPLY_TEXT)
        logged = "\n".join(" ".join(str(part) for part in call.args) for call in print_mock.call_args_list)
        self.assertIn("Duplicate LINE replyToken detected", logged)
        self.assertIn("reply_token=same-reply...", logged)

    def test_duplicate_line_event_is_skipped_before_ocr_parser_and_reply(self) -> None:
        body = image_body(
            message_id="617116753377886567",
            reply_token="78d2e5b4ce-token",
            is_redelivery=True,
        )
        processed_event_keys: set[str] = set()
        replies = []
        download_calls = []
        ocr_calls = []
        parse_calls = []
        saved_path = Path("incoming") / "line" / "line_617116753377886567.jpg"
        transaction = TransactionResult(
            date="2026-06-04",
            time="12:26",
            merchant="CP AXTRA PUBLIC COMPANY LIMITED",
            amount=58.0,
            raw_text="",
        )

        with patch("builtins.print") as print_mock:
            first_result = handle_line_webhook(
                body,
                sign(body),
                SECRET,
                "access-token",
                reply_fn=lambda reply_token, messages, token, event_type=None, message_type=None: replies.append(
                    messages
                ),
                image_download_fn=lambda message_id, token: download_calls.append(message_id) or saved_path,
                ocr_fn=lambda image_path: ocr_calls.append(image_path) or "amount 58",
                parse_fn=lambda ocr_text: parse_calls.append(ocr_text) or transaction,
                save_transaction_fn=lambda transaction, source: {
                    "saved": True,
                    "duplicate": False,
                    "sheet_tab": "2026-06",
                },
                duplicate_store_path=None,
                processed_event_keys=processed_event_keys,
            )
            second_result = handle_line_webhook(
                body,
                sign(body),
                SECRET,
                "access-token",
                reply_fn=lambda reply_token, messages, token, event_type=None, message_type=None: replies.append(
                    messages
                ),
                image_download_fn=lambda message_id, token: download_calls.append(message_id) or saved_path,
                ocr_fn=lambda image_path: ocr_calls.append(image_path) or "amount 58",
                parse_fn=lambda ocr_text: parse_calls.append(ocr_text) or transaction,
                save_transaction_fn=lambda transaction, source: {
                    "saved": True,
                    "duplicate": False,
                    "sheet_tab": "2026-06",
                },
                duplicate_store_path=None,
                processed_event_keys=processed_event_keys,
            )

        self.assertEqual(first_result, {"status": "ok", "events": 1, "replies": 0})
        self.assertEqual(second_result, {"status": "ok", "events": 1, "replies": 0})
        self.assertEqual(download_calls, [])
        self.assertEqual(ocr_calls, [])
        self.assertEqual(parse_calls, [])
        self.assertEqual(replies, [])
        logged = "\n".join(" ".join(str(part) for part in call.args) for call in print_mock.call_args_list)
        self.assertIn("event_key=message:617116753377886567", logged)
        self.assertIn("reply_token=78d2e5b4ce...", logged)
        self.assertIn("duplicate=False", logged)
        self.assertIn("is_redelivery=True", logged)
        self.assertIn("LINE redelivery event detected", logged)

    def test_line_event_key_prefers_webhook_event_id(self) -> None:
        event = {
            "webhookEventId": "webhook-event-id",
            "replyToken": "reply-token",
            "message": {
                "type": "image",
                "id": "message-id",
            },
        }

        self.assertEqual(line_event_key(event), "webhook:webhook-event-id")

    def test_send_line_reply_logs_http_error_response(self) -> None:
        error = urllib.error.HTTPError(
            url="https://api.line.me/v2/bot/message/reply",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=io.BytesIO(b'{"message":"Invalid reply token"}'),
        )

        with (
            patch("urllib.request.urlopen", side_effect=error),
            patch("builtins.print") as print_mock,
        ):
            send_line_reply("abcdefghij12345", "hello", "access-token")

        logged = "\n".join(" ".join(str(part) for part in call.args) for call in print_mock.call_args_list)
        self.assertIn("[ERROR] LINE reply failed", logged)
        self.assertIn("status=400", logged)
        self.assertIn("reply_token=abcdefghij...", logged)
        self.assertIn('response={"message":"Invalid reply token"}', logged)

    def test_send_line_reply_supports_multiple_message_objects(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse()

        messages = [
            build_text_message("first"),
            build_text_message("second"),
        ]

        with (
            patch("urllib.request.urlopen", side_effect=fake_urlopen),
            patch("builtins.print") as print_mock,
        ):
            send_line_reply(
                "abcdefghij12345",
                messages,
                "access-token",
                "message",
                "text",
            )

        self.assertEqual(
            captured["payload"],
            {
                "replyToken": "abcdefghij12345",
                "messages": messages,
            },
        )
        self.assertEqual(captured["timeout"], 10)
        logged = "\n".join(" ".join(str(part) for part in call.args) for call in print_mock.call_args_list)
        self.assertIn("payload_length=", logged)
        self.assertIn("message_count=2", logged)

    def test_save_line_transaction_logs_attempt_and_success(self) -> None:
        transaction = TransactionResult(
            date="2026-06-04",
            time="12:26",
            merchant="CP AXTRA PUBLIC COMPANY LIMITED",
            amount=58.0,
            raw_text="",
        )

        with patch("builtins.print") as print_mock:
            result = save_line_transaction(
                transaction,
                Path("incoming") / "line" / "line_image-id.jpg",
                "food",
                lambda transaction, source: {
                    "saved": True,
                    "sheet_tab": "2026-06",
                },
            )

        self.assertEqual(
            result,
            {
                "saved": True,
                "sheet_tab": "2026-06",
            },
        )
        logged = "\n".join(" ".join(str(part) for part in call.args) for call in print_mock.call_args_list)
        self.assertIn("Google Sheet append attempt", logged)
        self.assertIn("spreadsheet_id=", logged)
        self.assertIn("sheet_tab=2026-06", logged)
        self.assertIn("date=2026-06-04", logged)
        self.assertIn("amount=58.0", logged)
        self.assertIn("Google Sheet append success", logged)

    def test_line_daily_summary_logs_query_and_result(self) -> None:
        summary_data = {
            "date": "2026-06-05",
            "total_expense": 58.0,
            "transaction_count": 1,
            "transactions": [
                {
                    "time": "12:26",
                    "merchant": "Lotus's",
                    "amount": 58.0,
                }
            ],
        }

        with (
            patch("expense_tracker.line_bot.read_line_daily_summary", return_value=summary_data),
            patch("builtins.print") as print_mock,
        ):
            summary = __import__(
                "expense_tracker.line_bot",
                fromlist=["line_daily_summary"],
            ).line_daily_summary()

        self.assertEqual(summary["transaction_count"], 1)
        self.assertEqual(summary["total_expense"], 58.0)
        logged = "\n".join(" ".join(str(part) for part in call.args) for call in print_mock.call_args_list)
        self.assertIn("LINE daily summary query", logged)
        self.assertIn("sheet_tab=", logged)
        self.assertIn("LINE daily summary result", logged)
        self.assertIn("result_count=1", logged)
        self.assertIn("total=58.0", logged)

    def test_read_line_daily_summary_from_sheet_rows(self) -> None:
        rows = [
            LINE_SHEET_COLUMNS,
            ["2026-06-05", "12:26", 58, "Lotus's", "food", "line", "2026-06-05T12:27:00"],
            ["2026-06-04", "14:19", 50, "Other", "other", "line", "2026-06-04T14:20:00"],
        ]

        with (
            patch.dict(
                os.environ,
                {
                    "SPREADSHEET_ID": "spreadsheet-id",
                    "GOOGLE_APPLICATION_CREDENTIALS": "credentials.json",
                },
                clear=False,
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch("expense_tracker.line_bot._build_sheets_service", return_value=FakeLineSheetsService(rows=rows)),
            patch("builtins.print"),
        ):
            summary = read_line_daily_summary("2026-06-05")

        self.assertEqual(summary["transaction_count"], 1)
        self.assertEqual(summary["total_expense"], 58.0)
        self.assertEqual(summary["transactions"][0]["merchant"], "Lotus's")
        self.assertEqual(summary["transactions"][0]["source"], "line")

    def test_append_line_transaction_to_sheet_creates_tab_header_and_row(self) -> None:
        service = FakeLineSheetsService(rows=[], sheets=[])
        transaction = TransactionResult(
            date="2026-06-05",
            time="12:26",
            merchant="Lotus's",
            amount=58.0,
            raw_text="",
        )

        with (
            patch.dict(
                os.environ,
                {
                    "SPREADSHEET_ID": "spreadsheet-id",
                    "GOOGLE_APPLICATION_CREDENTIALS": "credentials.json",
                },
                clear=False,
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch("expense_tracker.line_bot._build_sheets_service", return_value=service),
        ):
            result = append_line_transaction_to_sheet(transaction, "food")

        self.assertEqual(result["saved"], True)
        self.assertEqual(result["sheet_tab"], "2026-06")
        self.assertIn("2026-06", service.sheets)
        self.assertEqual(service.updated_values, [LINE_SHEET_COLUMNS])
        self.assertEqual(service.appended_values[0][:6], [
            "2026-06-05",
            "12:26",
            58.0,
            "Lotus's",
            "food",
            "line",
        ])

    def test_ocr_text_parse_success(self) -> None:
        body = image_body()
        replies = []
        downloaded = []
        ocr_paths = []
        saved_path = Path("incoming") / "line" / "line_image-id.jpg"
        transaction = TransactionResult(
            date="2026-06-03",
            time="14:19",
            merchant="Lotus's",
            amount=50.0,
            raw_text="Lotus's\namount 50",
        )

        result = handle_line_webhook(
            body,
            sign(body),
            SECRET,
            "access-token",
            reply_fn=lambda reply_token, text, token: replies.append(
                {
                    "reply_token": reply_token,
                    "text": text,
                    "token": token,
                }
            ),
            image_download_fn=lambda message_id, token: downloaded.append(
                {"message_id": message_id, "token": token}
            ) or saved_path,
            ocr_fn=lambda image_path: ocr_paths.append(image_path) or "Lotus's\namount 50",
            parse_fn=lambda ocr_text: transaction,
            save_transaction_fn=lambda transaction, source: {
                "saved": True,
                "duplicate": False,
                "sheet_tab": "2026-06",
            },
            duplicate_store_path=None,
        )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        self.assertEqual(downloaded, [{"message_id": "image-id", "token": "access-token"}])
        self.assertEqual(ocr_paths, [saved_path])
        self.assertEqual(replies, [
            {
                "reply_token": "reply-token",
                "text": PRETTY_LOTUS_REPLY,
                "token": "access-token",
            }
        ])

    def test_parse_failure(self) -> None:
        body = image_body()
        replies = []
        saved_path = Path("incoming") / "line" / "line_image-id.jpg"

        result = handle_line_webhook(
            body,
            sign(body),
            SECRET,
            "access-token",
            reply_fn=lambda reply_token, text, token: replies.append(
                {
                    "reply_token": reply_token,
                    "text": text,
                    "token": token,
                }
            ),
            image_download_fn=lambda message_id, token: saved_path,
            ocr_fn=lambda image_path: "not a transaction",
            parse_fn=lambda ocr_text: TransactionResult(
                date=None,
                time=None,
                merchant=None,
                amount=None,
                raw_text=ocr_text,
            ),
            duplicate_store_path=None,
        )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        self.assertEqual(replies, [
            {
                "reply_token": "reply-token",
                "text": PARSE_FAILURE_TEXT,
                "token": "access-token",
            }
        ])

    def test_save_failure_returns_save_error_reply(self) -> None:
        body = image_body()
        replies = []
        saved_path = Path("incoming") / "line" / "line_image-id.jpg"
        transaction = TransactionResult(
            date="2026-06-04",
            time="12:26",
            merchant="CP AXTRA PUBLIC COMPANY LIMITED",
            amount="bad",
            raw_text="",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "processed" / "line_duplicates.json"
            result = handle_line_webhook(
                body,
                sign(body),
                SECRET,
                "access-token",
                reply_fn=lambda reply_token, text, token: replies.append(text),
                image_download_fn=lambda message_id, token: saved_path,
                ocr_fn=lambda image_path: "amount bad",
                parse_fn=lambda ocr_text: transaction,
                save_transaction_fn=lambda transaction, source: (_ for _ in ()).throw(
                    RuntimeError("sheet append failed")
                ),
                duplicate_store_path=store_path,
            )

            self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
            self.assertFalse(store_path.exists())
            self.assertEqual(replies, [SAVE_FAILURE_TEXT])

    def test_line_image_flow_returns_transaction_summary(self) -> None:
        body = image_body()
        replies = []
        saved_path = Path("incoming") / "line" / "line_image-id.jpg"
        ocr_text = "\n".join(
            [
                "@ \u0e08\u0e48\u0e32\u0e22\u0e1a\u0e34\u0e25\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08",
                "04/06/2026 12:26",
                "\u0e44\u0e1b\u0e22\u0e31\u0e07 | CP AXTRA PUBLIC COMPANY",
                "LIMITED (HEAD",
                "XXX-XXX073-8",
                "\u0e08\u0e4d\u0e32\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19 58.00",
            ]
        )

        with patch("expense_tracker.parser.normalize_merchant", side_effect=lambda merchant: merchant):
            result = handle_line_webhook(
                body,
                sign(body),
                SECRET,
                "access-token",
                reply_fn=lambda reply_token, text, token: replies.append(text),
                image_download_fn=lambda message_id, token: saved_path,
                ocr_fn=lambda image_path: ocr_text,
                save_transaction_fn=lambda transaction, source: {
                    "saved": True,
                    "duplicate": False,
                    "sheet_tab": "2026-06",
                },
                duplicate_store_path=None,
            )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        self.assertEqual(
            replies,
            [PRETTY_CP_AXTRA_REPLY],
        )

    def test_amount_formatted_with_two_decimals(self) -> None:
        transaction = TransactionResult(
            date="2026-06-03",
            time="14:19",
            merchant="Test Merchant",
            amount=58.0,
            raw_text="",
        )

        self.assertIn("Amount: 58.00 THB", build_transaction_reply_text(transaction))

    def test_build_transaction_reply_text_uses_dash_for_missing_merchant(self) -> None:
        transaction = TransactionResult(
            date="2026-06-03",
            time="14:19",
            merchant=None,
            amount=50.0,
            raw_text="",
        )

        self.assertIn("Merchant: -", build_transaction_reply_text(transaction, "food"))

    def test_build_transaction_reply_text_uses_dash_for_missing_category(self) -> None:
        transaction = TransactionResult(
            date="2026-06-03",
            time="14:19",
            merchant="Test Merchant",
            amount=50.0,
            raw_text="",
        )

        self.assertEqual(
            build_transaction_reply_text(transaction),
            "\n".join(
                [
                    "\U0001f4b8 Transaction Detected",
                    "",
                    "Amount: 50.00 THB",
                    "Date: 2026-06-03",
                    "Time: 14:19",
                    "",
                    "Merchant: Test Merchant",
                    "",
                    "Category: -",
                ]
            ),
        )

    def test_first_line_slip_is_accepted_and_recorded(self) -> None:
        body = image_body()
        saved_path = Path("incoming") / "line" / "line_image-id.jpg"
        transaction = TransactionResult(
            date="2026-06-04",
            time="12:26",
            merchant="CP AXTRA PUBLIC COMPANY LIMITED",
            amount=58.0,
            raw_text="",
        )
        replies = []

        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "processed" / "line_duplicates.json"
            result = handle_line_webhook(
                body,
                sign(body),
                SECRET,
                "access-token",
                reply_fn=lambda reply_token, text, token: replies.append(text),
                image_download_fn=lambda message_id, token: saved_path,
                ocr_fn=lambda image_path: "amount 58",
                parse_fn=lambda ocr_text: transaction,
                save_transaction_fn=lambda transaction, source: {
                    "saved": True,
                    "duplicate": False,
                    "sheet_tab": "2026-06",
                },
                duplicate_store_path=store_path,
            )

            self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
            self.assertTrue(store_path.exists())
            self.assertIn("💸 Transaction Saved", replies[0])

    def test_repeated_line_slip_is_detected_as_duplicate(self) -> None:
        body = image_body()
        saved_path = Path("incoming") / "line" / "line_image-id.jpg"
        transaction = TransactionResult(
            date="2026-06-04",
            time="12:26",
            merchant="CP AXTRA PUBLIC COMPANY LIMITED",
            amount=58.0,
            raw_text="",
        )
        replies = []

        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "processed" / "line_duplicates.json"
            for index in range(2):
                body = image_body(
                    message_id=f"image-id-{index}",
                    reply_token=f"reply-token-{index}",
                )
                handle_line_webhook(
                    body,
                    sign(body),
                    SECRET,
                    "access-token",
                    reply_fn=lambda reply_token, text, token: replies.append(text),
                    image_download_fn=lambda message_id, token: saved_path,
                    ocr_fn=lambda image_path: "amount 58",
                    parse_fn=lambda ocr_text: transaction,
                    save_transaction_fn=lambda transaction, source: {
                        "saved": True,
                        "duplicate": False,
                        "sheet_tab": "2026-06",
                    },
                    duplicate_store_path=store_path,
                )

        self.assertEqual(
            replies[-1],
            "\n".join(
                [
                    "Duplicate slip detected.",
                    "",
                    "Amount: 58.00 THB",
                    "Date: 2026-06-04",
                    "Time: 12:26",
                    "Merchant: CP AXTRA PUBLIC COMPANY LIMITED",
                ]
            ),
        )

    def test_duplicate_store_file_is_created_automatically(self) -> None:
        transaction = TransactionResult(
            date="2026-06-04",
            time="12:26",
            merchant="CP AXTRA PUBLIC COMPANY LIMITED",
            amount=58.0,
            raw_text="",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "processed" / "line_duplicates.json"
            self.assertFalse(store_path.exists())

            from expense_tracker.line_bot import record_line_transaction

            record_line_transaction(transaction, store_path)

            self.assertTrue(store_path.exists())

    def test_malformed_transaction_does_not_crash_duplicate_check(self) -> None:
        body = image_body()
        saved_path = Path("incoming") / "line" / "line_image-id.jpg"
        transaction = TransactionResult(
            date="2026-06-04",
            time="12:26",
            merchant="CP AXTRA PUBLIC COMPANY LIMITED",
            amount="bad",
            raw_text="",
        )
        replies = []

        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "processed" / "line_duplicates.json"
            result = handle_line_webhook(
                body,
                sign(body),
                SECRET,
                "access-token",
                reply_fn=lambda reply_token, text, token: replies.append(text),
                image_download_fn=lambda message_id, token: saved_path,
                ocr_fn=lambda image_path: "amount bad",
                parse_fn=lambda ocr_text: transaction,
                save_transaction_fn=lambda transaction, source: {
                    "saved": True,
                    "duplicate": False,
                    "sheet_tab": "2026-06",
                },
                duplicate_store_path=store_path,
            )

            self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
            self.assertFalse(store_path.exists())
            self.assertIn("Amount: bad", replies[0])

    def test_duplicate_reply_formatter(self) -> None:
        transaction = TransactionResult(
            date="2026-06-04",
            time="12:26",
            merchant="CP AXTRA PUBLIC COMPANY LIMITED",
            amount=58.0,
            raw_text="",
        )

        self.assertEqual(
            build_duplicate_reply_text(transaction),
            "\n".join(
                [
                    "Duplicate slip detected.",
                    "",
                    "Amount: 58.00 THB",
                    "Date: 2026-06-04",
                    "Time: 12:26",
                    "Merchant: CP AXTRA PUBLIC COMPANY LIMITED",
                ]
            ),
        )

    def test_ocr_failure(self) -> None:
        body = image_body()
        replies = []
        saved_path = Path("incoming") / "line" / "line_image-id.jpg"

        result = handle_line_webhook(
            body,
            sign(body),
            SECRET,
            "access-token",
            reply_fn=lambda reply_token, text, token: replies.append(
                {
                    "reply_token": reply_token,
                    "text": text,
                    "token": token,
                }
            ),
            image_download_fn=lambda message_id, token: saved_path,
            ocr_fn=lambda image_path: (_ for _ in ()).throw(RuntimeError("ocr failed")),
            duplicate_store_path=None,
        )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        self.assertEqual(replies, [
            {
                "reply_token": "reply-token",
                "text": OCR_FAILURE_TEXT,
                "token": "access-token",
            }
        ])

    def test_ocr_reply_text_truncates_to_500_characters(self) -> None:
        text = "x" * 501

        self.assertEqual(
            build_ocr_reply_text(text),
            f"OCR completed.\n\nDetected text:\n\n{'x' * 500}...",
        )

    def test_image_directory_auto_created(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return b"image-bytes"

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "incoming" / "line"
            with patch("urllib.request.urlopen", return_value=FakeResponse()):
                output_path = download_line_image(
                    "531224567891234567",
                    "access-token",
                    output_dir=output_dir,
                )

            self.assertEqual(
                output_path,
                output_dir / "line_531224567891234567.jpg",
            )
            self.assertEqual(output_path.read_bytes(), b"image-bytes")

    def test_failed_download_returns_error_reply(self) -> None:
        body = image_body()
        replies = []

        result = handle_line_webhook(
            body,
            sign(body),
            SECRET,
            "access-token",
            reply_fn=lambda reply_token, text, token: replies.append(
                {
                    "reply_token": reply_token,
                    "text": text,
                    "token": token,
                }
            ),
            image_download_fn=lambda message_id, token: (_ for _ in ()).throw(
                RuntimeError("download failed")
            ),
            duplicate_store_path=None,
        )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        self.assertEqual(replies, [
            {
                "reply_token": "reply-token",
                "text": IMAGE_DOWNLOAD_FAILURE_TEXT,
                "token": "access-token",
            }
        ])

    def test_unsupported_message_type_is_ignored(self) -> None:
        body = json.dumps(
            {
                "events": [
                    {
                        "type": "message",
                        "replyToken": "reply-token",
                        "message": {
                            "type": "sticker",
                            "id": "sticker-id",
                        },
                    }
                ]
            }
        ).encode("utf-8")
        replies = []

        result = handle_line_webhook(
            body,
            sign(body),
            SECRET,
            "access-token",
            reply_fn=lambda reply_token, text, token: replies.append(
                {
                    "reply_token": reply_token,
                    "text": text,
                    "token": token,
                }
            ),
        )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 0})
        self.assertEqual(replies, [])

    def test_env_config_loaded(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "LINE_CHANNEL_SECRET": "secret",
                    "LINE_CHANNEL_ACCESS_TOKEN": "token",
                },
                clear=False,
            ),
            patch("builtins.print"),
        ):
            config = load_line_config_with_debug()

        self.assertEqual(config["channel_secret"], "secret")
        self.assertEqual(config["channel_access_token"], "token")
        self.assertTrue(has_required_line_config(config))

    def test_missing_secret_returns_unauthorized_condition(self) -> None:
        config = {
            "channel_secret": "",
            "channel_access_token": "token",
        }

        with patch("builtins.print") as print_mock:
            self.assertFalse(has_required_line_config(config))

        print_mock.assert_called_once_with(
            "[ERROR] Missing LINE environment values:",
            "LINE_CHANNEL_SECRET",
        )
        with self.assertRaises(LineBotError):
            handle_line_webhook(
                b'{"events":[]}',
                "signature",
                config["channel_secret"],
                config["channel_access_token"],
                reply_fn=lambda reply_token, text, token: None,
            )


if __name__ == "__main__":
    unittest.main()
