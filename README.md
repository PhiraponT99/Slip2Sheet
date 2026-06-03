# Personal Expense Tracker V1

Extract transaction details from one payment slip image, print JSON, and optionally append the parsed row to Google Sheets.

## Scope

- Accept one local image path.
- Run OCR on the image.
- Extract transaction fields from the slip text.
- Optionally save one parsed slip row to Google Sheets.
- Automatically refresh a `Summary` dashboard sheet after saving.
- Watch an `incoming/` folder and process dropped slip images automatically.
- Detect duplicate transactions before saving.
- View daily and monthly spending reports from the command line.
- Backfill missing transaction keys and mark older duplicate rows.
- Track daily and monthly budgets in reports and Summary.
- Assign categories from configurable merchant category mappings.
- No UI, dashboard, bank APIs, or stored credentials.

## Project Structure

```text
.
├── AGENT.md
├── ROADMAP.md
├── main.py
├── expense_tracker/
│   ├── __init__.py
│   ├── models.py
│   ├── ocr.py
│   ├── parser.py
│   ├── reports.py
│   ├── sheets.py
│   ├── summary.py
│   └── maintenance.py
├── samples/
├── incoming/
├── processed/
├── failed/
├── merchant_aliases.json
├── tests/
├── .env.example
├── .gitignore
└── requirements.txt
```

## Project Guidance

- [AGENT.md](AGENT.md) defines project scope, architecture, hard rules, data rules, and development style for future AI coding agents.
- [ROADMAP.md](ROADMAP.md) tracks completed milestones and proposed next milestones.

