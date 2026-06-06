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

2026-06-06

- V1.28 Google Cloud Run Readiness
- Add Dockerfile using Python 3.11 for the LINE webhook runtime
- Add `.dockerignore` to keep local env files, credentials, runtime folders, reports, exports, and caches out of Docker builds
- Add `GET /healthz` returning plain text `ok`
- Document local run, Docker run, Cloud Run deploy, required environment variables, and production secret handling
- V1.29 Cloud Run Deployment Setup
- Document required Google Cloud services, environment variables, Secret Manager secrets, and deployment checklist
- Add safe `gcloud` examples for project setup, service enablement, secret creation, Cloud Run deployment, secret mounting, and LINE webhook setup
- V1.30 Cloud Run Production Smoke Test
- Add final Cloud Run smoke test checklist for health checks, LINE webhook verification, slip image processing, Google Sheet append logs, daily summary, and redelivery skip behavior
- Add final secret-based Cloud Run deploy template, log inspection command, git tag instructions, and rollback notes
- V1.30.1 Cloud Run OCR Runtime Fix
- Resolve Tesseract path from `TESSERACT_CMD`, Windows default path, PATH lookup, or Linux `/usr/bin/tesseract`
- Install English and Thai Tesseract language packages in the Docker image
