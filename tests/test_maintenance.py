from __future__ import annotations

import unittest

from expense_tracker.maintenance import (
    DUPLICATE_NOTE,
    build_transaction_key_from_row,
    duplicate_rows_to_mark,
    missing_key_updates,
    needs_column_expansion,
    needs_transaction_key_header,
)


class MaintenanceTest(unittest.TestCase):
    def test_build_transaction_key_from_row(self) -> None:
        row = ["2026-06-03", "14:19", "กะเพราหอม", "food", "26"]

        self.assertEqual(
            build_transaction_key_from_row(row),
            "2026-06-03|14:19|กะเพราหอม|26.0",
        )

    def test_missing_key_updates_skips_existing_keys(self) -> None:
        rows = [
            ["Date", "Time", "Merchant", "Category", "Amount", "", "", "", "", "", "", "TransactionKey"],
            ["2026-06-03", "14:19", "Shop", "food", "26"],
            ["2026-06-04", "10:00", "Cafe", "drink", "40", "", "", "", "", "", "", "existing"],
            ["2026-06-05", "11:00", "Bad", "food", "not-a-number"],
        ]

        self.assertEqual(
            missing_key_updates(rows),
            [(2, "2026-06-03|14:19|Shop|26.0")],
        )

    def test_old_sheet_with_11_columns_needs_expansion(self) -> None:
        self.assertTrue(needs_column_expansion(11))
        self.assertTrue(needs_column_expansion(None))
        self.assertFalse(needs_column_expansion(12))
        self.assertFalse(needs_column_expansion(15))

    def test_missing_transaction_key_header_is_detected(self) -> None:
        old_header = [["Date", "Time", "Merchant", "Category", "Amount", "", "", "", "Note", "SourceImage", "CreatedAt"]]
        new_header = [["Date", "Time", "Merchant", "Category", "Amount", "", "", "", "Note", "SourceImage", "CreatedAt", "TransactionKey"]]

        self.assertTrue(needs_transaction_key_header([]))
        self.assertTrue(needs_transaction_key_header(old_header))
        self.assertFalse(needs_transaction_key_header(new_header))

    def test_duplicate_rows_to_mark_keeps_oldest_row(self) -> None:
        rows = [
            ["Date", "Time", "Merchant", "Category", "Amount", "", "", "", "Note", "", "", "TransactionKey"],
            ["2026-06-03", "14:19", "Shop", "food", "26", "", "", "", "", "", "", "2026-06-03|14:19|Shop|26.0"],
            ["2026-06-03", "14:19", "Shop", "food", "26", "", "", "", "", "", "", "2026-06-03|14:19|Shop|26.0"],
            ["2026-06-03", "14:19", "Shop", "food", "26", "", "", "", DUPLICATE_NOTE, "", "", "2026-06-03|14:19|Shop|26.0"],
            ["2026-06-04", "10:00", "Cafe", "drink", "40"],
            ["2026-06-04", "10:00", "Cafe", "drink", "40"],
        ]

        self.assertEqual(duplicate_rows_to_mark(rows), [3, 6])


if __name__ == "__main__":
    unittest.main()
