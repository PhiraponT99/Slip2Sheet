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

    def test_month_export_command(self) -> None:
        argv = ["main.py", "--month", "2026-06", "--export", "csv"]
        report = {
            "month": "2026-06",
            "transactions": [{"amount": 65.0}],
        }
        export_result = {
            "month": "2026-06",
            "export_format": "csv",
            "export_file": "exports/2026-06.csv",
            "transaction_count": 1,
        }

        with (
            patch.object(sys, "argv", argv),
            patch("main.month_report", return_value=report) as month_report,
            patch("main.export_month_report", return_value=export_result) as export_month_report,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        month_report.assert_called_once_with("2026-06")
        export_month_report.assert_called_once_with(report, "csv")
        self.assertEqual(json.loads(stdout.getvalue()), export_result)

    def test_precommit_check_command(self) -> None:
        argv = ["main.py", "--precommit-check"]
        check_output = {
            "status": "PASS",
            "checks": {
                "tests": "PASS",
                "env_not_tracked": "PASS",
            },
        }

        with (
            patch.object(sys, "argv", argv),
            patch("main.run_precommit_check", return_value=(check_output, 0)) as run_precommit_check,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        run_precommit_check.assert_called_once_with()
        self.assertEqual(json.loads(stdout.getvalue()), check_output)

    def test_dashboard_command(self) -> None:
        argv = ["main.py", "--dashboard"]
        payload = {"today": {}, "month": {}, "insights": {}}

        with (
            patch.object(sys, "argv", argv),
            patch("main.dashboard_payload", return_value=payload) as dashboard_payload,
            patch("main.render_dashboard", return_value="dashboard text") as render_dashboard,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        dashboard_payload.assert_called_once_with()
        render_dashboard.assert_called_once_with(payload)
        self.assertEqual(stdout.getvalue().strip(), "dashboard text")

    def test_dashboard_json_command(self) -> None:
        argv = ["main.py", "--dashboard", "--json"]
        payload = {
            "today": {"total_expense": 50.0},
            "month": {"total_expense": 50.0},
            "insights": {"transaction_count": 1},
        }

        with (
            patch.object(sys, "argv", argv),
            patch("main.dashboard_payload", return_value=payload),
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), payload)

    def test_trend_command(self) -> None:
        argv = ["main.py", "--trend"]
        trend_output = {
            "months": [{"month": "2026-06", "total_expense": 50.0}],
            "trend": {
                "direction": "STABLE",
                "change_percent": 0.0,
                "message": "Not enough monthly data to calculate a trend.",
            },
        }

        with (
            patch.object(sys, "argv", argv),
            patch("main.trend_report", return_value=trend_output) as trend_report,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        trend_report.assert_called_once_with()
        self.assertEqual(json.loads(stdout.getvalue()), trend_output)

    def test_goals_command(self) -> None:
        argv = ["main.py", "--goals"]
        output = {"goals": [{"name": "Emergency Fund", "progress_percent": 20.0}]}

        with (
            patch.object(sys, "argv", argv),
            patch("main.goals_report", return_value=output) as goals_report,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        goals_report.assert_called_once_with()
        self.assertEqual(json.loads(stdout.getvalue()), output)

    def test_goal_add_command(self) -> None:
        argv = ["main.py", "--goal-add", "Emergency Fund", "50000", "10000"]
        goal = {
            "name": "Emergency Fund",
            "target_amount": 50000,
            "current_amount": 10000,
            "progress_percent": 20.0,
        }

        with (
            patch.object(sys, "argv", argv),
            patch("main.add_goal", return_value=goal) as add_goal,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        add_goal.assert_called_once_with("Emergency Fund", 50000.0, 10000.0)
        self.assertEqual(json.loads(stdout.getvalue()), {
            "goal_added": True,
            "goal": goal,
        })

    def test_goal_update_command(self) -> None:
        argv = ["main.py", "--goal-update", "Emergency Fund", "12000"]
        goal = {
            "name": "Emergency Fund",
            "target_amount": 50000,
            "current_amount": 12000,
            "progress_percent": 24.0,
        }

        with (
            patch.object(sys, "argv", argv),
            patch("main.update_goal", return_value=goal) as update_goal,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        update_goal.assert_called_once_with("Emergency Fund", 12000.0)
        self.assertEqual(json.loads(stdout.getvalue()), {
            "goal_updated": True,
            "goal": goal,
        })

    def test_reflection_command(self) -> None:
        argv = ["main.py", "--reflection"]
        output = {
            "date": "2026-06-03",
            "total_expense": 50.0,
            "transaction_count": 1,
            "reflection": {
                "top_category": "food",
                "top_merchant": "Lotus's",
                "budget_status": "OK",
                "message": "You stayed within your daily budget today.",
            },
        }

        with (
            patch.object(sys, "argv", argv),
            patch("main.reflection_report", return_value=output) as reflection_report,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        reflection_report.assert_called_once_with()
        self.assertEqual(json.loads(stdout.getvalue()), output)

    def test_reflection_history_command(self) -> None:
        argv = ["main.py", "--reflection-history"]
        output = {
            "month": "2026-06",
            "days_in_month": 30,
            "records": [],
            "summary": {
                "ok_days": 0,
                "over_budget_days": 0,
                "no_spending_days": 0,
                "total_days_with_transactions": 0,
            },
        }

        with (
            patch.object(sys, "argv", argv),
            patch("main.reflection_history_report", return_value=output) as reflection_history_report,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        reflection_history_report.assert_called_once_with()
        self.assertEqual(json.loads(stdout.getvalue()), output)

    def test_weekly_reflection_command(self) -> None:
        argv = ["main.py", "--weekly-reflection"]
        output = {
            "week_start": "2026-06-01",
            "week_end": "2026-06-07",
            "total_expense": 250.0,
            "transaction_count": 5,
            "top_category": "food",
            "top_merchant": "Lotus's",
            "total_days_with_transactions": 5,
            "spending_day_ratio": 0.71,
            "summary": {
                "ok_days": 4,
                "over_budget_days": 1,
                "no_spending_days": 2,
            },
            "message": "You stayed within budget for most spending days this week.",
        }

        with (
            patch.object(sys, "argv", argv),
            patch("main.weekly_reflection_report", return_value=output) as weekly_reflection_report,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        weekly_reflection_report.assert_called_once_with()
        self.assertEqual(json.loads(stdout.getvalue()), output)

    def test_monthly_reflection_command(self) -> None:
        argv = ["main.py", "--monthly-reflection"]
        output = {
            "month": "2026-06",
            "days_in_month": 30,
            "total_expense": 1250.0,
            "transaction_count": 18,
            "top_category": "food",
            "top_merchant": "Lotus's",
            "total_days_with_transactions": 12,
            "spending_day_ratio": 0.4,
            "summary": {
                "ok_days": 10,
                "over_budget_days": 2,
                "no_spending_days": 18,
            },
            "message": "You stayed within budget on most spending days this month.",
        }

        with (
            patch.object(sys, "argv", argv),
            patch("main.monthly_reflection_report", return_value=output) as monthly_reflection_report,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        monthly_reflection_report.assert_called_once_with()
        self.assertEqual(json.loads(stdout.getvalue()), output)

    def test_reflection_report_command(self) -> None:
        argv = ["main.py", "--reflection-report"]
        output = {
            "date": "2026-06-04",
            "daily": {"message": "You stayed within your daily budget today."},
            "weekly": {"message": "You stayed within budget on all spending days this week."},
            "monthly": {"message": "You stayed within budget on most spending days this month."},
            "overall_message": "Your spending is currently under control.",
        }

        with (
            patch.object(sys, "argv", argv),
            patch("main.combined_reflection_report", return_value=output) as combined_reflection_report,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        combined_reflection_report.assert_called_once_with()
        self.assertEqual(json.loads(stdout.getvalue()), output)

    def test_reflection_report_markdown_command(self) -> None:
        argv = ["main.py", "--reflection-report-md"]
        report = {
            "date": "2026-06-04",
            "daily": {},
            "weekly": {},
            "monthly": {},
            "overall_message": "Your spending is currently under control.",
        }

        with (
            patch.object(sys, "argv", argv),
            patch("main.combined_reflection_report", return_value=report) as combined_reflection_report,
            patch("main.render_reflection_report_markdown", return_value="# Report") as render_markdown,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            exit_code = main.main()

        self.assertEqual(exit_code, 0)
        combined_reflection_report.assert_called_once_with()
        render_markdown.assert_called_once_with(report)
        self.assertEqual(stdout.getvalue().strip(), "# Report")


if __name__ == "__main__":
    unittest.main()
