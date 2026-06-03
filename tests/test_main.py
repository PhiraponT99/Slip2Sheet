from __future__ import annotations

import io
import json
import sys
import unittest
from unittest.mock import patch

import main


class MainCliTest(unittest.TestCase):
    def test_add_alias_command(self) -> None:
        argv = [
            "main.py",
            "--add-alias",
            "CP AXTRA PUBLIC COMPANY LIMITED (HEAD",
            "Lotus's",
        ]

        with (
            patch.object(sys, "argv", argv),
            patch("main.add_alias") as add_alias,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        add_alias.assert_called_once_with(
            "CP AXTRA PUBLIC COMPANY LIMITED (HEAD",
            "Lotus's",
        )
        self.assertEqual(
            json.loads(stdout.getvalue()),
            {
                "alias_added": True,
                "raw_merchant": "CP AXTRA PUBLIC COMPANY LIMITED (HEAD",
                "alias": "Lotus's",
            },
        )

    def test_add_category_command(self) -> None:
        argv = [
            "main.py",
            "--add-category",
            "Lotus's",
            "food",
        ]

        with (
            patch.object(sys, "argv", argv),
            patch("main.add_category") as add_category,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        add_category.assert_called_once_with("Lotus's", "food")
        self.assertEqual(
            json.loads(stdout.getvalue()),
            {
                "category_added": True,
                "merchant": "Lotus's",
                "category": "food",
            },
        )


if __name__ == "__main__":
    unittest.main()
