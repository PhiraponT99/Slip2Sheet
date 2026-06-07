from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from expense_tracker.models import TransactionResult
from expense_tracker.sheets import (
    _build_sheets_service,
    append_transaction_to_sheet,
    build_sheet_row,
    detect_note,
    detect_payment_method,
    existing_transaction_keys,
    infer_category,
    monthly_tab_name,
    read_balance_from_sheet,
    save_balance_to_sheet,
    transaction_key,
)


class SheetsTest(unittest.TestCase):
    def _google_modules(self, credentials: object, service: object):
        google = types.ModuleType("google")
        google_auth = types.ModuleType("google.auth")
        google_auth.default = Mock(return_value=(credentials, "project-id"))
        google.auth = google_auth

        google_oauth2 = types.ModuleType("google.oauth2")
        service_account = types.ModuleType("google.oauth2.service_account")
        service_account.Credentials = Mock()
        service_account.Credentials.from_service_account_file = Mock(
            return_value=credentials
        )
        google_oauth2.service_account = service_account
        google.oauth2 = google_oauth2

        googleapiclient = types.ModuleType("googleapiclient")
        discovery = types.ModuleType("googleapiclient.discovery")
        discovery.build = Mock(return_value=service)
        googleapiclient.discovery = discovery

        modules = {
            "google": google,
            "google.auth": google_auth,
            "google.oauth2": google_oauth2,
            "google.oauth2.service_account": service_account,
            "googleapiclient": googleapiclient,
            "googleapiclient.discovery": discovery,
        }
        return modules, google_auth.default, service_account.Credentials, discovery.build

    def test_monthly_tab_name_uses_year_and_month(self) -> None:
        self.assertEqual(monthly_tab_name("2026-06-03"), "2026-06")

    def test_food_category_from_thai_merchant(self) -> None:
        self.assertEqual(infer_category("\u0e01\u0e30\u0e40\u0e1e\u0e23\u0e32\u0e2b\u0e2d\u0e21"), "food")
        self.assertEqual(infer_category("\u0e23\u0e49\u0e32\u0e19\u0e02\u0e49\u0e32\u0e27\u0e41\u0e01\u0e07"), "food")
        self.assertEqual(infer_category("CP AXTRA PUBLIC COMPANY LIMITED"), "food")
        self.assertEqual(infer_category("LOTUS'S"), "food")
        self.assertEqual(infer_category("Book Shop"), "other")

    def test_category_mapping_takes_precedence_over_fallback(self) -> None:
        with patch("expense_tracker.sheets.lookup_category", return_value="convenience"):
            self.assertEqual(infer_category("7-Eleven"), "convenience")

    def test_category_mapping_falls_back_to_rules_when_missing(self) -> None:
        with patch("expense_tracker.sheets.lookup_category", return_value=None):
            self.assertEqual(infer_category("Cafe Amazon"), "drink")

    def test_drink_category_from_merchant_or_text(self) -> None:
        self.assertEqual(infer_category("Cafe Amazon"), "drink")
        self.assertEqual(infer_category(None, "coffee 85 baht"), "drink")

    def test_payment_method_and_note_detection(self) -> None:
        raw_text = "\n".join(
            [
                "Payment by PromptPay QR",
                "\u0e2a\u0e34\u0e17\u0e18\u0e34\u0e41\u0e17\u0e22\u0e0a\u0e48\u0e27\u0e22\u0e44\u0e17\u0e22\u0e1e\u0e25\u0e31\u0e2a           -39 \u0e1a\u0e32\u0e17",
            ]
        )

        self.assertEqual(detect_payment_method(raw_text), "PromptPay")
        self.assertEqual(
            detect_note(raw_text),
            "\u0e2a\u0e34\u0e17\u0e18\u0e34\u0e41\u0e17\u0e22\u0e0a\u0e48\u0e27\u0e22\u0e44\u0e17\u0e22\u0e1e\u0e25\u0e31\u0e2a           -39 \u0e1a\u0e32\u0e17",
        )

    def test_build_sheet_row(self) -> None:
        raw_text = "\n".join(
            [
                "PromptPay",
                "\u0e2a\u0e34\u0e17\u0e18\u0e34\u0e41\u0e17\u0e22\u0e0a\u0e48\u0e27\u0e22\u0e44\u0e17\u0e22\u0e1e\u0e25\u0e31\u0e2a           -39 \u0e1a\u0e32\u0e17",
            ]
        )
        transaction = TransactionResult(
            date="2026-06-03",
            time="14:19",
            merchant="\u0e01\u0e30\u0e40\u0e1e\u0e23\u0e32\u0e2b\u0e2d\u0e21",
            amount=26.0,
            original_amount=65.0,
            discount=39.0,
            raw_text=raw_text,
        )

        with patch("expense_tracker.sheets.lookup_category", return_value=None):
            row = build_sheet_row(transaction, "./samples/slip1.jpg")

        self.assertEqual(row[:10], [
            "2026-06-03",
            "14:19",
            "\u0e01\u0e30\u0e40\u0e1e\u0e23\u0e32\u0e2b\u0e2d\u0e21",
            "food",
            26.0,
            65.0,
            39.0,
            "PromptPay",
            "\u0e2a\u0e34\u0e17\u0e18\u0e34\u0e41\u0e17\u0e22\u0e0a\u0e48\u0e27\u0e22\u0e44\u0e17\u0e22\u0e1e\u0e25\u0e31\u0e2a           -39 \u0e1a\u0e32\u0e17",
            "slip1.jpg",
        ])
        self.assertRegex(row[10], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        self.assertEqual(
            row[11],
            "2026-06-03|14:19|\u0e01\u0e30\u0e40\u0e1e\u0e23\u0e32\u0e2b\u0e2d\u0e21|26.0",
        )

    def test_transaction_key_uses_date_time_merchant_and_amount(self) -> None:
        transaction = TransactionResult(
            date="2026-06-03",
            time="14:19",
            merchant="\u0e01\u0e30\u0e40\u0e1e\u0e23\u0e32\u0e2b\u0e2d\u0e21",
            amount=26.0,
            original_amount=None,
            discount=None,
            raw_text=None,
        )

        self.assertEqual(
            transaction_key(transaction),
            "2026-06-03|14:19|\u0e01\u0e30\u0e40\u0e1e\u0e23\u0e32\u0e2b\u0e2d\u0e21|26.0",
        )

    def test_transaction_key_uses_normalized_merchant(self) -> None:
        transaction = TransactionResult(
            date="2026-06-03",
            time="14:19",
            merchant="CP AXTRA PUBLIC COMPANY LIMITED (HEAD",
            amount=50.0,
            original_amount=None,
            discount=None,
            raw_text=None,
        )

        with patch("expense_tracker.sheets.normalize_merchant", return_value="Lotus's"):
            self.assertEqual(
                transaction_key(transaction),
                "2026-06-03|14:19|Lotus's|50.0",
            )

    def test_existing_transaction_keys_reads_transaction_key_column(self) -> None:
        rows = [
            [
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
            ],
            ["2026-06-03", "14:19", "Shop", "other", "26.0", "", "", "", "", "", "", "2026-06-03|14:19|Shop|26.0"],
            ["2026-06-04", "10:00", "Cafe"],
            ["2026-06-05", "11:00", "Rice", "food", "60.0", "", "", "", "", "", "", ""],
        ]

        self.assertEqual(
            existing_transaction_keys(rows),
            {"2026-06-03|14:19|Shop|26.0"},
        )

    def test_build_sheets_service_uses_service_account_file_when_set(self) -> None:
        credentials = object()
        service = object()
        modules, default_mock, credentials_mock, build_mock = self._google_modules(
            credentials,
            service,
        )

        with tempfile.NamedTemporaryFile() as credentials_file:
            with patch.dict(sys.modules, modules):
                result = _build_sheets_service(credentials_file.name)

        self.assertIs(result, service)
        credentials_mock.from_service_account_file.assert_called_once_with(
            credentials_file.name,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        default_mock.assert_not_called()
        build_mock.assert_called_once_with("sheets", "v4", credentials=credentials)

    def test_build_sheets_service_uses_default_credentials_without_file(self) -> None:
        credentials = object()
        service = object()
        modules, default_mock, credentials_mock, build_mock = self._google_modules(
            credentials,
            service,
        )

        with patch.dict(sys.modules, modules):
            result = _build_sheets_service()

        self.assertIs(result, service)
        default_mock.assert_called_once_with(
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        credentials_mock.from_service_account_file.assert_not_called()
        build_mock.assert_called_once_with("sheets", "v4", credentials=credentials)

    def test_append_transaction_allows_default_credentials_mode(self) -> None:
        transaction = TransactionResult(
            date="2026-06-03",
            time="14:19",
            merchant="Shop",
            amount=26.0,
            original_amount=None,
            discount=None,
            raw_text=None,
        )
        service = Mock()
        spreadsheets = service.spreadsheets.return_value
        append_call = spreadsheets.values.return_value.append.return_value
        append_call.execute.return_value = {}

        with (
            patch.dict(os.environ, {"GOOGLE_SHEET_ID": "sheet-id"}, clear=True),
            patch("expense_tracker.sheets.load_dotenv"),
            patch(
                "expense_tracker.sheets._build_sheets_service",
                return_value=service,
            ) as build_mock,
            patch("expense_tracker.sheets._ensure_monthly_tab"),
            patch("expense_tracker.sheets._read_monthly_rows", return_value=[]),
        ):
            result = append_transaction_to_sheet(transaction, "slip.jpg")

        self.assertTrue(result["saved"])
        self.assertFalse(result["duplicate"])
        self.assertEqual(result["sheet_tab"], "2026-06")
        build_mock.assert_called_once_with(None)

    def test_save_balance_appends_settings_row_when_missing(self) -> None:
        service = Mock()
        values = service.spreadsheets.return_value.values.return_value

        with (
            patch.dict(os.environ, {"GOOGLE_SHEET_ID": "sheet-id"}, clear=True),
            patch("expense_tracker.sheets.load_dotenv"),
            patch("expense_tracker.sheets._build_sheets_service", return_value=service),
            patch("expense_tracker.sheets._ensure_settings_tab") as ensure_mock,
            patch(
                "expense_tracker.sheets._read_settings_rows",
                return_value=[["Key", "Value", "UpdatedAt"]],
            ),
        ):
            result = save_balance_to_sheet("9,460.90")

        self.assertEqual(result["key"], "current_balance")
        self.assertEqual(result["amount"], 9460.9)
        self.assertEqual(result["sheet_tab"], "Settings")
        ensure_mock.assert_called_once_with(service, "sheet-id")
        values.append.assert_called_once()
        append_kwargs = values.append.call_args.kwargs
        self.assertEqual(append_kwargs["range"], "'Settings'!A:C")
        self.assertEqual(
            append_kwargs["body"]["values"][0][:2],
            ["current_balance", 9460.9],
        )

    def test_save_balance_updates_existing_settings_row(self) -> None:
        service = Mock()
        values = service.spreadsheets.return_value.values.return_value

        with (
            patch.dict(os.environ, {"GOOGLE_SHEET_ID": "sheet-id"}, clear=True),
            patch("expense_tracker.sheets.load_dotenv"),
            patch("expense_tracker.sheets._build_sheets_service", return_value=service),
            patch("expense_tracker.sheets._ensure_settings_tab"),
            patch(
                "expense_tracker.sheets._read_settings_rows",
                return_value=[
                    ["Key", "Value", "UpdatedAt"],
                    ["current_balance", "9000.00", "old"],
                ],
            ),
        ):
            result = save_balance_to_sheet(9460.9)

        self.assertEqual(result["amount"], 9460.9)
        values.update.assert_called_once()
        update_kwargs = values.update.call_args.kwargs
        self.assertEqual(update_kwargs["range"], "'Settings'!B2:C2")
        self.assertEqual(update_kwargs["body"]["values"][0][0], 9460.9)

    def test_read_balance_from_settings(self) -> None:
        service = Mock()

        with (
            patch.dict(os.environ, {"GOOGLE_SHEET_ID": "sheet-id"}, clear=True),
            patch("expense_tracker.sheets.load_dotenv"),
            patch("expense_tracker.sheets._build_sheets_service", return_value=service),
            patch("expense_tracker.sheets._ensure_settings_tab") as ensure_mock,
            patch(
                "expense_tracker.sheets._read_settings_rows",
                return_value=[
                    ["Key", "Value", "UpdatedAt"],
                    ["other", "1", "old"],
                    ["current_balance", "9,460.90", "now"],
                ],
            ),
        ):
            balance = read_balance_from_sheet()

        self.assertEqual(balance, 9460.9)
        ensure_mock.assert_called_once_with(service, "sheet-id")

    def test_read_balance_from_settings_returns_none_when_missing(self) -> None:
        service = Mock()

        with (
            patch.dict(os.environ, {"GOOGLE_SHEET_ID": "sheet-id"}, clear=True),
            patch("expense_tracker.sheets.load_dotenv"),
            patch("expense_tracker.sheets._build_sheets_service", return_value=service),
            patch("expense_tracker.sheets._ensure_settings_tab"),
            patch(
                "expense_tracker.sheets._read_settings_rows",
                return_value=[["Key", "Value", "UpdatedAt"]],
            ),
        ):
            self.assertIsNone(read_balance_from_sheet())


if __name__ == "__main__":
    unittest.main()
