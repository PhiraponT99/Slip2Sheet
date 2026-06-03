from __future__ import annotations

import unittest
from unittest.mock import patch

from expense_tracker.models import TransactionResult
from expense_tracker.sheets import (
    build_sheet_row,
    detect_note,
    detect_payment_method,
    existing_transaction_keys,
    infer_category,
    monthly_tab_name,
    transaction_key,
)


class SheetsTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
