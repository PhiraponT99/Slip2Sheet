from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_BALANCE_PATH = Path("data") / "balance.json"


def save_balance(
    amount: float | int | str,
    source: str = "line",
    path: Path = DEFAULT_BALANCE_PATH,
) -> dict[str, Any]:
    balance_amount = _parse_balance_amount(amount)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "amount": balance_amount,
        "source": source,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def read_balance(path: Path = DEFAULT_BALANCE_PATH) -> float | None:
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return _parse_balance_amount(payload.get("amount"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _parse_balance_amount(amount: float | int | str | None) -> float:
    if amount is None:
        raise ValueError("Balance amount is required.")

    if isinstance(amount, str):
        amount = amount.replace(",", "").strip()

    value = float(amount)
    if value < 0:
        raise ValueError("Balance amount cannot be negative.")
    return value
