from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Callable

from expense_tracker.ocr import run_ocr


LINE_REPLY_ENDPOINT = "https://api.line.me/v2/bot/message/reply"
LINE_CONTENT_ENDPOINT = "https://api-data.line.me/v2/bot/message/{message_id}/content"
DEFAULT_REPLY_TEXT = "Hello from Slip2Sheet"
IMAGE_REPLY_TEXT = "Image received by Slip2Sheet"
IMAGE_DOWNLOAD_SUCCESS_TEXT = "Slip image received."
IMAGE_DOWNLOAD_FAILURE_TEXT = "Failed to download image."
OCR_FAILURE_TEXT = "OCR failed."
DEFAULT_LINE_IMAGE_DIR = Path("incoming") / "line"


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
    reply_fn: Callable[[str, str, str], None] = None,
    image_download_fn: Callable[[str, str], Path] = None,
    ocr_fn: Callable[[Path], str] = None,
) -> dict[str, Any]:
    if not verify_line_signature(body, signature, channel_secret):
        raise LineBotError("Invalid LINE signature.")

    if reply_fn is None:
        reply_fn = send_line_reply

    payload = json.loads(body.decode("utf-8") or "{}")
    events = payload.get("events", [])
    reply_count = 0

    for event in events:
        if _is_text_message_event(event):
            reply_token = event.get("replyToken")
            if reply_token:
                reply_fn(reply_token, DEFAULT_REPLY_TEXT, channel_access_token)
                reply_count += 1
        elif _is_image_message_event(event):
            reply_token = event.get("replyToken")
            if reply_token:
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
                        reply_text = build_ocr_reply_text(ocr_text)
                        print("[INFO] LINE image message_id:", message_id)
                        print("[INFO] LINE image saved_file:", str(saved_file))
                        print("[INFO] LINE image ocr_success:", True)
                    except Exception as exc:
                        print("[ERROR] LINE OCR failed:", str(exc))
                        print("[INFO] LINE image message_id:", message_id)
                        print("[INFO] LINE image saved_file:", str(saved_file))
                        print("[INFO] LINE image ocr_success:", False)
                        reply_text = OCR_FAILURE_TEXT
                reply_fn(reply_token, reply_text, channel_access_token)
                reply_count += 1

    return {
        "status": "ok",
        "events": len(events),
        "replies": reply_count,
        
    }


def build_text_reply_payload(reply_token: str, text: str = DEFAULT_REPLY_TEXT) -> dict[str, Any]:
    return {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": text,
            }
        ],
    }


def build_ocr_reply_text(ocr_text: str, limit: int = 500) -> str:
    text = ocr_text or ""
    if len(text) > limit:
        text = text[:limit] + "..."
    return f"OCR completed.\n\nDetected text:\n\n{text}"


def send_line_reply(reply_token: str, text: str, channel_access_token: str) -> None:
    if not channel_access_token:
        raise LineBotError("LINE_CHANNEL_ACCESS_TOKEN is not set.")

    request = urllib.request.Request(
        LINE_REPLY_ENDPOINT,
        data=json.dumps(build_text_reply_payload(reply_token, text)).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {channel_access_token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10):
        return


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
