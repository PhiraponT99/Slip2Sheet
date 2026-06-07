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
    DATE_PARSE_FAILURE_TEXT,
    DEFAULT_REPLY_TEXT,
    IMAGE_DOWNLOAD_FAILURE_TEXT,
    INVALID_BALANCE_TEXT,
    LineBotError,
    OCR_FAILURE_TEXT,
    PARSE_FAILURE_TEXT,
    PROCESSED_LINE_EVENT_KEYS,
    SAVE_FAILURE_TEXT,
    build_balance_saved_reply_text,
    build_daily_summary_reply_text,
    build_duplicate_reply_text,
    build_ocr_reply_text,
    build_text_message,
    build_text_reply_payload,
    build_transaction_reply_text,
    download_line_image,
    generate_line_signature,
    handle_line_webhook,
    is_balance_command,
    is_daily_summary_command,
    line_event_key,
    parse_balance_command,
    save_line_transaction,
    send_line_reply,
    signature_diagnostics,
    verify_line_signature,
)
from expense_tracker.balance import read_balance, save_balance
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
    timestamp: int | None = None,
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
    if timestamp is not None:
        event["timestamp"] = timestamp
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
            "remaining_budget": 9737.9,
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
        self.assertIn("วันนี้ใช้เงิน:", replies[0])
        self.assertIn("- Lotus's 58 บาท", replies[0])
        self.assertIn("รวม 125.50 บาท", replies[0])
        self.assertNotIn("ยอดเงินคงเหลือ", replies[0])

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
        self.assertIn("วันนี้ใช้เงิน:", replies[0])
        self.assertTrue(is_daily_summary_command(" สรุปวันนี้ "))

    def test_balance_command_saves_amount(self) -> None:
        body = text_body("ตั้งยอดเงิน 9737.90")
        replies = []

        with (
            patch("expense_tracker.line_bot.save_balance_to_sheet") as save_mock,
            patch("expense_tracker.line_bot.save_balance") as local_save_mock,
        ):
            result = handle_line_webhook(
                body,
                sign(body),
                SECRET,
                "access-token",
                reply_fn=lambda reply_token, text, token: replies.append(text),
            )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        save_mock.assert_called_once_with(9737.9)
        local_save_mock.assert_not_called()
        self.assertEqual(replies, ["บันทึกยอดเงินแล้ว: 9,737.90 บาท"])
        self.assertTrue(is_balance_command("ยอดเงิน 9737.90"))
        self.assertEqual(
            parse_balance_command("เงินคงเหลือ 9,737.90"),
            {"matched": True, "amount": 9737.9},
        )
        self.assertEqual(
            build_balance_saved_reply_text(9737.9),
            "บันทึกยอดเงินแล้ว: 9,737.90 บาท",
        )

    def test_current_balance_command_reads_settings(self) -> None:
        body = text_body("ยอดเงิน")
        replies = []

        with patch("expense_tracker.line_bot._read_line_balance", return_value=9460.9):
            result = handle_line_webhook(
                body,
                sign(body),
                SECRET,
                "access-token",
                reply_fn=lambda reply_token, text, token: replies.append(text),
            )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        self.assertEqual(replies, ["ยอดเงินปัจจุบัน: 9,460.90 บาท"])

    def test_current_balance_command_missing_settings_value(self) -> None:
        body = text_body("ยอดเงิน")
        replies = []

        with patch("expense_tracker.line_bot._read_line_balance", return_value=None):
            result = handle_line_webhook(
                body,
                sign(body),
                SECRET,
                "access-token",
                reply_fn=lambda reply_token, text, token: replies.append(text),
            )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        self.assertEqual(
            replies,
            ["ยังไม่ได้ตั้งยอดเงิน พิมพ์: ตั้งยอดเงิน 9460.90"],
        )

    def test_invalid_balance_command_returns_helpful_error(self) -> None:
        body = text_body("ตั้งยอดเงิน abc")
        replies = []

        with patch("expense_tracker.line_bot.save_balance") as save_mock:
            result = handle_line_webhook(
                body,
                sign(body),
                SECRET,
                "access-token",
                reply_fn=lambda reply_token, text, token: replies.append(text),
            )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        save_mock.assert_not_called()
        self.assertEqual(replies, [INVALID_BALANCE_TEXT])

    def test_line_daily_summary_adds_balance_from_settings(self) -> None:
        summary_data = {
            "date": "2026-06-05",
            "total_expense": 113.0,
            "transactions": [
                {"merchant": "ชาบูเสียบไม้ โอะนาเบะ", "amount": 40.0},
                {"merchant": "ป้านก", "amount": 73.0},
            ],
        }

        with (
            patch("expense_tracker.line_bot.today_report", return_value=summary_data),
            patch("expense_tracker.line_bot._read_line_balance", return_value=9460.9),
        ):
            summary = __import__(
                "expense_tracker.line_bot",
                fromlist=["line_daily_summary"],
            ).line_daily_summary()

        self.assertEqual(summary["current_balance"], 9460.9)
        self.assertIn("ยอดเงินคงเหลือ: 9,460.90 บาท", build_daily_summary_reply_text(summary))

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
                    "วันนี้ใช้เงิน:",
                    "",
                    "ไม่มีรายการใช้เงินวันนี้",
                ]
            ),
        )

    def test_daily_summary_includes_remaining_balance_when_saved(self) -> None:
        with patch("expense_tracker.line_bot.read_balance", return_value=9737.9):
            reply = build_daily_summary_reply_text(
                {
                    "date": "2026-06-05",
                    "total_expense": 113.0,
                    "transactions": [
                        {
                            "merchant": "ชาบูเสียบไม้ โอะนาเบะ",
                            "amount": 40.0,
                        },
                        {
                            "merchant": "ป้านก",
                            "amount": 73.0,
                        },
                    ],
                }
            )

        self.assertEqual(
            reply,
            "\n".join(
                [
                    "วันนี้ใช้เงิน:",
                    "- ชาบูเสียบไม้ โอะนาเบะ 40 บาท",
                    "- ป้านก 73 บาท",
                    "",
                    "รวม 113 บาท",
                    "ยอดเงินคงเหลือ: 9,737.90 บาท",
                ]
            ),
        )

    def test_daily_summary_omits_remaining_balance_when_not_saved(self) -> None:
        with patch("expense_tracker.line_bot.read_balance", return_value=None):
            reply = build_daily_summary_reply_text(
                {
                    "date": "2026-06-05",
                    "total_expense": 35.6,
                    "transactions": [
                        {
                            "merchant": "ชา",
                            "amount": 35.6,
                        },
                    ],
                }
            )

        self.assertIn("- ชา 35.60 บาท", reply)
        self.assertIn("รวม 35.60 บาท", reply)
        self.assertNotIn("ยอดเงินคงเหลือ", reply)

    def test_daily_summary_count_uses_filtered_transaction_list(self) -> None:
        reply = build_daily_summary_reply_text(
            {
                "date": "2026-06-05",
                "total_expense": 100.0,
                "transactions": [
                    {"time": "10:00", "merchant": "A", "amount": 10.0},
                    {"time": "11:00", "merchant": "B", "amount": 20.0},
                    {"time": "12:00", "merchant": "C", "amount": 70.0},
                ],
            }
        )

        self.assertNotIn("Transactions:", reply)
        self.assertIn("- A 10 บาท", reply)
        self.assertIn("- C 70 บาท", reply)
        self.assertIn("รวม 100 บาท", reply)

    def test_daily_summary_prefers_note_over_merchant_for_item_label(self) -> None:
        reply = build_daily_summary_reply_text(
            {
                "date": "2026-06-05",
                "total_expense": 183.0,
                "remaining_budget": 9737.9,
                "transactions": [
                    {"note": "ชา", "merchant": "ร้านน้ำ", "amount": 15.0},
                    {"note": "มื้อเที่ยง", "merchant": "เหมียวแซ่บ", "amount": 16.0},
                    {"merchant": "ขนมเบื้อง", "amount": 24.0},
                ],
            }
        )

        self.assertEqual(
            reply,
            "\n".join(
                [
                    "วันนี้ใช้เงิน:",
                    "- ชา 15 บาท",
                    "- มื้อเที่ยง 16 บาท",
                    "- ขนมเบื้อง 24 บาท",
                    "",
                    "รวม 183 บาท",
                ]
            ),
        )

    def test_daily_summary_skips_discount_payment_lines_as_labels(self) -> None:
        reply = build_daily_summary_reply_text(
            {
                "date": "2026-06-05",
                "total_expense": 75.6,
                "transactions": [
                    {
                        "note": "สิทธิไทยช่วยไทยพลัส -36 บาท",
                        "merchant": "ขนมเบื้อง",
                        "category": "food",
                        "amount": 24.0,
                    },
                    {
                        "note": "จำนวนเงินที่ชำระ 16 บาท",
                        "merchant": "มื้อเที่ยง",
                        "category": "food",
                        "amount": 16.0,
                    },
                    {
                        "note": "58.00",
                        "item": "ส่วนลด",
                        "merchant": "discount",
                        "category": "drink",
                        "amount": 35.6,
                    },
                ],
            }
        )

        self.assertIn("- ขนมเบื้อง 24 บาท", reply)
        self.assertIn("- มื้อเที่ยง 16 บาท", reply)
        self.assertIn("- drink 35.60 บาท", reply)
        self.assertIn("รวม 75.60 บาท", reply)
        self.assertNotIn("สิทธิไทยช่วยไทยพลัส", reply)
        self.assertNotIn("จำนวนเงินที่ชำระ", reply)

    def test_daily_summary_uses_generic_label_when_all_names_rejected(self) -> None:
        reply = build_daily_summary_reply_text(
            {
                "date": "2026-06-05",
                "total_expense": 58.0,
                "transactions": [
                    {
                        "note": "จำนวนเงิน 58.00",
                        "item": "ค่าสินค้า/บริการ 58 บาท",
                        "merchant": "สิทธิไทยช่วยไทยพลัส -24 บาท",
                        "category": "บาท",
                        "amount": 58.0,
                    },
                ],
            }
        )

        self.assertIn("- รายการ 58 บาท", reply)
        self.assertNotIn("จำนวนเงิน", reply)
        self.assertNotIn("ค่าสินค้า/บริการ", reply)

    def test_balance_is_not_reset_by_image_uploads(self) -> None:
        body = image_body()
        saved_path = Path("incoming") / "line" / "line_image-id.jpg"
        transaction = TransactionResult(
            date="2026-06-05",
            time="12:26",
            merchant="Lotus's",
            amount=58.0,
            raw_text="",
        )

        with patch("expense_tracker.line_bot.save_balance") as save_balance_mock:
            result = handle_line_webhook(
                body,
                sign(body),
                SECRET,
                "access-token",
                reply_fn=lambda reply_token, text, token: None,
                image_download_fn=lambda message_id, token: saved_path,
                ocr_fn=lambda image_path: "amount 58",
                parse_fn=lambda ocr_text: transaction,
                save_transaction_fn=lambda transaction, source: {
                    "saved": True,
                    "duplicate": False,
                    "sheet_tab": "2026-06",
                },
                duplicate_store_path=None,
            )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        save_balance_mock.assert_not_called()

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
            "transactions": [
                {
                    "time": "12:26",
                    "merchant": "Lotus's",
                    "amount": 58.0,
                }
            ],
        }

        with (
            patch("expense_tracker.line_bot.today_report", return_value=summary_data),
            patch("builtins.print") as print_mock,
        ):
            summary = __import__(
                "expense_tracker.line_bot",
                fromlist=["line_daily_summary"],
            ).line_daily_summary()

        self.assertEqual(len(summary["transactions"]), 1)
        self.assertEqual(summary["total_expense"], 58.0)
        logged = "\n".join(" ".join(str(part) for part in call.args) for call in print_mock.call_args_list)
        self.assertIn("LINE daily summary query", logged)
        self.assertIn("sheet_tab=", logged)
        self.assertIn("LINE daily summary result", logged)
        self.assertIn("result_count=1", logged)
        self.assertIn("total=58.0", logged)

    def test_save_line_transaction_uses_existing_sheet_append(self) -> None:
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
            patch("expense_tracker.line_bot.append_transaction_to_sheet") as append_mock,
        ):
            append_mock.return_value = {
                "saved": True,
                "duplicate": False,
                "sheet_tab": "2026-06",
            }
            result = save_line_transaction(
                transaction,
                Path("incoming") / "line" / "line_image-id.jpg",
                "food",
            )

        self.assertEqual(result["saved"], True)
        self.assertEqual(result["sheet_tab"], "2026-06")
        append_mock.assert_called_once_with(
            transaction,
            Path("incoming") / "line" / "line_image-id.jpg",
        )

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

    def test_missing_parsed_date_returns_clear_error_without_save(self) -> None:
        body = image_body()
        replies = []
        saved_path = Path("incoming") / "line" / "line_image-id.jpg"
        save_calls = []
        transaction = TransactionResult(
            date=None,
            time="11:47",
            merchant="เหมียวแซ่บ",
            amount=16.0,
            raw_text="5 bad-month 2569 11:47 น.",
        )

        result = handle_line_webhook(
            body,
            sign(body),
            SECRET,
            "access-token",
            reply_fn=lambda reply_token, text, token: replies.append(text),
            image_download_fn=lambda message_id, token: saved_path,
            ocr_fn=lambda image_path: transaction.raw_text,
            parse_fn=lambda ocr_text: transaction,
            save_transaction_fn=lambda transaction, source: save_calls.append(transaction),
            duplicate_store_path=None,
        )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        self.assertEqual(replies, [DATE_PARSE_FAILURE_TEXT])
        self.assertEqual(save_calls, [])

    def test_missing_date_with_amount_and_time_uses_event_local_date(self) -> None:
        body = image_body(timestamp=1780678800000)
        replies = []
        saved_path = Path("incoming") / "line" / "line_image-id.jpg"
        saved_transactions = []
        transaction = TransactionResult(
            date="-",
            time="17:36",
            merchant="\u0e02\u0e19\u0e21\u0e40\u0e1a\u0e37\u0e49\u0e2d\u0e07",
            amount=24.0,
            raw_text="\u0e08\u0e48\u0e32\u0e22\u0e1a\u0e34\u0e25\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08\n17:36\n\u0e08\u0e33\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19 24.00",
        )

        def save_transaction(transaction, source):
            saved_transactions.append(transaction)
            return {"saved": True, "duplicate": False, "sheet_tab": "2026-06"}

        result = handle_line_webhook(
            body,
            sign(body),
            SECRET,
            "access-token",
            reply_fn=lambda reply_token, text, token: replies.append(text),
            image_download_fn=lambda message_id, token: saved_path,
            ocr_fn=lambda image_path: transaction.raw_text,
            parse_fn=lambda ocr_text: transaction,
            save_transaction_fn=save_transaction,
            duplicate_store_path=None,
        )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        self.assertEqual(saved_transactions[0].date, "2026-06-06")
        self.assertIn("Transaction Saved", replies[0])
        self.assertIn("Date: 2026-06-06", replies[0])

    def test_missing_date_with_amount_without_time_uses_event_local_date(self) -> None:
        body = image_body(timestamp=1780678800000)
        replies = []
        saved_path = Path("incoming") / "line" / "line_image-id.jpg"
        saved_transactions = []
        transaction = TransactionResult(
            date=None,
            time=None,
            merchant="\u0e0a\u0e32\u0e1a\u0e39\u0e40\u0e2a\u0e35\u0e22\u0e1a\u0e44\u0e21\u0e49 \u0e42\u0e2d\u0e30\u0e19\u0e32\u0e40\u0e1a\u0e30",
            amount=40.0,
            raw_text="\u0e08\u0e33\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19\u0e17\u0e35\u0e48\u0e0a\u0e33\u0e23\u0e30 40 \u0e1a\u0e32\u0e17",
        )

        def save_transaction(transaction, source):
            saved_transactions.append(transaction)
            return {"saved": True, "duplicate": False, "sheet_tab": "2026-06"}

        result = handle_line_webhook(
            body,
            sign(body),
            SECRET,
            "access-token",
            reply_fn=lambda reply_token, text, token: replies.append(text),
            image_download_fn=lambda message_id, token: saved_path,
            ocr_fn=lambda image_path: transaction.raw_text,
            parse_fn=lambda ocr_text: transaction,
            save_transaction_fn=save_transaction,
            duplicate_store_path=None,
        )

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        self.assertEqual(saved_transactions[0].date, "2026-06-06")
        self.assertIn("Transaction Saved", replies[0])
        self.assertIn("Date: 2026-06-06", replies[0])

    def test_valid_parsed_date_is_not_overwritten_by_event_date(self) -> None:
        body = image_body(timestamp=1780678800000)
        replies = []
        saved_path = Path("incoming") / "line" / "line_image-id.jpg"
        saved_transactions = []
        transaction = TransactionResult(
            date="2026-06-05",
            time="17:36",
            merchant="\u0e02\u0e19\u0e21\u0e40\u0e1a\u0e37\u0e49\u0e2d\u0e07",
            amount=24.0,
            raw_text="",
        )

        def save_transaction(transaction, source):
            saved_transactions.append(transaction)
            return {"saved": True, "duplicate": False, "sheet_tab": "2026-06"}

        handle_line_webhook(
            body,
            sign(body),
            SECRET,
            "access-token",
            reply_fn=lambda reply_token, text, token: replies.append(text),
            image_download_fn=lambda message_id, token: saved_path,
            ocr_fn=lambda image_path: "",
            parse_fn=lambda ocr_text: transaction,
            save_transaction_fn=save_transaction,
            duplicate_store_path=None,
        )

        self.assertEqual(saved_transactions[0].date, "2026-06-05")
        self.assertIn("Date: 2026-06-05", replies[0])

    def test_missing_date_fallback_logs_warning(self) -> None:
        body = image_body(timestamp=1780678800000)
        saved_path = Path("incoming") / "line" / "line_image-id.jpg"
        transaction = TransactionResult(
            date=None,
            time="17:36",
            merchant="\u0e02\u0e19\u0e21\u0e40\u0e1a\u0e37\u0e49\u0e2d\u0e07",
            amount=24.0,
            raw_text="",
        )

        with patch("builtins.print") as print_mock:
            handle_line_webhook(
                body,
                sign(body),
                SECRET,
                "access-token",
                reply_fn=lambda reply_token, text, token: None,
                image_download_fn=lambda message_id, token: saved_path,
                ocr_fn=lambda image_path: "",
                parse_fn=lambda ocr_text: transaction,
                save_transaction_fn=lambda transaction, source: {
                    "saved": True,
                    "duplicate": False,
                    "sheet_tab": "2026-06",
                },
                duplicate_store_path=None,
            )

        logged = "\n".join(
            " ".join(str(part) for part in call.args)
            for call in print_mock.call_args_list
        )
        self.assertIn("LINE transaction date missing; fallback to event local date.", logged)
        self.assertIn("original_date=-", logged)
        self.assertIn("fallback_date=2026-06-06", logged)
        self.assertIn("event_timestamp=1780678800000", logged)

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
            self.assertFalse(store_path.exists())
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
            save_results = [
                {
                    "saved": True,
                    "duplicate": False,
                    "sheet_tab": "2026-06",
                },
                {
                    "saved": False,
                    "duplicate": True,
                    "sheet_tab": "2026-06",
                },
            ]
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
                    save_transaction_fn=lambda transaction, source: save_results.pop(0),
                    duplicate_store_path=store_path,
                )

            self.assertFalse(store_path.exists())

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


class BalanceStorageTest(unittest.TestCase):
    def test_save_and_read_balance_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "data" / "balance.json"

            payload = save_balance("9,737.90", path=path)

            self.assertTrue(path.exists())
            self.assertEqual(payload["amount"], 9737.9)
            self.assertEqual(payload["source"], "line")
            self.assertEqual(read_balance(path), 9737.9)

    def test_read_balance_missing_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertIsNone(read_balance(Path(temp_dir) / "missing.json"))


if __name__ == "__main__":
    unittest.main()
