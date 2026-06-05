from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> bool:
        env_path = Path(".env")
        if not env_path.exists():
            return False

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return True

from expense_tracker.line_bot import LineBotError, get_line_config, handle_line_webhook


HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8000"))


load_dotenv()


def load_line_config_with_debug() -> dict[str, str]:
    load_dotenv()
    config = get_line_config()
    print("[INFO] LINE_CHANNEL_SECRET loaded:", bool(config["channel_secret"]))
    print("[INFO] LINE_CHANNEL_ACCESS_TOKEN loaded:", bool(config["channel_access_token"]))
    return config


def has_required_line_config(config: dict[str, str]) -> bool:
    missing = [
        name
        for name, value in (
            ("LINE_CHANNEL_SECRET", config.get("channel_secret")),
            ("LINE_CHANNEL_ACCESS_TOKEN", config.get("channel_access_token")),
        )
        if not value
    ]
    if missing:
        print("[ERROR] Missing LINE environment values:", ", ".join(missing))
        return False
    return True


class LineWebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/webhook":
            self._send_json(404, {"error": "Not found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        signature = self.headers.get("X-Line-Signature")
        config = load_line_config_with_debug()

        if not has_required_line_config(config):
            self._send_json(401, {"error": "LINE webhook configuration is missing."})
            return

        try:
            result = handle_line_webhook(
                body,
                signature,
                config["channel_secret"],
                config["channel_access_token"],
            )
        except LineBotError as exc:
            print("[ERROR] LINE webhook failed:", str(exc))
            self._send_json(401, {"error": str(exc)})
            return
        except json.JSONDecodeError:
            print("[ERROR] LINE webhook failed: Invalid JSON payload.")
            self._send_json(400, {"error": "Invalid JSON payload."})
            return

        self._send_json(200, result)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": "Not found"})

    def _send_json(self, status_code: int, payload: dict) -> None:
        response = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        try:
            self.wfile.write(response)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            print("[WARN] Client disconnected before response was fully sent.")


def main() -> None:
    load_line_config_with_debug()
    server = HTTPServer((HOST, PORT), LineWebhookHandler)
    print(f"[INFO] LINE webhook listening on http://{HOST}:{PORT}/webhook")
    server.serve_forever()


if __name__ == "__main__":
    main()
