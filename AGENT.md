# Slip2Sheet Agent Guide

## Project Name

Slip2Sheet

## Purpose

Slip2Sheet is a personal expense tracking system that reads Thai payment slip images, extracts transaction data, saves it to Google Sheets, and provides summaries/reports.

## Main Workflow

```text
Slip image
-> OCR
-> Parser
-> Merchant normalization
-> Category assignment
-> Duplicate detection
-> Google Sheets
-> Summary dashboard
-> CLI reports
-> Terminal dashboard
-> Trend analysis
-> Financial goals
-> Daily reflection
-> Reflection history
-> Weekly reflection
-> Monthly reflection
```

## Current Capabilities

- V1.0 Save parsed slip to Google Sheets
- V1.1 Summary Dashboard
- V1.2 Watch Folder Mode
- V1.3 Duplicate Detection
- V1.4 Daily/Monthly Report CLI
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

## Core Modules

- `main.py`
- `watch.py`
- `expense_tracker/ocr.py`
- `expense_tracker/parser.py`
- `expense_tracker/sheets.py`
- `expense_tracker/summary.py`
- `expense_tracker/reports.py`
- `expense_tracker/maintenance.py`
- `expense_tracker/exports.py`
- `expense_tracker/safety.py`
- `expense_tracker/dashboard.py`
- `expense_tracker/trends.py`
- `expense_tracker/goals.py`
- `expense_tracker/reflection.py`
- `expense_tracker/reflection_history.py`
- `expense_tracker/weekly_reflection.py`
- `expense_tracker/monthly_reflection.py`
- `merchant_aliases.json`
- `merchant_categories.json`
- `goals.json`

## Hard Rules

- Do not commit credentials.
- Do not modify OCR logic unless task explicitly asks for OCR improvement.
- Do not modify parser logic unless task explicitly asks for parser improvement.
- Do not rewrite Google Sheets integration unnecessarily.
- Do not remove duplicate detection.
- Do not change sheet schema without migration/backfill support.
- Do not connect to bank APIs.
- Do not store bank credentials.
- Run `python main.py --precommit-check` before committing.
- Keep changes small and incremental.
- Preserve backward compatibility where possible.

## Data Rules

- `Amount` means actual paid amount.
- `OriginalAmount` means pre-discount amount.
- `Discount` means discount or subsidy amount.
- `SourceImage` must be preserved.
- `TransactionKey` format:

```text
date|time|merchant|amount
```

## Security Rules

- `.env` must not be committed.
- Service account JSON must not be committed.
- Raw private keys must never be pasted into docs.
- Use `.env.example` for placeholders only.
- Runtime folders such as `exports/`, `incoming/`, `processed/`, and `failed/` must not be committed.

## Preferred Development Style

- Add tests for every feature.
- Keep CLI behavior stable.
- Prefer small helper modules.
- Keep Thai slip support as primary use case.
- Use simple rule-based logic first before adding AI/ML.
