from __future__ import annotations

import re
from datetime import date

from expense_tracker.merchant_aliases import normalize_merchant
from expense_tracker.models import TransactionResult


THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

THAI_MONTHS = {
    "ม.ค.": 1,
    "มกราคม": 1,
    "ก.พ.": 2,
    "กุมภาพันธ์": 2,
    "มี.ค.": 3,
    "มีนาคม": 3,
    "เม.ย.": 4,
    "เมษายน": 4,
    "พ.ค.": 5,
    "พฤษภาคม": 5,
    "มิ.ย.": 6,
    "มิถุนายน": 6,
    "ก.ค.": 7,
    "กรกฎาคม": 7,
    "ส.ค.": 8,
    "สิงหาคม": 8,
    "ก.ย.": 9,
    "กันยายน": 9,
    "ต.ค.": 10,
    "ตุลาคม": 10,
    "พ.ย.": 11,
    "พฤศจิกายน": 11,
    "ธ.ค.": 12,
    "ธันวาคม": 12,
}

MERCHANT_KEYWORDS = (
    "merchant",
    "receiver",
    "recipient",
    "payee",
    "biller",
    "to ",
    "to:",
    "ร้าน",
    "ผู้รับ",
    "ผู้รับเงิน",
    "ปลายทาง",
    "ชื่อบัญชี",
)

AMOUNT_KEYWORDS = (
    "amount",
    "total",
    "paid",
    "payment",
    "thb",
    "baht",
    "จำนวนเงิน",
    "ยอดเงิน",
    "ยอดชำระ",
    "บาท",
)

MERCHANT_LABEL_KEYWORDS = (
    "to",
    "payee",
    "merchant",
    "biller",
    "\u0e44\u0e1b\u0e22\u0e31\u0e07",
)

NOISE_MERCHANT_KEYWORDS = (
    "date",
    "time",
    "amount",
    "total",
    "reference",
    "transaction",
    "วันที่",
    "เวลา",
    "จำนวนเงิน",
    "ยอดเงิน",
    "อ้างอิง",
    "เลขที่",
    "ตรวจสอบสถานะการจ่ายเงิน",
    "ผู้รับเงินสามารถสแกน",
    "เลขที่อ้างอิง",
    "รหัสอ้างอิง",
    "biller id",
    "หมายเลขร้านค้า",
    "บันทึกช่วยจำ",
    "จาก",
    "ไปยัง",
)

REFERENCE_KEYWORDS = (
    "reference",
    "transaction id",
    "transaction no",
    "ref",
    "biller",
    "merchant id",
    "\u0e23\u0e2b\u0e31\u0e2a\u0e2d\u0e49\u0e32\u0e07\u0e2d\u0e34\u0e07",
    "\u0e40\u0e25\u0e02\u0e17\u0e35\u0e48\u0e2d\u0e49\u0e32\u0e07\u0e2d\u0e34\u0e07",
    "อ้างอิง",
    "เลขที่",
    "รายการ",
)

STRONG_AMOUNT_KEYWORDS = (
    "amount",
    "total",
    "\u0e08\u0e33\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19",
    "\u0e08\u0e4d\u0e32\u0e19\u0e27\u0e19\u0e40\u0e07\u0e34\u0e19",
    "\u0e22\u0e2d\u0e14\u0e40\u0e07\u0e34\u0e19",
)

PAID_AMOUNT_KEYWORDS = (
    "paidamount",
    "amountpaid",
    "paymentamount",
    "totalpaid",
    "paid",
    "จำนวนเงินที่ชำระ",
    "จํานวนเงินที่ชําระ",
    "ยอดชำระ",
    "ยอดชําระ",
    "ยอดที่ชำระ",
    "ยอดที่ชําระ",
)

ORIGINAL_AMOUNT_KEYWORDS = (
    "ค่าสินค้า/บริการ",
    "ค่าสินค้าบริการ",
    "ค่าสินค้า",
    "ค่าบริการ",
    "ราคาสินค้า",
    "originalamount",
    "subtotal",
)

