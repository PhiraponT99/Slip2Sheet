from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from expense_tracker.merchant_aliases import add_alias, load_aliases, normalize_merchant


class MerchantAliasesTest(unittest.TestCase):
    def test_add_alias_persists_json_and_normalizes_merchant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "merchant_aliases.json"

            add_alias("CP AXTRA PUBLIC COMPANY LIMITED (HEAD", "Lotus's", path)

            self.assertEqual(
                load_aliases(path),
                {"CP AXTRA PUBLIC COMPANY LIMITED (HEAD": "Lotus's"},
            )
            self.assertEqual(
                normalize_merchant("CP AXTRA PUBLIC COMPANY LIMITED (HEAD", path),
                "Lotus's",
            )
            self.assertEqual(normalize_merchant("Unknown", path), "Unknown")

    def test_add_alias_rejects_empty_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "merchant_aliases.json"

            with self.assertRaises(ValueError):
                add_alias("", "Lotus's", path)
            with self.assertRaises(ValueError):
                add_alias("Raw", "", path)


if __name__ == "__main__":
    unittest.main()
