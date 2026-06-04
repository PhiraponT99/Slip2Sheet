from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from expense_tracker.reflection_export import export_reflection_report
from tests.test_reflection_markdown import REPORT


MARKDOWN = """# Slip2Sheet Reflection Report

Date: 2026-06-04

## Daily Reflection

## Weekly Reflection

## Monthly Reflection

## Overall
"""


class ReflectionExportTest(unittest.TestCase):
    def test_exports_markdown_file_successfully(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = export_reflection_report(
                report_fn=lambda: REPORT,
                render_fn=lambda report: MARKDOWN,
                output_dir=Path(tmpdir) / "reports",
            )
            file_path = Path(tmpdir) / "reports" / "reflection-2026-06-04.md"

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["file_path"], str(file_path).replace("\\", "/"))
            self.assertTrue(file_path.exists())
            self.assertEqual(file_path.read_text(encoding="utf-8"), MARKDOWN)

    def test_creates_reports_directory_if_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "missing" / "reports"

            export_reflection_report(
                report_fn=lambda: REPORT,
                render_fn=lambda report: MARKDOWN,
                output_dir=output_dir,
            )

            self.assertTrue(output_dir.exists())

    def test_overwrites_existing_report_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "reports"
            output_dir.mkdir()
            file_path = output_dir / "reflection-2026-06-04.md"
            file_path.write_text("old content", encoding="utf-8")

            export_reflection_report(
                report_fn=lambda: REPORT,
                render_fn=lambda report: MARKDOWN,
                output_dir=output_dir,
            )

            self.assertEqual(file_path.read_text(encoding="utf-8"), MARKDOWN)

    def test_exported_file_contains_required_markdown_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = export_reflection_report(
                report_fn=lambda: REPORT,
                output_dir=Path(tmpdir) / "reports",
            )
            markdown = Path(result["file_path"]).read_text(encoding="utf-8")

            for section in (
                "Slip2Sheet Reflection Report",
                "Daily Reflection",
                "Weekly Reflection",
                "Monthly Reflection",
                "Overall",
            ):
                self.assertIn(section, markdown)


if __name__ == "__main__":
    unittest.main()