DISCOUNT_KEYWORDS = (
    "discount",
    "ส่วนลด",
    "สิทธิ",
    "ช่วยไทย",
    "พลัส",
    "โปรโมชัน",
    "โปรโมชั่น",
)

MERCHANT_CATEGORY_KEYWORDS = (
    "อาหาร",
    "ของหวาน",
    "เครื่องดื่ม",
    "เครื่องดืม",
    "กาแฟ",
    "เบเกอรี่",
)

BANK_OR_HEADER_KEYWORDS = (
    "ธนาคาร",
    "พร้อมเพย์",
    "promptpay",
    "scb",
    "kbank",
    "kasikorn",
    "krungthai",
    "กรุงไทย",
    "กสิกร",
    "ไทยพาณิชย์",
    "กรุงเทพ",
    "รายการสำเร็จ",
    "ทำรายการสำเร็จ",
    "ชำระเงินสำเร็จ",
    "ชําระเงินสําเร็จ",
    "โอนเงินสำเร็จ",
    "โอนเงินสําเร็จ",
    "ใบเสร็จ",
    "receipt",
    "สิทธิ",
    "ช่วยไทย",
    "พลัส",
    "ตรวจสอบสถานะการจ่ายเงิน",
    "ผู้รับเงินสามารถสแกน",
    "เลขที่อ้างอิง",
    "รหัสอ้างอิง",
    "biller id",
    "หมายเลขร้านค้า",
    "บันทึกช่วยจำ",
)

SUCCESS_HEADER_KEYWORDS = (
    "\u0e08\u0e48\u0e32\u0e22\u0e1a\u0e34\u0e25\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08",
    "\u0e08\u0e48\u0e32\u0e22\u0e1a\u0e34\u0e25\u0e2a\u0e4d\u0e32\u0e40\u0e23\u0e47\u0e08",
    "\u0e42\u0e2d\u0e19\u0e40\u0e07\u0e34\u0e19\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08",
    "\u0e42\u0e2d\u0e19\u0e40\u0e07\u0e34\u0e19\u0e2a\u0e4d\u0e32\u0e40\u0e23\u0e47\u0e08",
    "payment successful",
    "success",
)

SCB_TRANSFER_KEYWORDS = (
    "โอนเงินสำเร็จ",
    "จาก",
    "ไปยัง",
    "จำนวนเงิน",
)

SCB_STOP_KEYWORDS = (
    "biller id",
    "หมายเลขร้านค้า",
    "เลขที่อ้างอิง",
    "จำนวนเงิน",
    "บันทึกช่วยจำ",
)


def extract_transaction(raw_text: str | None) -> TransactionResult:
    if not raw_text:
        return TransactionResult(
            date=None,
            time=None,
            merchant=None,
            amount=None,
            raw_text=raw_text,
        )

    normalized = raw_text.translate(THAI_DIGITS)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    amount_details = _extract_amount_details(lines)
    amount = amount_details["paid_amount"]
    if amount is None:
        amount = _extract_amount(lines)

    return TransactionResult(
        date=_extract_date(normalized),
        time=_extract_time(normalized),
        merchant=normalize_merchant(_extract_merchant(lines)),
        amount=amount,
        raw_text=raw_text,
        original_amount=amount_details["original_amount"],
        discount=amount_details["discount"],
    )


def _extract_date(text: str) -> str | None:
    iso_match = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", text)
    if iso_match:
        return _format_date(
            int(iso_match.group(1)),
            int(iso_match.group(2)),
            int(iso_match.group(3)),
        )

    dmy_match = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b", text)
    if dmy_match:
        return _format_date(
            _normalize_year(int(dmy_match.group(3))),
            int(dmy_match.group(2)),
            int(dmy_match.group(1)),
        )

    month_names = "|".join(re.escape(month) for month in THAI_MONTHS)
    thai_match = re.search(
        rf"\b(\d{{1,2}})\s*({month_names})\s*(\d{{2,4}})\b",
        text,
        re.IGNORECASE,
    )
    if thai_match:
        return _format_date(
            _normalize_year(int(thai_match.group(3))),
            THAI_MONTHS[thai_match.group(2)],
            int(thai_match.group(1)),
        )

    return None


