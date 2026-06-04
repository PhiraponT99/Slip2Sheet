from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from expense_tracker.reflection_markdown import render_reflection_report_markdown
from expense_tracker.reflection_report import reflection_report


def export_reflection_report(
    report_fn: Callable[[], dict[str, Any]] = reflection_report,
    render_fn: Callable[[dict[str, Any]], str] = render_reflection_report_markdown,
    output_dir: Path | str = "reports",
) -> dict[str, str]:
    report = report_fn()
    markdown = render_fn(report)
    report_date = str(report.get("date") or "unknown-date")

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / f"reflection-{report_date}.md"
    file_path.write_text(markdown, encoding="utf-8")

    return {
        "status": "success",
        "file_path": str(file_path).replace("\\", "/"),
    }
