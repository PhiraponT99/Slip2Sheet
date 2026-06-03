from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from expense_tracker.exports import EXPORT_COLUMNS, export_month_report


REPORT = {
    "month": "2026-06",
    "total_expense": 101.0,
    "category_totals": {"food": 65.0, "drink": 36.0},
    "insights": {
        "top_category": "food",
        "top_category_amount": 65.0,
        "top_merchant": "Rice Shop",
        "top_merchant_amount": 65.0,
        "transaction_count": 2,
        "average_transaction": 50.5,
    },
    "transactions": [
        {
            "date": "2026-06-03",
            "time": "10:00",
            "merchant": "Rice Shop",
            "category": "food",
            "amount": 65.0,
            "original_amount": 65.0,
            "discount": None,
            "payment_method": "PromptPay",
            "note": None,
            "source_image": "slip1.jpg",
            "created_at": "2026-06-03T10:01:00",
            "transaction_key": "2026-06-03|10:00|Rice Shop|65.0",
        },
        {
            "date": "2026-06-03",
            "time": "14:19",
            "merchant": "Cafe",
            "category": "drink",
            "amount": 36.0,
            "original_amount": 45.0,
            "discount": 9.0,
            "payment_method": None,
            "note": "discount",
            "source_image": "slip2.jpg",
            "created_at": "2026-06-03T14:20:00",
            "transaction_key": "2026-06-03|14:19|Cafe|36.0",
        },
    ],
}


class ExportTest(unittest.TestCase):
    def test_export_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = export_month_report(REPORT, "csv", tmpdir)
            export_file = Path(tmpdir) / "2026-06.csv"

            self.assertEqual(result["month"], "2026-06")
            self.assertEqual(result["export_format"], "csv")
            self.assertEqual(result["transaction_count"], 2)
            self.assertTrue(export_file.exists())

            with export_file.open("r", encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))

            self.assertEqual(rows[0]["merchant"], "Rice Shop")
            self.assertEqual(rows[0]["discount"], "")
            self.assertEqual(rows[1]["category"], "drink")
            self.assertEqual(list(rows[0].keys()), EXPORT_COLUMNS)

    def test_export_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = export_month_report(REPORT, "json", tmpdir)
            export_file = Path(tmpdir) / "2026-06.json"

            self.assertEqual(result["export_format"], "json")
            self.assertEqual(result["transaction_count"], 2)
            self.assertTrue(export_file.exists())

            with export_file.open("r", encoding="utf-8") as file:
                payload = json.load(file)

            self.assertEqual(payload["month"], "2026-06")
            self.assertEqual(payload["total_expense"], 101.0)
            self.assertEqual(payload["category_totals"], {"food": 65.0, "drink": 36.0})
            self.assertEqual(payload["insights"]["top_merchant"], "Rice Shop")
            self.assertEqual(len(payload["transactions"]), 2)

    def test_empty_month_export(self) -> None:
        report = {
            "month": "2026-07",
            "total_expense": 0.0,
            "category_totals": {},
            "insights": {
                "top_category": None,
                "top_category_amount": None,
                "top_merchant": None,
                "top_merchant_amount": None,
                "transaction_count": 0,
                "average_transaction": 0.0,
            },
            "transactions": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            result = export_month_report(report, "csv", tmpdir)
            export_file = Path(tmpdir) / "2026-07.csv"

            self.assertEqual(result["transaction_count"], 0)
            with export_file.open("r", encoding="utf-8", newline="") as file:
                rows = list(csv.reader(file))

            self.assertEqual(rows, [EXPORT_COLUMNS])

    def test_export_directory_auto_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir) / "nested" / "exports"

            result = export_month_report(REPORT, "json", export_dir)

            self.assertTrue(export_dir.exists())
            self.assertTrue((export_dir / "2026-06.json").exists())
            self.assertEqual(result["export_file"], str(export_dir / "2026-06.json").replace("\\", "/"))


if __name__ == "__main__":
    unittest.main()
