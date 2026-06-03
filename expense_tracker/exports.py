from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


EXPORT_COLUMNS = [
    "date",
    "time",
    "merchant",
    "category",
    "amount",
    "original_amount",
    "discount",
    "payment_method",
    "note",
    "source_image",
    "created_at",
    "transaction_key",
]


def export_month_report(
    report: dict[str, Any],
    export_format: str,
    export_dir: Path | str = "exports",
) -> dict[str, Any]:
    normalized_format = export_format.strip().lower()
    if normalized_format not in {"csv", "json"}:
        raise ValueError("Export format must be csv or json.")

    directory = Path(export_dir)
    directory.mkdir(parents=True, exist_ok=True)

    month = str(report["month"])
    export_file = directory / f"{month}.{normalized_format}"

    if normalized_format == "csv":
        _write_csv(export_file, report.get("transactions", []))
    else:
        _write_json(export_file, report)

    return {
        "month": month,
        "export_format": normalized_format,
        "export_file": str(export_file).replace("\\", "/"),
        "transaction_count": len(report.get("transactions", [])),
    }


def _write_csv(path: Path, transactions: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for transaction in transactions:
            writer.writerow(
                {column: _csv_value(transaction.get(column)) for column in EXPORT_COLUMNS}
            )


def _write_json(path: Path, report: dict[str, Any]) -> None:
    payload = {
        "month": report["month"],
        "total_expense": report["total_expense"],
        "category_totals": report["category_totals"],
        "insights": report["insights"],
        "transactions": report["transactions"],
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    return value
