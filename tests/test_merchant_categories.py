from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from expense_tracker.merchant_categories import (
    add_category,
    load_categories,
    lookup_category,
)


class MerchantCategoriesTest(unittest.TestCase):
    def test_add_category_persists_json_and_looks_up_category(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "merchant_categories.json"

            add_category("Lotus's", "food", path)

            self.assertEqual(load_categories(path), {"Lotus's": "food"})
            self.assertEqual(lookup_category("Lotus's", path), "food")
            self.assertIsNone(lookup_category("Unknown", path))

    def test_add_category_rejects_invalid_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "merchant_categories.json"

            with self.assertRaises(ValueError):
                add_category("", "food", path)
            with self.assertRaises(ValueError):
                add_category("Lotus's", "not-a-category", path)


if __name__ == "__main__":
    unittest.main()
