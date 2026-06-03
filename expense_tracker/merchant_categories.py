from __future__ import annotations

import json
from pathlib import Path


MERCHANT_CATEGORIES_PATH = Path("merchant_categories.json")
ALLOWED_CATEGORIES = {
    "food",
    "drink",
    "convenience",
    "transport",
    "rent",
    "phone",
    "subscription",
    "shopping",
    "health",
    "other",
}


def load_categories(path: str | Path = MERCHANT_CATEGORIES_PATH) -> dict[str, str]:
    category_path = Path(path)
    if not category_path.exists():
        return {}

    try:
        data = json.loads(category_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    if not isinstance(data, dict):
        return {}

    return {
        str(merchant): str(category).strip().lower()
        for merchant, category in data.items()
        if str(merchant).strip() and _is_allowed_category(str(category))
    }


def save_categories(
    categories: dict[str, str],
    path: str | Path = MERCHANT_CATEGORIES_PATH,
) -> None:
    category_path = Path(path)
    category_path.write_text(
        json.dumps(categories, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def add_category(
    merchant: str,
    category: str,
    path: str | Path = MERCHANT_CATEGORIES_PATH,
) -> dict[str, str]:
    merchant = merchant.strip()
    category = category.strip().lower()
    if not merchant:
        raise ValueError("Merchant name cannot be empty.")
    if not _is_allowed_category(category):
        raise ValueError(f"Category must be one of: {', '.join(sorted(ALLOWED_CATEGORIES))}.")

    categories = load_categories(path)
    categories[merchant] = category
    save_categories(categories, path)
    return categories


def lookup_category(
    merchant: str | None,
    path: str | Path = MERCHANT_CATEGORIES_PATH,
) -> str | None:
    if merchant is None:
        return None

    return load_categories(path).get(merchant)


def _is_allowed_category(category: str) -> bool:
    return category.strip().lower() in ALLOWED_CATEGORIES
