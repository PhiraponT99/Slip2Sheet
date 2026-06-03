from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from expense_tracker.safety import (
    REQUIRED_GITIGNORE_ENTRIES,
    check_credentials_not_tracked,
    check_env_not_tracked,
    check_gitignore_required_entries,
    check_runtime_folders_not_tracked,
    check_sample_images_documented,
    run_precommit_check,
)


class SafetyTest(unittest.TestCase):
    def test_gitignore_required_entries_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".gitignore").write_text(
                "\n".join(REQUIRED_GITIGNORE_ENTRIES),
                encoding="utf-8",
            )

            result = check_gitignore_required_entries(root)

        self.assertEqual(result["status"], "PASS")

    def test_gitignore_required_entries_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".gitignore").write_text(".env\n", encoding="utf-8")

            result = check_gitignore_required_entries(root)

        self.assertEqual(result["status"], "FAIL")
        self.assertIn("credentials/", result["reason"])

    def test_env_not_tracked_fails_when_env_is_tracked(self) -> None:
        with patch("expense_tracker.safety.tracked_paths", return_value=[".env"]):
            result = check_env_not_tracked(Path("."))

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["paths"], [".env"])

    def test_credentials_not_tracked_fails_for_credentials_folder(self) -> None:
        with patch(
            "expense_tracker.safety.tracked_paths",
            return_value=["credentials/google-service-account.json"],
        ):
            result = check_credentials_not_tracked(Path("."))

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["paths"], ["credentials/google-service-account.json"])

    def test_runtime_folders_not_tracked_fails_for_exports(self) -> None:
        with patch(
            "expense_tracker.safety.tracked_paths",
            return_value=["exports/2026-06.csv"],
        ):
            result = check_runtime_folders_not_tracked(Path("."))

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["paths"], ["exports/2026-06.csv"])

    def test_sample_images_documented_passes_when_readme_declares_sample_test_slips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "README.md").write_text(
                "Images in samples/ are sample/test slips only.",
                encoding="utf-8",
            )
            with patch(
                "expense_tracker.safety.tracked_paths",
                return_value=["samples/slip.jpg"],
            ):
                result = check_sample_images_documented(root)

        self.assertEqual(result["status"], "PASS")

    def test_precommit_check_aggregates_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".gitignore").write_text(".env\n", encoding="utf-8")
            with (
                patch("expense_tracker.safety.check_unit_tests", return_value={"status": "PASS"}),
                patch("expense_tracker.safety.tracked_paths", return_value=[".env"]),
            ):
                output, exit_code = run_precommit_check(root)

        self.assertEqual(exit_code, 1)
        self.assertEqual(output["status"], "FAIL")
        self.assertEqual(output["checks"]["tests"], "PASS")
        self.assertEqual(output["checks"]["env_not_tracked"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
