from __future__ import annotations

import unittest
from unittest.mock import patch

from expense_tracker.parser_diagnostics import (
    analyze_parser_accuracy,
    log_parser_investigation,
)


class ParserDiagnosticsTest(unittest.TestCase):
    def test_report_identifies_expected_amount_after_ranking_fix(self) -> None:
        raw_text = "\n".join(
            [
                "2026-06-03",
                "14:19",
                "merchant: Test Shop",
                "XXX-XXX073-8",
                "\u0e08\u0e4d\u0e32\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19 58.00",
            ]
        )

        report = analyze_parser_accuracy(raw_text, expected_amount=58.0)

        self.assertEqual(report["selected_amount"], 58.0)
        self.assertEqual(report["selected_line"], "\u0e08\u0e4d\u0e32\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19 58.00")
        self.assertGreater(report["selected_score"], 0)
        self.assertEqual(report["root_cause"], "parser_selected_expected_amount")
        self.assertIn(58.0, [candidate["value"] for candidate in report["ocr_amount_candidates"]])
        self.assertIn(73.0, [candidate["value"] for candidate in report["ocr_amount_candidates"]])

    def test_report_identifies_ocr_likely_missed_expected_amount(self) -> None:
        raw_text = "\n".join(
            [
                "2026-06-03",
                "14:19",
                "merchant: Test Shop",
                "amount 73.00 THB",
            ]
        )

        report = analyze_parser_accuracy(raw_text, expected_amount=58.0)

        self.assertEqual(report["selected_amount"], 73.0)
        self.assertEqual(
            report["root_cause"],
            "ocr_likely_missed_or_misread_expected_amount",
        )

    def test_report_without_expected_amount_requests_review(self) -> None:
        raw_text = "amount 73.00 THB"

        report = analyze_parser_accuracy(raw_text)

        self.assertEqual(report["selected_amount"], 73.0)
        self.assertEqual(report["selected_line"], raw_text)
        self.assertIsInstance(report["selected_score"], int)
        self.assertEqual(report["root_cause"], "needs_expected_amount_or_slip_review")

    def test_log_parser_investigation_prints_ocr_text_and_report(self) -> None:
        raw_text = "amount 73.00 THB"

        with patch("builtins.print") as print_mock:
            report = log_parser_investigation(raw_text)

        self.assertEqual(report["selected_amount"], 73.0)
        print_mock.assert_any_call("[DEBUG] OCR text:")
        print_mock.assert_any_call(raw_text)
        print_mock.assert_any_call("[DEBUG] Parser investigation report:")


if __name__ == "__main__":
    unittest.main()
