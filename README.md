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
- Show monthly spending insights from report data.
- Export monthly reports to CSV or JSON files.
- Evaluate monthly budget health against expected spend.
- Run pre-commit safety checks before committing.
- Show a terminal dashboard for daily and monthly status.
- Forecast projected monthly spending from current pace.
- Analyze spending trends across monthly sheets.
- Track financial goals and progress.
- Generate a simple daily spending reflection.
- No graphical UI, bank APIs, or stored credentials.

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

Files in `samples/` must be sample/test slips only. Do not commit real personal payment slips.

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

Export a monthly report:

```bash
python main.py --month 2026-06 --export csv
python main.py --month 2026-06 --export json
```

Print the terminal dashboard:

```bash
python main.py --dashboard
```

Print dashboard data as JSON:

```bash
python main.py --dashboard --json
```

Analyze spending trends across monthly sheets:

```bash
python main.py --trend
```

Show financial goals:

```bash
python main.py --goals
```

Add or replace a financial goal:

```bash
python main.py --goal-add "Emergency Fund" 50000 10000
```

Update a goal's current amount:

```bash
python main.py --goal-update "Emergency Fund" 12000
```

Show today's spending reflection:

```bash
python main.py --reflection
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
  "insights": {
    "top_category": "food",
    "top_category_amount": 101.0,
    "top_merchant": "Lotus's",
    "top_merchant_amount": 65.0,
    "transaction_count": 2,
    "average_transaction": 50.5
  },
  "budget_health": {
    "monthly_budget": 9000.0,
    "days_in_month": 30,
    "current_day": 3,
    "expected_spend": 900.0,
    "actual_spend": 101.0,
    "variance": -799.0,
    "health_status": "GOOD",
    "health_message": "You are spending below your planned budget."
  },
  "forecast": {
    "current_day": 3,
    "days_in_month": 30,
    "actual_spend": 101.0,
    "daily_average_so_far": 33.67,
    "projected_monthly_spend": 1010.0,
    "monthly_budget": 9000.0,
    "projected_remaining_budget": 7990.0,
    "forecast_status": "UNDER_BUDGET"
  },
  "transactions": []
}
```

Monthly insights are calculated from non-duplicate rows in the selected monthly sheet:

- `top_category`: category with the highest spending
- `top_merchant`: merchant with the highest spending
- `transaction_count`: number of transactions in the report
- `average_transaction`: total expense divided by transaction count

Monthly budget health compares actual spending with the expected spend for the selected month:

- Current month uses today's local date.
- Historical months use the last day of that month.
- Future months use day 1.
- `GOOD`: variance is less than or equal to -20% of expected spend.
- `ON_TRACK`: variance is between -20% and +20% of expected spend.
- `OVERSPENDING`: variance is greater than +20% of expected spend.

Monthly spending forecast estimates the full-month result from the current pace:

- Current month uses today's local day of month.
- Historical months use the last day of that month.
- Future months use day 1.
- `UNDER_BUDGET`: projected spend is less than or equal to 80% of monthly budget.
- `ON_TRACK`: projected spend is greater than 80% and less than or equal to 100% of monthly budget.
- `OVER_BUDGET`: projected spend is greater than the monthly budget.

Monthly exports are written to `exports/`:

```text
exports/2026-06.csv
exports/2026-06.json
```

CSV exports use UTF-8 encoding and include one transaction row per line with:

```text
date, time, merchant, category, amount, original_amount, discount, payment_method, note, source_image, created_at, transaction_key
```

JSON exports include the selected month, total expense, category totals, insights, and transactions.

Export command output:

```json
{
  "month": "2026-06",
  "export_format": "csv",
  "export_file": "exports/2026-06.csv",
  "transaction_count": 27
}
```

Terminal dashboard output:

```text
══════════════════════════════════════
Slip2Sheet Dashboard
══════════════════════════════════════

Today
──────────────────────────────────────
Spent:              50.00 THB
Budget:            300.00 THB
Remaining:         250.00 THB
Status:                    OK

Month
──────────────────────────────────────
Spent:              50.00 THB
Budget:           9000.00 THB
Remaining:        8950.00 THB
Status:                  GOOD

Top Category
──────────────────────────────────────
food (50.00 THB)

Top Merchant
──────────────────────────────────────
Lotus's (50.00 THB)

Insights
──────────────────────────────────────
Transactions:               1
Average Spend:      50.00 THB

Forecast
──────────────────────────────────────
Projected:         375.00 THB
Remaining:        8625.00 THB
Status:          UNDER_BUDGET

══════════════════════════════════════
```

The dashboard reuses `today_report()` and `month_report()`. If the selected month has no sheet tab yet, it displays an empty dashboard instead of failing.

Trend output:

```json
{
  "months": [
    {
      "month": "2026-04",
      "total_expense": 8200.0
    },
    {
      "month": "2026-05",
      "total_expense": 7600.0
    },
    {
      "month": "2026-06",
      "total_expense": 50.0
    }
  ],
  "trend": {
    "direction": "DOWN",
    "change_percent": -99.3,
    "message": "Spending decreased compared to previous month."
  }
}
```

Trend analysis reads every sheet tab named `YYYY-MM`, sorts months ascending, calculates each monthly total, and compares the latest month with the previous month. Less than 5% change is `STABLE`; positive change is `UP`; negative change is `DOWN`.

Financial goals are stored in `goals.json`:

```json
{
  "Emergency Fund": {
    "target_amount": 50000,
    "current_amount": 10000
  }
}
```

Goal output is sorted by progress descending:

```json
{
  "goals": [
    {
      "name": "Emergency Fund",
      "target_amount": 50000,
      "current_amount": 10000,
      "progress_percent": 20.0
    }
  ]
}
```

The terminal dashboard includes a Goals section:

```text
Goals
──────────────────────────────────────
Emergency Fund           20.0%
Debt Payoff              12.8%
```

Daily reflection output:

```json
{
  "date": "2026-06-03",
  "total_expense": 50.0,
  "transaction_count": 1,
  "reflection": {
    "top_category": "food",
    "top_merchant": "Lotus's",
    "budget_status": "OK",
    "message": "You stayed within your daily budget today."
  }
}
```

Reflection messages:

- No transactions: `No spending recorded today.`
- Within daily budget: `You stayed within your daily budget today.`
- Over daily budget: `You exceeded your daily budget today.`

The terminal dashboard includes a Reflection section with the daily message.

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

## Pre-Commit Safety Check

Run before committing:

```bash
python main.py --precommit-check
```

The check runs unit tests and verifies that private or runtime files are not tracked by git:

- `.env`
- `credentials/`
- service account JSON files
- `exports/`
- `incoming/`
- `processed/`
- `failed/`

It also verifies that `.gitignore` contains the required safety entries and that any tracked sample images are documented as sample/test slips.

Example output:

```json
{
  "status": "PASS",
  "checks": {
    "tests": "PASS",
    "env_not_tracked": "PASS",
    "credentials_not_tracked": "PASS",
    "runtime_folders_not_tracked": "PASS",
    "gitignore_required_entries": "PASS",
    "sample_images_documented": "PASS"
  }
}
```
