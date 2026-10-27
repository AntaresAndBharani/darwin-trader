# Implementation Plan: Live Strategy Backtest Progress Telemetry & Black-Screen Crash Resilience

**Branch**: `feat/005-backtest-progress-resilience` | **Date**: 2026-10-27 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/005-backtest-progress-resilience/spec.md`

## Summary

Eliminate the black-screen unmount crash when running strategies in the Web Dashboard and provide real-time per-ticker execution progress feedback:
1. **Backend Progress Telemetry & Speed Optimization**: Add a `progress_callback` hook to `run_yahoo_portfolio_backtest()`, expose `GET /api/v1/yahoo/strategies/backtest/status` (`_backtest_state` synchronized via `_yahoo_lock`), and precompute `DarwinTrendStrategy` EMA/RSI/ATR indicators vectorially once per ticker DataFrame for a ~10x batch speedup.
2. **Frontend Live Progress UI & Crash Resilience**: Poll `/api/v1/yahoo/strategies/backtest/status` while a backtest is running, render a live progress banner (`Evaluating K / N tickers — <SYMBOL>...`, progress bar, and 100ms elapsed timer), add a contextual chart overlay when zero bars are plotted, default ticker selection to symbols with `price_bars_count > 0`, harden all numeric/date formatters against null/undefined values, wrap workspaces in a reusable `ErrorBoundary` component, and suppress benign `ECONNABORTED` WebSocket close errors in `vite.config.ts`.

## Technical Context

**Language/Version**: Python 3.11+ (Backend & Strategy Engine), TypeScript 5.6 / React 18.3 (Web UI)  
**Primary Dependencies**: FastAPI, Pydantic v2, Pandas, NumPy, React 18, Lightweight Charts v5, Axios, Vite 6, Vitest  
**Storage**: SQLite (`data/yahoo_finance.db` via `YahooFinanceDB` in WAL mode)  
**Testing**: `pytest` (`api_gateway/tests`, `strategy_engine/tests`, `tui/tests`) and `vitest` + `eslint` + `tsc -b` (`web/`)  
**Target Platform**: Windows / Cross-platform local server (`127.0.0.1:8000` & `localhost:5173`) and headless Linux CI runners  
**Project Type**: Full-stack Quantitative Trading Platform (FastAPI Gateway + Strategy Engine + React Web UI + Textual TUI)  
**Performance Goals**: `< 150ms` single-asset backtest, `< 300ms` 20-ticker batch backtest, `100ms` UI elapsed timer refresh, `0` unmounted black-screen crashes  
**Constraints**: Strict isolation from Darwinex MT5 live state (`routes_strategy.py` and `historical_rates.db` untouched); 100% offline deterministic test suites.  
**Scale/Scope**: ~1,000 active Yahoo Finance tickers in `data/yahoo_finance.db`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Clean Architecture & Pure Quantitative Core**: **PASS** — `yahoo_backtester.py` and `sample_strategy.py` remain pure Python/Pandas/NumPy with zero transport dependencies; progress callbacks are injected via standard Python callables.
- **II. Darwinex Zero Risk & Capital Preservation**: **PASS** — Yahoo Finance backtesting remains 100% isolated from live MT5 execution and `RiskManager`.
- **III. Zero-Click Operational Readiness & Scoped Client Evolution**: **PASS** — Enhances the Web `StrategyLifecycleWorkspace` and Vite dev server proxy without affecting TUI workflows.
- **IV. Test-First & Platform-Independent Simulation**: **PASS** — Full unit and integration tests in both `pytest` and `vitest` run deterministically offline.
- **V. Structured Concurrency, Lock Discipline & Observability**: **PASS** — `_backtest_state` updates in `routes_yahoo.py` are synchronized under `_yahoo_lock` (`threading.Lock`).
- **VI. Multi-Provider Data Isolation & Self-Contained Storage**: **PASS** — Reads strictly from `YahooFinanceDB` (`data/yahoo_finance.db`).

## Project Structure

### Documentation (this feature)

```text
specs/005-backtest-progress-resilience/
├── plan.md                          # This file
├── research.md                      # Phase 0 technical decisions
├── data-model.md                    # Phase 1 state & interface models
├── quickstart.md                    # Phase 1 verification guide
├── contracts/
│   └── backtest-progress-api.md     # REST & UI testid contracts
├── checklists/
│   ├── requirements.md              # Spec quality checklist
│   └── resilience-ux.md             # Domain quality checklist
└── tasks.md                         # Phase 2 actionable task breakdown
```

### Source Code (repository root)

```text
api_gateway/
├── routes_yahoo.py                  # Add _backtest_state + GET /strategies/backtest/status + progress callback wiring
└── tests/
    └── test_routes_yahoo.py         # Add endpoint & progress state tests

strategy_engine/
├── sample_strategy.py               # Support precomputed _ema_fast, _ema_slow, _rsi, _atr columns
├── yahoo_backtester.py              # Precompute DarwinTrend indicators + invoke progress_callback per symbol
└── tests/
    └── test_yahoo_backtester.py     # Add progress_callback & precomputed DarwinTrend parity tests

web/
├── vite.config.ts                   # Suppress benign ws proxy ECONNABORTED/ECONNRESET socket errors
└── src/
    ├── App.tsx                      # Wrap workspace tabs in ErrorBoundary
    ├── App.test.tsx                 # Verify ErrorBoundary resilience
    ├── api/
    │   ├── yahoo.ts                 # Add YahooBacktestStatusResponse & yahooApi.getBacktestStatus()
    │   └── yahoo.test.ts            # Unit test getBacktestStatus()
    └── components/
        ├── ErrorBoundary.tsx        # Reusable React Error Boundary with recovery UI
        ├── ErrorBoundary.test.tsx   # Unit tests for ErrorBoundary capture & reset
        ├── StrategyLifecycleWorkspace.tsx       # Live progress card, elapsed timer, chart empty overlay, safe formatters
        └── StrategyLifecycleWorkspace.test.tsx  # Progress bar, empty chart overlay, and edge-case payload tests
```

**Structure Decision**: Extends existing modules in `strategy_engine/`, `api_gateway/`, and `web/src/` and adds one focused component (`web/src/components/ErrorBoundary.tsx` + test) in compliance with Darwin Trader's modular architecture.

## Complexity Tracking

No Constitution violations or unjustified complexity.
