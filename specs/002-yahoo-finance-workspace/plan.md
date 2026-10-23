# Implementation Plan: Yahoo Finance Market Data Integration, Legacy Data Migration & Web Explorer Workspace

**Branch**: `feat/002-yahoo-finance-workspace` | **Date**: 2026-10-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-yahoo-finance-workspace/spec.md`

## Summary

Integrate Yahoo Finance stock data (daily OHLCV with `D1`/`W1`/`MN1` resampling, market/sector/industry ticker metadata, quarterly EPS & revenue, and quarterly valuation multiples) into Darwin Trader alongside Darwinex Zero MT5 data. Store Yahoo Finance data in an isolated SQLite WAL database (`data/yahoo_finance.db`), migrate the existing 1,011 tickers, 1,313,580 price rows, and 12,374 valuation rows from PostgreSQL (`localhost:5433/fractanomicsdb`), expose `/api/v1/yahoo/*` FastAPI endpoints and `yahoo-migrate`/`yahoo-sync` CLI commands, remove the placeholder `StrategySidebar` from the **Darwinex MT5** tab, and add a top-level **Yahoo Finance** Master-Detail Explorer tab (`YahooWorkspace.tsx`) in the React Web Dashboard.

## Technical Context

**Language/Version**: Python 3.11+ (Backend & Strategy Engine), TypeScript 5 / React 18 (Web Client)

**Primary Dependencies**: FastAPI, Pydantic v2, Pandas, NumPy, SQLite3 (`WAL` mode), `yahooquery`, `psycopg2-binary` (for legacy migration), React 18, Axios, TailwindCSS, TradingView `lightweight-charts`, Vitest

**Storage**: `data/yahoo_finance.db` (SQLite WAL mode with `tickers`, `stock_prices`, and `valuation_history` tables, isolated from `data/historical_rates.db`)

**Testing**: `pytest` (`api_gateway/tests`, `strategy_engine/tests`, `tui/tests`) and `vitest` / `eslint` / `tsc` (`web/`)

**Target Platform**: Windows / Cross-platform local workstation & headless Linux CI runners

**Project Type**: Full-stack algorithmic trading platform (`strategy_engine` + `api_gateway` + `web` + `tui`)

**Performance Goals**: Migrate 1.31M rows in `<60s`; ticker filtering and `D1`/`W1`/`MN1` chart + fundamentals queries in `<500ms`

**Constraints**: Zero external database servers required at runtime; 100% offline deterministic unit/integration tests on CI

**Scale/Scope**: 1,011 tracked global tickers, 1.31M+ daily price bars, 12.3k+ quarterly valuation snapshots

## Constitution Check

*GATE: Checked before Phase 0 research and re-verified after Phase 1 design against Constitution v1.1.0.*

- **I. Clean Architecture & Pure Quantitative Core**: **PASS** — `yahoo_db.py` and `yahoo_fetcher.py` reside in `strategy_engine/`; FastAPI routes live in `api_gateway/routes_yahoo.py`; React UI (`web/src/components/YahooWorkspace.tsx`) communicates strictly through `/api/v1/yahoo/*`.
- **II. Darwinex Zero Risk & Capital Preservation**: **PASS** — Emergency Kill Switch and `PositionsGrid` remain intact and now span full width on the `Darwinex MT5` tab.
- **III. Zero-Click Operational Readiness & Scoped Client Evolution**: **PASS** — Startup auto-connect and `ConnectModal` parity remain untouched; Web Dashboard adds top-level `Darwinex MT5` and `Yahoo Finance` tabs and retires the unused `StrategySidebar` placeholder.
- **IV. Test-First & Platform-Independent Simulation**: **PASS** — `yahoo_fetcher.py` accepts injectable ticker factories and mockable database connections so all Python and Web tests run 100% offline on CI.
- **V. Structured Concurrency, Lock Discipline & Observability**: **PASS** — `YahooFinanceDB` uses WAL mode, context-managed connection closure, `BEGIN IMMEDIATE` transactions, and exponential-backoff retries on `SQLITE_BUSY`/`SQLITE_LOCKED`.
- **VI. Multi-Provider Data Isolation & Self-Contained Storage**: **PASS** — `data/yahoo_finance.db` is completely isolated from `data/historical_rates.db` and requires no runtime PostgreSQL daemon.

## Project Structure

### Documentation (this feature)

```text
specs/002-yahoo-finance-workspace/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output (/speckit-plan)
├── data-model.md        # Phase 1 output (/speckit-plan)
├── quickstart.md        # Phase 1 output (/speckit-plan)
├── contracts/
│   └── yahoo-api.md     # Phase 1 REST & CLI contracts (/speckit-plan)
├── checklists/
│   ├── requirements.md  # Spec quality checklist (/speckit-specify)
│   └── yahoo-data.md    # Domain requirements checklist (/speckit-checklist)
└── tasks.md             # Phase 2 task list (/speckit-tasks)
```

### Source Code (repository root)

```text
strategy_engine/
├── yahoo_db.py                  # NEW: SQLite WAL storage & D1/W1/MN1 resampling for Yahoo Finance
├── yahoo_fetcher.py             # NEW: yahooquery OHLCV/metadata/valuation fetcher & PG migrator
├── cli.py                       # MODIFIED: Add yahoo-migrate and yahoo-sync CLI subcommands
├── requirements.txt             # MODIFIED: Add yahooquery and psycopg2-binary
└── tests/
    ├── test_yahoo_db.py         # NEW: Unit tests for YahooFinanceDB & resampling
    └── test_yahoo_fetcher.py    # NEW: Unit tests for Yahoo fetcher, migrator & CLI

api_gateway/
├── routes_yahoo.py              # NEW: FastAPI /api/v1/yahoo/* endpoints
├── main.py                      # MODIFIED: Include yahoo_router
└── tests/
    └── test_routes_yahoo.py     # NEW: FastAPI integration tests for /api/v1/yahoo/*

web/
└── src/
    ├── App.tsx                  # MODIFIED: Top-level tabs (Darwinex MT5 / Yahoo Finance) & remove StrategySidebar
    ├── App.test.tsx             # MODIFIED: Tests for tab switching & full-width PositionsGrid
    ├── api/
    │   ├── yahoo.ts             # NEW: Typed Axios client for /api/v1/yahoo/*
    │   └── yahoo.test.ts        # NEW: Unit tests for yahooApi
    └── components/
        ├── YahooWorkspace.tsx       # NEW: Master-detail Yahoo Finance Explorer, Chart & Fundamentals view
        └── YahooWorkspace.test.tsx  # NEW: Component tests for YahooWorkspace
```

**Structure Decision**: Extends the existing 3-tier modular architecture (`strategy_engine/` → `api_gateway/` → `web/src/`) without introducing new top-level packages.

## Complexity Tracking

No Constitution violations exist.
