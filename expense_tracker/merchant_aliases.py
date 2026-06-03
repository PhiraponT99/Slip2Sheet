from __future__ import annotations

import json
from pathlib import Path


MERCHANT_ALIASES_PATH = Path("merchant_aliases.json")


def load_aliases(path: str | Path = MERCHANT_ALIASES_PATH) -> dict[str, str]:
    alias_path = Path(path)
    if not alias_path.exists():
        return {}

    try:
        data = json.loads(alias_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    if not isinstance(data, dict):
        return {}

    return {
        str(raw_name): str(alias)
        for raw_name, alias in data.items()
        if str(raw_name).strip() and str(alias).strip()
    }


def save_aliases(
    aliases: dict[str, str],
    path: str | Path = MERCHANT_ALIASES_PATH,
) -> None:
    alias_path = Path(path)
    alias_path.write_text(
        json.dumps(aliases, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def add_alias(
    raw_name: str,
    alias: str,
    path: str | Path = MERCHANT_ALIASES_PATH,
) -> dict[str, str]:
    raw_name = raw_name.strip()
    alias = alias.strip()
    if not raw_name:
        raise ValueError("Raw merchant name cannot be empty.")
    if not alias:
        raise ValueError("Merchant alias cannot be empty.")

    aliases = load_aliases(path)
    aliases[raw_name] = alias
    save_aliases(aliases, path)
    return aliases


def normalize_merchant(
    merchant: str | None,
    path: str | Path = MERCHANT_ALIASES_PATH,
) -> str | None:
    if merchant is None:
        return None

    aliases = load_aliases(path)
    return aliases.get(merchant, merchant)
