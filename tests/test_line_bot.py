from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import unittest
from unittest.mock import patch

from expense_tracker.line_bot import (
    DEFAULT_REPLY_TEXT,
    IMAGE_REPLY_TEXT,
    LineBotError,
    build_text_reply_payload,
    generate_line_signature,
    handle_line_webhook,
    signature_diagnostics,
    verify_line_signature,
)
from line_webhook import has_required_line_config, load_line_config_with_debug


SECRET = "test-secret"


def sign(body: bytes) -> str:
    digest = hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


class LineBotTest(unittest.TestCase):
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
        body = json.dumps(
            {
                "events": [
                    {
                        "type": "message",
                        "replyToken": "reply-token",
                        "message": {
                            "type": "text",
                            "text": "hello",
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

    def test_image_message_reply(self) -> None:
        body = json.dumps(
            {
                "events": [
                    {
                        "type": "message",
                        "replyToken": "reply-token",
                        "message": {
                            "type": "image",
                            "id": "image-id",
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

        self.assertEqual(result, {"status": "ok", "events": 1, "replies": 1})
        self.assertEqual(replies, [
            {
                "reply_token": "reply-token",
                "text": IMAGE_REPLY_TEXT,
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
