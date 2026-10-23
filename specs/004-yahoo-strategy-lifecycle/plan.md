# Implementation Plan: Yahoo Finance Strategy Lifecycle & Backtesting Control Panel

**Branch**: `feat/004-yahoo-strategy-lifecycle` | **Date**: 2026-10-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-yahoo-strategy-lifecycle/spec.md`

## Summary

Promote the Strategy Lifecycle experience into a dedicated full-screen Web workspace tab (**Strategy Lifecycle**) that runs registered quantitative strategies (`DarwinTrendStrategy` and `DarwinXZeroTraderStrategy`) exclusively against Yahoo Finance historical data (`data/yahoo_finance.db`). Provide a comprehensive control panel supporting single-asset and multi-asset/sector batch selection, dynamic strategy and simulation parameter tuning with reset-to-defaults, on-demand mark-to-market backtesting, KPI summary cards, an interactive chart toggling between the Equity Curve and Price Chart with Buy/Sell markers, a clickable Multi-Asset Comparison Table, and a Trade Execution Log.

## Technical Context

**Language/Version**: Python 3.11+ (Backend & Strategy Engine), TypeScript 5.x / React 18 (Web Client)

**Primary Dependencies**: FastAPI, Pydantic v2, Pandas, NumPy, SQLite3 (`YahooFinanceDB`), React 18, Vite, TailwindCSS, Axios, TradingView Lightweight Charts (`lightweight-charts`)

**Storage**: `data/yahoo_finance.db` (SQLite WAL mode via `YahooFinanceDB`, strictly isolated from `data/historical_rates.db`)

**Testing**: `pytest` (Backend & Strategy Engine), `vitest` + `@testing-library/react` + `eslint` + `tsc` (Web Client)

**Target Platform**: Local Workstation & Headless Linux/Windows CI Runners

**Project Type**: Full-Stack Web & Quantitative Trading Application (`strategy_engine/`, `api_gateway/`, `web/`)

**Performance Goals**: `< 500ms` single-asset backtest execution; `< 3s` multi-asset batch backtest (25 tickers)

**Constraints**: Zero side effects on Darwinex Zero MT5 live connector (`routes_strategy.py`) or `data/historical_rates.db`; zero-lookahead Weekly Heikin-Ashi alignment; finite JSON float serialization (no `NaN`/`Infinity`)

**Scale/Scope**: 1,011+ Yahoo Finance tickers, 1.31M+ daily price rows (`D1`, `W1`, `MN1` timeframes)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Clean Architecture & Pure Quantitative Core**: **PASS** — Strategy execution, MTM backtesting, and Weekly Heikin-Ashi zero-lookahead alignment reside in `strategy_engine/yahoo_backtester.py` with zero FastAPI/UI imports; FastAPI endpoints reside in `api_gateway/routes_yahoo.py`; React UI communicates strictly via `/api/v1/yahoo/*`.
- **II. Darwinex Zero Risk & Capital Preservation**: **PASS** — Live Darwinex Zero MT5 routes (`routes_strategy.py`) and emergency kill-switch behavior remain untouched.
- **III. Zero-Click Operational Readiness & Scoped Client Evolution**: **PASS** — Adds the top-level **Strategy Lifecycle** tab in `web/src/App.tsx` alongside **Darwinex MT5** and **Yahoo Finance**, and removes the legacy bottom-right `StrategySidebar` card from the Darwinex MT5 tab while keeping TUI workflows intact.
- **IV. Test-First & Platform-Independent Simulation**: **PASS** — All unit and integration tests run offline using temporary SQLite `YahooFinanceDB` fixtures and Vitest mocked API payloads.
- **V. Structured Concurrency, Lock Discipline & Observability**: **PASS** — Reads from `YahooFinanceDB` use WAL context-managed connections without holding write locks during compute.
- **VI. Multi-Provider Data Isolation & Self-Contained Storage**: **PASS** — 100% of Strategy Lifecycle backtests query `YahooFinanceDB` (`data/yahoo_finance.db`) and never touch `HistoricalRatesDB` (`data/historical_rates.db`).

## Project Structure

### Documentation (this feature)

```text
specs/004-yahoo-strategy-lifecycle/
├── plan.md                          # This file (/speckit-plan command output)
├── research.md                      # Phase 0 output (/speckit-plan command)
├── data-model.md                    # Phase 1 output (/speckit-plan command)
├── quickstart.md                    # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── yahoo-strategy-api.md        # Phase 1 API contracts
└── tasks.md                         # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
strategy_engine/
├── yahoo_db.py                      # Yahoo Finance SQLite WAL storage + date-range price queries
├── yahoo_backtester.py              # Yahoo Finance strategy catalog, parameter schemas, zero-lookahead W1 HA alignment & MTM portfolio/single backtester
├── strategies/
│   └── darwinx_zero_trader.py       # Configurable Quad-MA & 3-stage parameters on DarwinXZeroTraderStrategy
└── tests/
    └── test_yahoo_backtester.py     # Unit tests for single/multi-asset Yahoo backtesting, custom params & MTM invariants

api_gateway/
├── routes_yahoo.py                  # GET /api/v1/yahoo/strategies and POST /api/v1/yahoo/strategies/backtest
└── tests/
    └── test_routes_yahoo.py         # FastAPI integration tests for Yahoo strategy catalog & backtest endpoints

web/
└── src/
    ├── App.tsx                      # 3 top-level tabs: Darwinex MT5, Yahoo Finance, Strategy Lifecycle
    ├── App.test.tsx                 # Top-level tab navigation tests
    ├── api/
    │   ├── yahoo.ts                 # Client methods & TypeScript types for getStrategies() and runBacktest()
    │   └── yahoo.test.ts            # Unit tests for Yahoo strategy API client methods
    └── components/
        ├── StrategyLifecycleWorkspace.tsx       # Full-screen Yahoo Finance Strategy Control Panel & Results Dashboard
        └── StrategyLifecycleWorkspace.test.tsx  # Component tests for asset switching, param editing, batch drill-down & chart toggling
```

**Structure Decision**: Extends the existing 3-tier modular architecture (`strategy_engine/` → `api_gateway/` → `web/src/`) by introducing a dedicated `strategy_engine/yahoo_backtester.py` service, mounting `/strategies` and `/strategies/backtest` on `api_gateway/routes_yahoo.py`, and adding `web/src/components/StrategyLifecycleWorkspace.tsx` as the 3rd top-level workspace tab in `web/src/App.tsx`.

## Complexity Tracking

No Constitution violations—table omitted.