def _extract_time(text: str) -> str | None:
    match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?\b", text)
    if not match:
        return None
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def _extract_merchant(lines: list[str]) -> str | None:
    labeled_merchant = _extract_labeled_merchant(lines)
    if labeled_merchant:
        return labeled_merchant

    scb_merchant = _extract_scb_transfer_merchant(lines)
    if scb_merchant:
        return scb_merchant

    for index, line in enumerate(lines):
        if not _looks_like_category_line(line):
            continue
        for previous_line in reversed(lines[:index]):
            if _looks_like_merchant(previous_line):
                return previous_line.strip()

    for index, line in enumerate(lines):
        lower = line.lower()
        if not any(keyword in lower for keyword in MERCHANT_KEYWORDS):
            continue

        inline_value = _value_after_label(line)
        if _looks_like_merchant(inline_value):
            return _clean_merchant_text(inline_value)

        if index + 1 < len(lines) and _looks_like_merchant(lines[index + 1]):
            return _clean_merchant_text(lines[index + 1])

    for line in lines:
        if _looks_like_merchant(line) and any(ch >= "\u0e00" and ch <= "\u0e7f" for ch in line):
            return line.strip()

    return None


def _extract_labeled_merchant(lines: list[str]) -> str | None:
    for index, line in enumerate(lines):
        label = _merchant_label_in_line(line)
        if not label:
            continue

        merchant_parts = []
        inline_value = _value_after_merchant_label(line, label)
        if inline_value:
            merchant_parts.append(inline_value)

        for candidate in lines[index + 1 :]:
            if _is_merchant_stop_line(candidate):
                break
            if _looks_like_merchant(candidate):
                merchant_parts.append(candidate)
                continue
            if merchant_parts:
                break

        merchant = _clean_joined_text(merchant_parts)
        if _looks_like_merchant(merchant):
            return merchant

    return None


def _extract_scb_transfer_merchant(lines: list[str]) -> str | None:
    if not _looks_like_scb_transfer(lines):
        return None

    for index, line in enumerate(lines):
        if not _has_keyword(_match_text(line), ("ไปยัง",)):
            continue

        merchant_parts = []
        inline_value = _value_after_scb_label(line, "ไปยัง")
        if inline_value:
            merchant_parts.append(inline_value)

        for candidate in lines[index + 1 :]:
            if _is_scb_stop_line(candidate):
                break
            if _looks_like_merchant(candidate):
                merchant_parts.append(candidate.strip())

        merchant = _clean_joined_text(merchant_parts)
        if _looks_like_merchant(merchant):
            return merchant

    return None


def _merchant_label_in_line(line: str) -> str | None:
    match_text = _match_text(line)
    for label in MERCHANT_LABEL_KEYWORDS:
        if _match_text(label) in match_text:
            return label
    return None


