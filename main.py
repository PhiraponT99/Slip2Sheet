from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from expense_tracker.maintenance import backfill_transaction_keys, dedupe_transactions
from expense_tracker.merchant_categories import add_category
from expense_tracker.merchant_aliases import add_alias
from expense_tracker.ocr import OcrError, run_ocr
from expense_tracker.parser import extract_transaction
from expense_tracker.reports import month_report, today_report
from expense_tracker.sheets import SheetsError, append_transaction_to_sheet
from expense_tracker.summary import update_summary_sheet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract basic transaction fields from one payment slip image."
    )
    parser.add_argument(
        "--image",
        help="Path to a local payment slip image, for example ./samples/slip.jpg",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Append the parsed transaction to Google Sheets.",
    )
    parser.add_argument(
        "--today",
        action="store_true",
        help="Print today's spending report from Google Sheets.",
    )
    parser.add_argument(
        "--month",
        help="Print a monthly spending report from Google Sheets, for example 2026-06.",
    )
    parser.add_argument(
        "--backfill-keys",
        action="store_true",
        help="Backfill missing TransactionKey values in monthly Google Sheet tabs.",
    )
    parser.add_argument(
        "--dedupe",
        action="store_true",
        help="Mark duplicate monthly rows and refresh Summary.",
    )
    parser.add_argument(
        "--add-alias",
        nargs=2,
        metavar=("RAW_MERCHANT", "ALIAS"),
        help="Store a merchant alias, for example: --add-alias RAW ALIAS.",
    )
    parser.add_argument(
        "--add-category",
        nargs=2,
        metavar=("MERCHANT_NAME", "CATEGORY"),
        help="Store a merchant category mapping, for example: --add-category MERCHANT food.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command_count = sum(
        1
        for selected in (
            bool(args.image),
            args.today,
            bool(args.month),
            args.backfill_keys,
            args.dedupe,
            bool(args.add_alias),
            bool(args.add_category),
        )
        if selected
    )

    if command_count != 1:
        print(
            "Use exactly one command: --image, --today, --month, --backfill-keys, --dedupe, --add-alias, or --add-category.",
            file=sys.stderr,
        )
        return 2
    if args.save and not args.image:
        print("--save requires --image.", file=sys.stderr)
        return 2

    if args.today:
        try:
            return _print_output(today_report())
        except SheetsError as exc:
            print(f"Report failed: {exc}", file=sys.stderr)
            return 1

    if args.month:
        try:
            return _print_output(month_report(args.month))
        except SheetsError as exc:
            print(f"Report failed: {exc}", file=sys.stderr)
            return 1

    if args.backfill_keys:
        try:
            return _print_output(backfill_transaction_keys())
        except SheetsError as exc:
            print(f"Backfill failed: {exc}", file=sys.stderr)
            return 1

    if args.dedupe:
        try:
            return _print_output(dedupe_transactions())
        except SheetsError as exc:
            print(f"Dedupe failed: {exc}", file=sys.stderr)
            return 1

    if args.add_alias:
        raw_name, alias = args.add_alias
        try:
            add_alias(raw_name, alias)
        except ValueError as exc:
            print(f"Add alias failed: {exc}", file=sys.stderr)
            return 2
        return _print_output(
            {
                "alias_added": True,
                "raw_merchant": raw_name,
                "alias": alias,
            }
        )

    if args.add_category:
        merchant, category = args.add_category
        try:
            add_category(merchant, category)
        except ValueError as exc:
            print(f"Add category failed: {exc}", file=sys.stderr)
            return 2
        return _print_output(
            {
                "category_added": True,
                "merchant": merchant,
                "category": category.strip().lower(),
            }
        )

    image_path = Path(args.image)

    if not image_path.exists():
        print(f"Image file not found: {image_path}", file=sys.stderr)
        return 2

    raw_text = None
    try:
        raw_text = run_ocr(image_path)
    except OcrError as exc:
        print(f"OCR failed: {exc}", file=sys.stderr)
        result = extract_transaction(None)
    else:
        result = extract_transaction(raw_text)

    output = result.to_dict()
    exit_code = 0

    if args.save:
        if raw_text is None:
            output["saved"] = False
            output["error"] = "OCR failed; transaction was not saved."
            exit_code = 1
        else:
            try:
                saved_result = append_transaction_to_sheet(result, image_path)
                output["saved"] = saved_result["saved"]
                output["duplicate"] = saved_result["duplicate"]
                output["sheet_tab"] = saved_result["sheet_tab"]
                if "message" in saved_result:
                    output["message"] = saved_result["message"]
            except SheetsError as exc:
                output["saved"] = False
                output["duplicate"] = False
                output["error"] = str(exc)
                exit_code = 1
            else:
                if saved_result["duplicate"]:
                    return _print_output(output)

                try:
                    update_summary_sheet()
                except SheetsError as exc:
                    output["summary_updated"] = False
                    output["summary_error"] = str(exc)
                    exit_code = 1
                else:
                    output["summary_updated"] = True

    _print_output(output)
    return exit_code


def _print_output(output: dict) -> int:
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
