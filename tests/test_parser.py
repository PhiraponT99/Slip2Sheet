from __future__ import annotations

import unittest
from unittest.mock import patch

from expense_tracker.parser import extract_transaction


class ParserTest(unittest.TestCase):
    def test_real_thai_slip_amounts_and_merchant(self) -> None:
        raw_text = "\n".join(
            [
                "\u0e0a\u0e33\u0e23\u0e30\u0e40\u0e07\u0e34\u0e19\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08",
                "03/06/2026 14:19",
                "\u0e27\u0e31\u0e22(\u0e15\u0e17\u0e22",
                "\u0e01\u0e30\u0e40\u0e1e\u0e23\u0e32\u0e2b\u0e2d\u0e21",
                "\u0e2d\u0e32\u0e2b\u0e32\u0e23 \u0e02\u0e2d\u0e07\u0e2b\u0e27\u0e32\u0e19 \u0e40\u0e04\u0e23\u0e37\u0e48\u0e2d\u0e07\u0e14\u0e37\u0e48\u0e21",
                "\u0e04\u0e48\u0e32\u0e2a\u0e34\u0e19\u0e04\u0e49\u0e32/\u0e1a\u0e23\u0e34\u0e01\u0e32\u0e23               65 \u0e1a\u0e32\u0e17",
                "\u0e2a\u0e34\u0e17\u0e18\u0e34\u0e41\u0e17\u0e22\u0e0a\u0e48\u0e27\u0e22\u0e44\u0e17\u0e22\u0e1e\u0e25\u0e31\u0e2a           -39 \u0e1a\u0e32\u0e17",
                "\u0e08\u0e4d\u0e32\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19\u0e17\u0e35\u0e48\u0e0a\u0e4d\u0e32\u0e23\u0e30              26 \u0e1a\u0e32\u0e17",
            ]
        )

        result = extract_transaction(raw_text).to_dict()

        self.assertEqual(result["date"], "2026-06-03")
        self.assertEqual(result["time"], "14:19")
        self.assertEqual(result["merchant"], "\u0e01\u0e30\u0e40\u0e1e\u0e23\u0e32\u0e2b\u0e2d\u0e21")
        self.assertEqual(result["amount"], 26.0)
        self.assertEqual(result["original_amount"], 65.0)
        self.assertEqual(result["discount"], 39.0)

    def test_amount_falls_back_when_no_paid_label_exists(self) -> None:
        raw_text = "\n".join(
            [
                "2026-06-03 10:25",
                "\u0e1c\u0e39\u0e49\u0e23\u0e31\u0e1a\u0e40\u0e07\u0e34\u0e19: \u0e23\u0e49\u0e32\u0e19\u0e15\u0e32\u0e21\u0e2a\u0e31\u0e48\u0e07",
                "\u0e08\u0e33\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19 65.00 \u0e1a\u0e32\u0e17",
            ]
        )

        result = extract_transaction(raw_text).to_dict()

        self.assertEqual(result["amount"], 65.0)
        self.assertIsNone(result["original_amount"])
        self.assertIsNone(result["discount"])

    def test_amount_ranking_prefers_payment_amount_over_masked_account(self) -> None:
        raw_text = "\n".join(
            [
                "2026-06-03 10:25",
                "XXX-XXX073-8",
                "\u0e08\u0e4d\u0e32\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19 58.00",
            ]
        )

        result = extract_transaction(raw_text).to_dict()

        self.assertEqual(result["amount"], 58.0)

    def test_scb_bill_payment_multiline_merchant_after_to_label(self) -> None:
        raw_text = "\n".join(
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
            result = extract_transaction(raw_text).to_dict()

        self.assertEqual(result["merchant"], "CP AXTRA PUBLIC COMPANY LIMITED (HEAD")
        self.assertEqual(result["amount"], 58.0)

    def test_success_header_is_ignored_as_merchant(self) -> None:
        raw_text = "\n".join(
            [
                "@ \u0e08\u0e48\u0e32\u0e22\u0e1a\u0e34\u0e25\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08",
                "04/06/2026 12:26",
                "\u0e44\u0e1b\u0e22\u0e31\u0e07 | CP AXTRA PUBLIC COMPANY",
                "\u0e08\u0e4d\u0e32\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19 58.00",
            ]
        )

        with patch("expense_tracker.parser.normalize_merchant", side_effect=lambda merchant: merchant):
            result = extract_transaction(raw_text).to_dict()

        self.assertNotEqual(result["merchant"], "@ \u0e08\u0e48\u0e32\u0e22\u0e1a\u0e34\u0e25\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08")
        self.assertEqual(result["merchant"], "CP AXTRA PUBLIC COMPANY")

    def test_fallback_merchant_still_works(self) -> None:
        raw_text = "\n".join(
            [
                "2026-06-03 10:25",
                "\u0e01\u0e30\u0e40\u0e1e\u0e23\u0e32\u0e2b\u0e2d\u0e21",
                "\u0e2d\u0e32\u0e2b\u0e32\u0e23 \u0e02\u0e2d\u0e07\u0e2b\u0e27\u0e32\u0e19 \u0e40\u0e04\u0e23\u0e37\u0e48\u0e2d\u0e07\u0e14\u0e37\u0e48\u0e21",
                "\u0e08\u0e33\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19 65.00",
            ]
        )

        result = extract_transaction(raw_text).to_dict()

        self.assertEqual(result["merchant"], "\u0e01\u0e30\u0e40\u0e1e\u0e23\u0e32\u0e2b\u0e2d\u0e21")

    def test_scb_transfer_prefers_merchant_after_to_label(self) -> None:
        raw_text = "\n".join(
            [
                "\u0e42\u0e2d\u0e19\u0e40\u0e07\u0e34\u0e19\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08",
                "03/06/2026 14:19",
                "\u0e15\u0e23\u0e27\u0e08\u0e2a\u0e2d\u0e1a\u0e2a\u0e16\u0e32\u0e19\u0e30\u0e01\u0e32\u0e23\u0e08\u0e48\u0e32\u0e22\u0e40\u0e07\u0e34\u0e19",
                "\u0e08\u0e32\u0e01",
                "MR TEST USER",
                "\u0e44\u0e1b\u0e22\u0e31\u0e07",
                "CP AXTRA PUBLIC COMPANY LIMITED",
                "\u0e08\u0e33\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19",
                "50.00 \u0e1a\u0e32\u0e17",
                "\u0e40\u0e25\u0e02\u0e17\u0e35\u0e48\u0e2d\u0e49\u0e32\u0e07\u0e2d\u0e34\u0e07 123456789",
                "Biller ID 0105555000000",
            ]
        )

        with patch("expense_tracker.parser.normalize_merchant", side_effect=lambda merchant: merchant):
            result = extract_transaction(raw_text).to_dict()

        self.assertEqual(result["merchant"], "CP AXTRA PUBLIC COMPANY LIMITED")
        self.assertEqual(result["amount"], 50.0)

    def test_scb_transfer_joins_wrapped_to_merchant_and_uses_amount_label(self) -> None:
        raw_text = "\n".join(
            [
                "\u0e42\u0e2d\u0e19\u0e40\u0e07\u0e34\u0e19\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08",
                "03/06/2026 14:19",
                "\u0e08\u0e32\u0e01",
                "123-x-xxxxx-9",
                "\u0e44\u0e1b\u0e22\u0e31\u0e07 CP AXTRA PUBLIC COMPANY",
                "LIMITED (HEAD",
                "Biller ID : 0105555000000",
                "\u0e2b\u0e21\u0e32\u0e22\u0e40\u0e25\u0e02\u0e23\u0e49\u0e32\u0e19\u0e04\u0e49\u0e32 123456789",
                "\u0e40\u0e25\u0e02\u0e17\u0e35\u0e48\u0e2d\u0e49\u0e32\u0e07\u0e2d\u0e34\u0e07 987654321",
                "\u0e08\u0e33\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19                                                             50.00",
                "\u0e1a\u0e31\u0e19\u0e17\u0e36\u0e01\u0e0a\u0e48\u0e27\u0e22\u0e08\u0e33",
                "73.0",
            ]
        )

        with patch("expense_tracker.parser.normalize_merchant", side_effect=lambda merchant: merchant):
            result = extract_transaction(raw_text).to_dict()

        self.assertEqual(result["merchant"], "CP AXTRA PUBLIC COMPANY LIMITED (HEAD")
        self.assertEqual(result["amount"], 50.0)

    def test_merchant_alias_is_applied_after_extraction(self) -> None:
        raw_text = "\n".join(
            [
                "\u0e42\u0e2d\u0e19\u0e40\u0e07\u0e34\u0e19\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08",
                "03/06/2026 14:19",
                "\u0e08\u0e32\u0e01",
                "123-x-xxxxx-9",
                "\u0e44\u0e1b\u0e22\u0e31\u0e07 CP AXTRA PUBLIC COMPANY",
                "LIMITED (HEAD",
                "Biller ID : 0105555000000",
                "\u0e08\u0e33\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19 50.00",
            ]
        )

        with patch("expense_tracker.parser.normalize_merchant", return_value="Lotus's"):
            result = extract_transaction(raw_text).to_dict()

        self.assertEqual(result["merchant"], "Lotus's")


if __name__ == "__main__":
    unittest.main()
