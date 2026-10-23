# Phase 1 Quickstart & Verification Guide

## Prerequisites
- Python 3.11+ with `darwin-trader` virtual environment active (`yahooquery`, `psycopg2-binary`, `fastapi`, `pytest`).
- Node.js 20+ (`npm` in `web/`).
- Optional for one-time migration: Local PostgreSQL at `localhost:5433/fractanomicsdb` containing the legacy `tickers`, `stock_prices`, and `valuation_history` tables.

## 1. Migrate Existing Yahoo Finance Data from PostgreSQL to SQLite

Run the CLI migration command from the repository root:

```powershell
python -m strategy_engine.cli yahoo-migrate --pg-host localhost --pg-port 5433 --pg-db fractanomicsdb --pg-user postgres --pg-pass postgres
```

Expected output:
```text
Migrated 1011 tickers, 1313580 stock price rows, and 12374 valuation history rows into data\yahoo_finance.db.
```

## 2. Sync a Ticker via CLI

```powershell
python -m strategy_engine.cli yahoo-sync --symbol AAPL --include-fundamentals --include-valuation --include-metadata
```

## 3. Run Automated Test Suites

### Backend & Quantitative Engine
```powershell
pytest api_gateway/tests strategy_engine/tests tui/tests -v
```

### Web Frontend (Unit Tests, Linter, and Production Build)
```powershell
cd web
npm test
npm run lint
npm run build
```

## 4. Launch Web Dashboard

```powershell
.\scripts\run-web.ps1
```
- Open the browser URL printed by Vite (`http://localhost:5173`).
- Verify the **Darwinex MT5** tab displays the chart and full-width **Open Positions** grid (with no `StrategySidebar`).
- Click the **Yahoo Finance** tab to filter the 1,011 migrated tickers by Market, Sector, Industry, or search query, view `D1`/`W1`/`MN1` Candlestick and Heikin-Ashi charts, and inspect the Fundamentals & Quarterly Valuation multiples.