## Setup

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Install the native Tesseract OCR engine and Thai language data. On Windows, this project is configured for:

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
```

The OCR module requests Thai and English text with `tha+eng`.

## Google Sheets Setup

1. Create a Google Cloud service account.
2. Enable the Google Sheets API for the project.
3. Download the service account JSON key file.
4. Share the target Google Sheet with the service account email as an editor.
5. Copy `.env.example` to `.env` and set:

```text
GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\service-account.json
GOOGLE_SHEET_ID=your_google_sheet_id_here
DAILY_BUDGET=300
MONTHLY_BUDGET=9000
```

`.gitignore` excludes `.env` and `*.json`, so service account credentials should stay out of git.

`DAILY_BUDGET` and `MONTHLY_BUDGET` are optional. Defaults are `300` and `9000`.

## Usage

Print parsed JSON only:

```bash
python main.py --image ./samples/slip1.jpg
```

Print parsed JSON and append to Google Sheets:

```bash
python main.py --image ./samples/slip1.jpg --save
```

When `--save` succeeds, the output includes:

```json
{
  "date": "2026-06-03",
  "time": "14:19",
  "merchant": "กะเพราหอม",
  "amount": 26.0,
  "original_amount": 65.0,
  "discount": 39.0,
  "raw_text": "...",
  "saved": true,
  "duplicate": false,
  "sheet_tab": "2026-06",
  "summary_updated": true
}
```

If the transaction already exists in the target monthly sheet:

```json
{
  "saved": false,
  "duplicate": true,
  "sheet_tab": "2026-06",
  "message": "Duplicate transaction detected. Skipped."
}
```

Print today's spending report from Google Sheets:

```bash
python main.py --today
```

Print a monthly spending report from Google Sheets:

```bash
python main.py --month 2026-06
```

Daily report output:

```json
{
  "date": "2026-06-03",
  "total_expense": 101.0,
  "daily_budget": 300.0,
  "remaining_budget": 199.0,
  "budget_status": "OK",
  "category_totals": {
    "food": 101.0
  },
  "transactions": []
}
```

Monthly report output:

```json
{
  "month": "2026-06",
  "total_expense": 101.0,
  "monthly_budget": 9000.0,
  "remaining_budget": 8899.0,
  "budget_status": "OK",
  "category_totals": {
    "food": 101.0
  },
  "transactions": []
}
```

Add or update a merchant alias:

```bash
python main.py --add-alias "CP AXTRA PUBLIC COMPANY LIMITED (HEAD" "Lotus's"
```

Aliases are stored in `merchant_aliases.json`. New OCR parses use the normalized merchant immediately, and reports also normalize existing sheet rows when displaying transactions.

Add or update a merchant category mapping:

```bash
python main.py --add-category "Lotus's" "food"
```

Categories are stored in `merchant_categories.json`. Supported category strings are:

```text
food
drink
convenience
transport
rent
phone
subscription
shopping
health
other
```

Merchant category mappings are checked after merchant alias normalization. If no mapping exists, the app falls back to the existing rule-based category logic.

## Monthly Sheet Rule

The sheet tab is derived from the transaction date:

```text
2026-06-03 -> 2026-06
```

If the monthly tab does not exist, the app creates it and writes this schema B header:

```text
Date, Time, Merchant, Category, Amount, OriginalAmount, Discount, PaymentMethod, Note, SourceImage, CreatedAt, TransactionKey
```

`SourceImage` is the input image filename. `CreatedAt` is the current system timestamp in ISO format.

Category inference starts simple:

- `food`: text contains `กะเพรา`, `ข้าว`, `อาหาร`, or `food`
- `drink`: text contains `กาแฟ`, `coffee`, `cafe`, or `amazon`
- `other`: everything else

`PaymentMethod` is inferred from slip text when possible. `Note` is set to detected discount program text when available.

## Duplicate Detection

Monthly sheets include a `TransactionKey` column:

```text
date|time|merchant|amount
```

Example:

```text
2026-06-03|14:19|กะเพราหอม|26.0
```

Before appending, the app reads the target monthly sheet and skips the append if the same `TransactionKey` already exists.

## Data Cleanup

Rows saved before V1.3 may have an empty `TransactionKey`, which prevents duplicate detection from seeing older rows. Backfill keys first:

```bash
python main.py --backfill-keys
```

This reads every monthly tab matching `YYYY-MM`, generates missing keys using:

```text
date|time|merchant|amount
```

Then it updates the `TransactionKey` cells and refreshes `Summary`.

After backfill, mark duplicate rows:

```bash
python main.py --dedupe
```

This keeps the oldest row for each `TransactionKey` and marks later duplicates by setting `Note` to:

```text
DUPLICATE_SKIPPED
```

Marked duplicates are ignored by Summary, `--today`, and `--month` reports. The dedupe command refreshes `Summary` after marking rows.

## Summary Dashboard

After `--save` appends a row, the app reads every monthly tab whose name matches `YYYY-MM`, ignores `Summary`, recalculates totals, and rewrites the `Summary` sheet.

Summary section 1:

```text
Metric | Value
Total Expense
Food Expense
Transport Expense
Utilities Expense
Other Expense
```

Summary section 2:

```text
Month | Total Expense
```

Months are sorted ascending. Categories other than `food`, `transport`, and `utilities` are included in `Other Expense`.

Summary also includes a Budget Overview section:

```text
Budget Overview
Metric | Value
Daily Budget
Monthly Budget
Current Month Expense
Remaining Monthly Budget
Budget Status
```

Budget status rules:

- `OK`: total expense is less than or equal to 80% of the budget
- `WARNING`: total expense is greater than 80% and less than or equal to 100%
- `OVER_BUDGET`: total expense is greater than 100%

## Watch Folder Mode

Run:

```bash
python watch.py
```

Then drop slip images into `incoming/`.

Supported image extensions:

```text
.jpg
.jpeg
.png
```

For each new image in the current watch session, the watcher:

1. Runs OCR.
2. Parses the transaction.
3. Saves the row to Google Sheets.
4. Refreshes the `Summary` sheet.
5. Moves the image to `processed/` if successful.
6. Moves the image to `failed/` if processing fails.
7. Moves duplicate images to `processed/duplicate/`.

Logs look like:

```text
[INFO] Watching incoming/
[INFO] Processing slip1.jpg
[INFO] Saved to sheet tab 2026-06
[INFO] Summary updated
[INFO] Moved to processed/
[ERROR] Failed to process slip1.jpg: <reason>
```

Duplicate logs look like:

```text
[WARN] Duplicate transaction detected: slip2.jpg
[INFO] Skipped save
[INFO] Moved to processed/
```

Duplicate processing is prevented during a single watch session by tracking filenames in memory.

## Tests

```bash
python -m unittest discover -s tests
```
