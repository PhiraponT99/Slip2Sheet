from __future__ import annotations

import unittest

from expense_tracker.trends import calculate_trend, calculate_trend_report


HEADER = [
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
]


def month_rows(month: str, amounts: list[float]) -> list[list[str]]:
    rows = [HEADER]
    for index, amount in enumerate(amounts, start=1):
        rows.append(
            [
                f"{month}-{index:02d}",
                "10:00",
                "Shop",
                "food",
                str(amount),
                "",
                "",
                "",
                "",
                f"slip{index}.jpg",
                "",
                f"{month}-{index:02d}|10:00|Shop|{amount}",
            ]
        )
    return rows


class TrendsTest(unittest.TestCase):
    def test_increasing_trend(self) -> None:
        report = calculate_trend_report(
            {
                "2026-04": month_rows("2026-04", [100.0]),
                "2026-05": month_rows("2026-05", [200.0]),
            }
        )

        self.assertEqual(report["months"], [
            {"month": "2026-04", "total_expense": 100.0},
            {"month": "2026-05", "total_expense": 200.0},
        ])
        self.assertEqual(report["trend"]["direction"], "UP")
        self.assertEqual(report["trend"]["change_percent"], 100.0)
        self.assertEqual(
            report["trend"]["message"],
            "Spending increased compared to previous month.",
        )

    def test_decreasing_trend(self) -> None:
        report = calculate_trend_report(
            {
                "2026-04": month_rows("2026-04", [8200.0]),
                "2026-05": month_rows("2026-05", [7600.0]),
                "2026-06": month_rows("2026-06", [50.0]),
            }
        )

        self.assertEqual([month["month"] for month in report["months"]], [
            "2026-04",
            "2026-05",
            "2026-06",
        ])
        self.assertEqual(report["trend"]["direction"], "DOWN")
        self.assertEqual(report["trend"]["change_percent"], -99.3)
        self.assertEqual(
            report["trend"]["message"],
            "Spending decreased compared to previous month.",
        )

    def test_stable_trend(self) -> None:
        trend = calculate_trend(
            [
                {"month": "2026-05", "total_expense": 100.0},
                {"month": "2026-06", "total_expense": 104.9},
            ]
        )

        self.assertEqual(trend["direction"], "STABLE")
        self.assertEqual(trend["change_percent"], 4.9)
        self.assertEqual(
            trend["message"],
            "Spending is stable compared to previous month.",
        )

    def test_single_month(self) -> None:
        trend = calculate_trend([{"month": "2026-06", "total_expense": 50.0}])

        self.assertEqual(trend["direction"], "STABLE")
        self.assertEqual(trend["change_percent"], 0.0)
        self.assertEqual(
            trend["message"],
            "Not enough monthly data to calculate a trend.",
        )

    def test_empty_data(self) -> None:
        report = calculate_trend_report({})

        self.assertEqual(report["months"], [])
        self.assertEqual(report["trend"]["direction"], "STABLE")
        self.assertEqual(report["trend"]["change_percent"], 0.0)


if __name__ == "__main__":
    unittest.main()
