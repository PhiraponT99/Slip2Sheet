from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TransactionResult:
    date: str | None
    time: str | None
    merchant: str | None
    amount: float | None
    raw_text: str | None
    original_amount: float | None = None
    discount: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "time": self.time,
            "merchant": self.merchant,
            "amount": self.amount,
            "original_amount": self.original_amount,
            "discount": self.discount,
            "raw_text": self.raw_text,
        }
