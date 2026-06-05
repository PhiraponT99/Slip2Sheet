from __future__ import annotations

import importlib
import json
import os
import unittest
from unittest.mock import Mock, patch

import line_webhook
from line_webhook import LineWebhookHandler


class FakeWriter:
    def __init__(self, error: Exception = None) -> None:
        self.error = error
        self.written = b""

    def write(self, data: bytes) -> None:
        if self.error:
            raise self.error
        self.written += data


class LineWebhookResponseTest(unittest.TestCase):
    def _handler_with_writer(self, writer: FakeWriter):
        handler = object.__new__(LineWebhookHandler)
        handler.wfile = writer
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        return handler

    def test_send_json_normal_response_still_works(self) -> None:
        writer = FakeWriter()
        handler = self._handler_with_writer(writer)

        handler._send_json(200, {"status": "ok"})

        self.assertEqual(writer.written, json.dumps({"status": "ok"}).encode("utf-8"))
        handler.send_response.assert_called_once_with(200)
        handler.send_header.assert_any_call("Content-Type", "application/json")
        handler.end_headers.assert_called_once()

    def test_send_json_handles_connection_aborted(self) -> None:
        handler = self._handler_with_writer(FakeWriter(ConnectionAbortedError()))

        with patch("builtins.print") as print_mock:
            handler._send_json(200, {"status": "ok"})

        print_mock.assert_called_once_with(
            "[WARN] Client disconnected before response was fully sent."
        )

    def test_send_json_handles_broken_pipe(self) -> None:
        handler = self._handler_with_writer(FakeWriter(BrokenPipeError()))

        with patch("builtins.print") as print_mock:
            handler._send_json(200, {"status": "ok"})

        print_mock.assert_called_once_with(
            "[WARN] Client disconnected before response was fully sent."
        )

    def test_send_json_handles_connection_reset(self) -> None:
        handler = self._handler_with_writer(FakeWriter(ConnectionResetError()))

        with patch("builtins.print") as print_mock:
            handler._send_json(200, {"status": "ok"})

        print_mock.assert_called_once_with(
            "[WARN] Client disconnected before response was fully sent."
        )


class LineWebhookConfigTest(unittest.TestCase):
    def test_port_uses_environment_with_local_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            reloaded = importlib.reload(line_webhook)
            self.assertEqual(reloaded.HOST, "0.0.0.0")
            self.assertEqual(reloaded.PORT, 8000)

        with patch.dict(os.environ, {"PORT": "8080"}, clear=True):
            reloaded = importlib.reload(line_webhook)
            self.assertEqual(reloaded.HOST, "0.0.0.0")
            self.assertEqual(reloaded.PORT, 8080)

        importlib.reload(line_webhook)


if __name__ == "__main__":
    unittest.main()
