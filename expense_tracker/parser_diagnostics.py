from __future__ import annotations

import json
from typing import Any

from expense_tracker import parser
from expense_tracker.parser import extract_transaction


def analyze_parser_accuracy(
    raw_text: str | None,
    expected_amount: float | None = None,
) -> dict[str, Any]:
    transaction = extract_transaction(raw_text)
    normalized = (raw_text or "").translate(parser.THAI_DIGITS)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    amount_details = parser._extract_amount_details(lines)
    fallback_candidates = _fallback_amount_candidates(lines)
    ocr_amount_candidates = _all_amount_candidates(lines, fallback_candidates)
    selected_candidate = _selected_candidate(transaction.amount, fallback_candidates)

    root_cause = _root_cause(
        expected_amount=expected_amount,
        selected_amount=transaction.amount,
        amount_details=amount_details,
        fallback_candidates=fallback_candidates,
        ocr_amount_candidates=ocr_amount_candidates,
    )

    return {
        "ocr_amount_candidates": ocr_amount_candidates,
        "selected_amount": transaction.amount,
        "selected_line": selected_candidate["line"] if selected_candidate else None,
        "selected_score": selected_candidate["score"] if selected_candidate else None,
        "root_cause": root_cause,
        "recommended_fix": _recommended_fix(root_cause),
    }


def log_parser_investigation(
    raw_text: str | None,
    expected_amount: float | None = None,
) -> dict[str, Any]:
    report = analyze_parser_accuracy(raw_text, expected_amount=expected_amount)
    print("[DEBUG] OCR text:")
    print(raw_text or "")
    print("[DEBUG] Parser investigation report:")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def _fallback_amount_candidates(lines: list[str]) -> list[dict[str, Any]]:
    candidates = []
    for line_number, line in enumerate(lines, start=1):
        for match in parser._number_matches(line, allow_negative=False):
            raw_value = match.group(0)
            value = parser._parse_number(raw_value)
            if value is None:
                continue

            score = parser._score_amount_candidate(line, raw_value, value)

            candidates.append(
                {
                    "line_number": line_number,
                    "line": line,
                    "raw_value": raw_value,
                    "value": round(value, 2),
                    "score": score,
                    "usable": score > 0,
                    "reasons": _score_reasons(line, raw_value, value),
                }
            )
    return candidates


def _score_reasons(line: str, raw_value: str, value: float) -> list[str]:
    lower = line.lower()
    reasons = []
    if any(keyword in lower for keyword in parser.AMOUNT_KEYWORDS):
        reasons.append("amount_keyword:+3")
    else:
        reasons.append("no_amount_keyword:+1")
    if parser._has_strong_amount_keyword(line):
        reasons.append("strong_amount_keyword:+10")
    if parser._looks_like_reference_line(line):
        reasons.append("reference_line:-5")
    if parser._looks_like_account_line(line):
        reasons.append("account_like_line:-5")
    if parser._looks_like_decimal_amount(raw_value):
        reasons.append("decimal_amount:+3")
    if value <= 0:
        reasons.append("non_positive:-2")
    if parser._looks_like_date_or_time_number(line, raw_value):
        reasons.append("date_or_time_like:-2")
    return reasons


def _selected_candidate(
    selected_amount: float | None,
    fallback_candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if selected_amount is None:
        return None

    usable = [candidate for candidate in fallback_candidates if candidate["usable"]]
    usable.sort(key=lambda candidate: (candidate["score"], candidate["value"]), reverse=True)
    for candidate in usable:
        if round(candidate["value"], 2) == round(selected_amount, 2):
            return candidate
    return None


def _all_amount_candidates(
    lines: list[str],
    fallback_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = list(fallback_candidates)
    amount_details = parser._extract_amount_details(lines)
    for source_key, label in (
        ("paid_amount", "paid_amount_priority"),
        ("original_amount", "original_amount"),
        ("discount", "discount"),
    ):
        value = amount_details.get(source_key)
        if value is not None:
            candidates.append(
                {
                    "line_number": None,
                    "line": None,
                    "raw_value": str(value),
                    "value": value,
                    "score": None,
                    "usable": True,
                    "reasons": [label],
                }
            )
    return candidates


def _root_cause(
    expected_amount: float | None,
    selected_amount: float | None,
    amount_details: dict[str, float | None],
    fallback_candidates: list[dict[str, Any]],
    ocr_amount_candidates: list[dict[str, Any]],
) -> str:
    if selected_amount is None:
        return "amount_extraction_failed"

    if expected_amount is None:
        return "needs_expected_amount_or_slip_review"

    expected = round(expected_amount, 2)
    selected = round(selected_amount, 2)
    values = {round(candidate["value"], 2) for candidate in ocr_amount_candidates}

    if expected not in values:
        return "ocr_likely_missed_or_misread_expected_amount"
    if selected == expected:
        return "parser_selected_expected_amount"

    paid_amount = amount_details.get("paid_amount")
    if paid_amount is not None and round(paid_amount, 2) == selected:
        return "paid_amount_priority_selected_wrong_candidate"

    usable = [candidate for candidate in fallback_candidates if candidate["usable"]]
    if usable:
        usable.sort(key=lambda candidate: (candidate["score"], candidate["value"]), reverse=True)
        top = usable[0]
        if round(top["value"], 2) == selected:
            return "amount_ranking_selected_highest_scored_candidate"

    return "parser_selected_wrong_candidate"


def _recommended_fix(root_cause: str) -> str:
    recommendations = {
        "amount_extraction_failed": "Improve amount label detection or OCR preprocessing so amount candidates are extracted.",
        "needs_expected_amount_or_slip_review": "Compare the OCR text with the slip image; provide the expected amount to classify OCR versus ranking errors.",
        "ocr_likely_missed_or_misread_expected_amount": "Improve OCR image preprocessing or inspect whether Tesseract read 58.00 as another value.",
        "parser_selected_expected_amount": "No parser fix needed for amount selection in this sample.",
        "paid_amount_priority_selected_wrong_candidate": "Tighten paid amount label matching so unrelated numeric lines are not treated as actual paid amount.",
        "amount_ranking_selected_highest_scored_candidate": "Adjust amount ranking to prefer explicit paid/total labels and ignore unrelated amount-like candidates such as references, balances, or item totals.",
        "parser_selected_wrong_candidate": "Add slip-specific parser tests and refine candidate filtering around the selected line.",
    }
    return recommendations.get(root_cause, "Add a regression test for this OCR text before changing parser logic.")
