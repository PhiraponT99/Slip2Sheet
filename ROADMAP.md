# Slip2Sheet Roadmap

## Completed Milestones

- V1.0 Save to Google Sheets
- V1.1 Summary Dashboard
- V1.2 Watch Folder
- V1.3 Duplicate Detection
- V1.4 Report CLI
- V1.5 Budget Tracking
- V1.5.1 SCB Parser Improvement
- V1.6 Merchant Alias
- V1.7 Merchant Category Mapping
- V1.7.1 Monthly Insights
- V1.8 Report Export
- V1.9 Monthly Budget Health Check
- V1.10 Release Safety Check
- V1.11 Terminal Dashboard
- V1.12 Spending Forecast
- V1.13 Spending Trend Analysis
- V1.14 Financial Goal Tracking
- V1.15 Daily Reflection
- V1.16 Reflection History
- V1.17 Weekly Reflection Summary
- V1.17.1 Weekly Reflection Message Refinement
- V1.18 Monthly Reflection Summary

## Proposed Milestones

## V1.19 Better Parser Test Dataset

### Goal

Improve parser confidence across real Thai slip formats.

### Scope

- Add anonymized OCR text fixtures for common Thai banks and payment flows.
- Cover success cases, missing fields, discounts, SCB transfers, wrapped merchant names, and noisy OCR.
- Keep fixtures text-only and free of private identifiers.

### Out of Scope

- Storing real personal slip images.
- Adding paid OCR services.
- Training ML models.

### Acceptance Criteria

- Parser tests include multiple banks/payment formats.
- Fixtures do not contain private account numbers, names, or credentials.
- Regression tests prevent known merchant/amount/date failures from returning.

## V1.20 Advanced Monthly Financial Insights

### Goal

Expand month-level spending insights beyond the V1.7.1 basics.

### Scope

- Add largest transactions.
- Add category share percentages.
- Add comparison against previous month where data exists.

### Out of Scope

- Investment, debt, or bank account analysis.
- Predictive modeling.
- Web dashboard.

### Acceptance Criteria

- `--month YYYY-MM` includes advanced insight fields without removing existing fields.
- Insights ignore rows marked `DUPLICATE_SKIPPED`.
- Tests cover calculations and empty-month behavior.

## V2.0 Mobile-Friendly Upload Flow

### Goal

Make slip upload easier from a phone.

### Scope

- Provide a lightweight local or hosted upload endpoint.
- Accept image upload and run the existing OCR/parser/save pipeline.
- Return JSON status to the user.

### Out of Scope

- Full dashboard UI.
- Bank API integration.
- Storing bank credentials.

### Acceptance Criteria

- A mobile browser can upload one slip image.
- Successful uploads save to Google Sheets.
- Duplicate detection still applies.
- Credentials remain server-side and are not exposed to the client.

## V2.1 LINE/Telegram Bot Upload

### Goal

Allow users to send slip images through a chat bot.

### Scope

- Add a bot webhook for LINE or Telegram.
- Download incoming images securely.
- Reuse the existing OCR/parser/save/report modules.
- Return a concise success/duplicate/failure message.

### Out of Scope

- Multi-user billing.
- Bank API integrations.
- Storing chat credentials in source code.

### Acceptance Criteria

- Sending a supported slip image to the bot creates or skips a transaction correctly.
- Duplicate and failure messages are clear.
- Bot secrets are loaded from environment variables.
- Tests cover webhook payload handling with mocked downloads.

## V2.2 Google Drive Auto Import

### Goal

Automatically process slip images placed in a Google Drive folder.

### Scope

- Poll or list a configured Drive folder.
- Download unprocessed image files.
- Run existing OCR/parser/save pipeline.
- Mark or move processed files.

### Out of Scope

- Replacing the local watch folder.
- Processing arbitrary document types.
- Storing Drive credentials in source code.

### Acceptance Criteria

- New Drive images are processed once.
- Processed and failed states are visible.
- Duplicate detection remains active.
- Tests cover Drive file selection and state transitions with mocks.

## V2.3 Web Dashboard

### Goal

Provide a browser-based view for summaries, budgets, and reports.

### Scope

- Display daily, monthly, category, and budget summaries.
- Show transactions with duplicate rows excluded by default.
- Reuse existing report and Summary logic.

### Out of Scope

- Bank API connections.
- Complex accounting features.
- Editing raw Google Sheets credentials from the UI.

### Acceptance Criteria

- Dashboard loads report data without opening Google Sheets.
- Budget status is visible.
- User can inspect monthly transactions.
- Existing CLI remains supported.