def _value_after_merchant_label(line: str, label: str) -> str | None:
    if label == "\u0e44\u0e1b\u0e22\u0e31\u0e07":
        return _value_after_scb_label(line, label)

    match = re.search(
        rf"\b{re.escape(label)}\b\s*[|:：]?\s*(.+?)\s*$",
        line,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    parts = re.split(r"[|:：]\s*", line, maxsplit=1)
    if len(parts) == 2:
        return parts[1].strip()
    return None


def _is_merchant_stop_line(line: str) -> bool:
    return (
        _is_scb_stop_line(line)
        or _looks_like_account_line(line)
        or _has_keyword(_match_text(line), AMOUNT_KEYWORDS + REFERENCE_KEYWORDS)
        or _looks_like_date_or_time_number(line, line.strip())
    )


def _looks_like_scb_transfer(lines: list[str]) -> bool:
    match_text = _match_text("\n".join(lines))
    return all(_has_keyword(match_text, (keyword,)) for keyword in SCB_TRANSFER_KEYWORDS)


def _value_after_scb_label(line: str, label: str) -> str | None:
    pattern = rf"^\s*{re.escape(label)}\s*[:：]?\s*(.+?)\s*$"
    match = re.search(pattern, line, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _is_scb_stop_line(line: str) -> bool:
    return _has_keyword(_match_text(line), SCB_STOP_KEYWORDS)


def _clean_joined_text(parts: list[str]) -> str | None:
    cleaned = " ".join(
        _clean_merchant_text(part) for part in parts if part and part.strip()
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _clean_merchant_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"^[\s@|:：-]+", "", value.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _extract_amount_details(lines: list[str]) -> dict[str, float | None]:
    paid_amount = _extract_scb_transfer_amount(lines)
    original_amount = None
    discount = None

    for line in lines:
        signed_amounts = _numbers_in_line(line, allow_negative=True)
        if not signed_amounts:
            continue

        match_text = _match_text(line)
        first_amount = abs(signed_amounts[0])

        if paid_amount is None and _has_keyword(match_text, PAID_AMOUNT_KEYWORDS):
            paid_amount = first_amount
            continue

        if original_amount is None and _has_keyword(match_text, ORIGINAL_AMOUNT_KEYWORDS):
            original_amount = first_amount
            continue

        if discount is None:
            has_discount_keyword = _has_keyword(match_text, DISCOUNT_KEYWORDS)
            negative_amounts = [abs(amount) for amount in signed_amounts if amount < 0]
            if negative_amounts and has_discount_keyword:
                discount = negative_amounts[0]
            elif negative_amounts:
                discount = negative_amounts[0]

    return {
        "paid_amount": _round_amount(paid_amount),
        "original_amount": _round_amount(original_amount),
        "discount": _round_amount(discount),
    }


def _extract_scb_transfer_amount(lines: list[str]) -> float | None:
    if not _looks_like_scb_transfer(lines):
        return None

    for index, line in enumerate(lines):
        if not _has_keyword(_match_text(line), ("จำนวนเงิน",)):
            continue

        for candidate in lines[index : index + 4]:
            numbers = _numbers_in_line(candidate, allow_negative=False)
            if numbers:
                return abs(numbers[0])

        break

    return None


def _extract_amount(lines: list[str]) -> float | None:
    candidates: list[tuple[int, float]] = []

    for line in lines:
        for match in _number_matches(line, allow_negative=False):
            value = _parse_number(match.group(0))
            if value is None:
                continue

            score = _score_amount_candidate(line, match.group(0), value)
            candidates.append((score, value))

    usable = [candidate for candidate in candidates if candidate[0] > 0]
    if not usable:
        return None

    usable.sort(key=lambda candidate: (candidate[0], candidate[1]), reverse=True)
    return round(usable[0][1], 2)


def _score_amount_candidate(line: str, raw_value: str, value: float) -> int:
    lower = line.lower()
    score = 3 if any(keyword in lower for keyword in AMOUNT_KEYWORDS) else 1

    if _has_strong_amount_keyword(line):
        score += 10
    if _looks_like_reference_line(line):
        score -= 5
    if _looks_like_account_line(line):
        score -= 5
    if _looks_like_decimal_amount(raw_value):
        score += 3
    if value <= 0:
        score -= 2
    if _looks_like_date_or_time_number(line, raw_value):
        score -= 2

    return score


def _has_strong_amount_keyword(line: str) -> bool:
    return _has_keyword(_match_text(line), STRONG_AMOUNT_KEYWORDS)


def _looks_like_reference_line(line: str) -> bool:
    return _has_keyword(_match_text(line), REFERENCE_KEYWORDS)


def _looks_like_account_line(line: str) -> bool:
    lower = line.lower()
    if "xxx-" in lower or "xxxx" in lower:
        return True
    if re.search(r"\b[xX]{2,}-[xX]{2,}\d{2,}-\d\b", line):
        return True
    if re.search(r"\b\d{3}-[xX\d]{1,}-[xX\d]{2,}-\d\b", line):
        return True
    return False


def _looks_like_decimal_amount(raw_value: str) -> bool:
    return bool(re.search(r"\.\d{1,2}$", raw_value.strip()))


def _format_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _normalize_year(year: int) -> int:
    if year >= 2400:
        return year - 543
    if year < 100:
        return 2000 + year
    return year


def _value_after_label(line: str) -> str | None:
    parts = re.split(r"[:：]\s*", line, maxsplit=1)
    if len(parts) == 2:
        return parts[1].strip()

    match = re.search(
        r"(?:merchant|receiver|recipient|payee|ผู้รับเงิน|ผู้รับ|ปลายทาง|ชื่อบัญชี)\s+(.+)",
        line,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return None


def _looks_like_merchant(value: str | None) -> bool:
    value = _clean_merchant_text(value)
    if not value:
        return False
    lower = value.lower()
    if any(keyword in lower for keyword in NOISE_MERCHANT_KEYWORDS):
        return False
    match_text = _match_text(value)
    if _has_keyword(match_text, SUCCESS_HEADER_KEYWORDS):
        return False
    if _has_keyword(match_text, BANK_OR_HEADER_KEYWORDS):
        return False
    if _has_keyword(match_text, AMOUNT_KEYWORDS + PAID_AMOUNT_KEYWORDS + ORIGINAL_AMOUNT_KEYWORDS + DISCOUNT_KEYWORDS):
        return False
    if _looks_like_category_line(value):
        return False
    if re.fullmatch(r"[\d\s.,:/-]+", value):
        return False
    if not any(ch >= "\u0e00" and ch <= "\u0e7f" for ch in value) and len(value.strip()) < 4:
        return False
    return len(value.strip()) >= 2


def _parse_number(value: str) -> float | None:
    try:
        return float(value.replace(",", "").replace("−", "-"))
    except ValueError:
        return None


def _number_matches(line: str, allow_negative: bool):
    sign = r"[-−]?\s*" if allow_negative else ""
    return re.finditer(
        rf"(?<![\d:]){sign}(?:\d{{1,3}}(?:,\d{{3}})+|\d+)(?:\.\d{{1,2}})?(?![\d:])",
        line,
    )


def _numbers_in_line(line: str, allow_negative: bool = False) -> list[float]:
    values = []
    for match in _number_matches(line, allow_negative=allow_negative):
        value = _parse_number(match.group(0).replace(" ", ""))
        if value is not None and not _looks_like_date_or_time_number(line, match.group(0)):
            values.append(value)
    return values


def _round_amount(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def _match_text(value: str) -> str:
    normalized = value.lower().translate(THAI_DIGITS)
    normalized = normalized.replace("\u0e4d\u0e32", "\u0e33")
    normalized = normalized.replace("\u0e4d", "")
    return re.sub(r"[\s:：,.-]+", "", normalized)


def _has_keyword(match_text: str, keywords: tuple[str, ...]) -> bool:
    return any(_match_text(keyword) in match_text for keyword in keywords)


def _looks_like_category_line(value: str) -> bool:
    match_text = _match_text(value)
    matches = sum(1 for keyword in MERCHANT_CATEGORY_KEYWORDS if _match_text(keyword) in match_text)
    return matches >= 2


def _looks_like_date_or_time_number(line: str, value: str) -> bool:
    if ":" in line:
        return True
    if re.search(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}", line):
        return True
    if re.search(r"20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}", line):
        return True
    return len(value) == 4 and value.startswith(("19", "20", "25"))
