2026-06-03

- Initial OCR support
- Google Sheets integration
- Summary dashboard
- Watch folder
- Duplicate detection
- Budget tracking
- Merchant alias support
- SCB transfer slip support

2026-06-05

- V1.26.2 Amount Ranking Fix
- Prioritize explicit payment amount lines such as `จำนวนเงิน`, `จํานวนเงิน`, `ยอดเงิน`, `amount`, and `total`
- Penalize masked account, reference, biller, and merchant ID lines during amount ranking
- Prefer decimal amount candidates such as `58.00` over integer fragments from account numbers
- V1.26.3 Pretty LINE Transaction Reply
- Format LINE transaction replies with a clearer title, blank-line grouping, two-decimal THB amounts, and `-` for missing fields
- V1.26.4 Better Merchant Detection
- Prefer merchant lines near `ไปยัง`, `To`, `Payee`, `Merchant`, and `Biller`
- Ignore success headers such as `จ่ายบิลสำเร็จ`, `โอนเงินสำเร็จ`, `payment successful`, and `success`
- Clean leading symbols and merge wrapped merchant names such as `CP AXTRA PUBLIC COMPANY` plus `LIMITED (HEAD`
- V1.26.6 Duplicate LINE Slip Detection
- Store recent LINE duplicate keys in `processed/line_duplicates.json`
- Detect duplicate LINE slips using `date|time|amount|merchant`
- Reply with a duplicate summary instead of the normal transaction summary for repeated submissions
- V1.27 LINE Daily Summary
- Add LINE text commands `สรุปวันนี้` and `summary today`
- Reuse existing daily report, budget, and reflection calculations for the LINE summary reply
- Keep ordinary text replies and LINE image processing unchanged
