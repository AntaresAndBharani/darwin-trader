---
description: "Task list for Live Strategy Backtest Progress Telemetry & Black-Screen Crash Resilience"
---

# Tasks: Live Strategy Backtest Progress Telemetry & Black-Screen Crash Resilience

**Input**: Design documents from `/specs/005-backtest-progress-resilience/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/backtest-progress-api.md`  
**Tests**: Included per Darwin Trader Constitution Principle IV (`pytest` + `vitest` 100% pass requirement).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`)
- Exact file paths are included in every task description.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Ensure branch synchronization and baseline verification

- [X] T001 Verify feature branch `feat/005-backtest-progress-resilience` is up to date with `origin/main` and `.specify/feature.json` points to `specs/005-backtest-progress-resilience`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Backend progress callback hook and frontend TypeScript contract definitions required by all user stories

- [X] T002 Add optional `progress_callback: Optional[Callable[[str, int, int], None]] = None` parameter to `run_yahoo_portfolio_backtest()` in `strategy_engine/yahoo_backtester.py` and invoke it before and after evaluating each symbol in `target_symbols`
- [X] T003 [P] Add `YahooBacktestStatusResponse` interface (`status: 'IDLE' | 'RUNNING' | 'COMPLETED' | 'FAILED'`, `strategy_id`, `strategy_name`, `timeframe`, `total_symbols`, `completed_symbols`, `current_symbol`, `progress_pct`, `elapsed_ms`, `message`) and `yahooApi.getBacktestStatus()` (`GET /yahoo/strategies/backtest/status`) in `web/src/api/yahoo.ts`

---

## Phase 3: User Story 1 - Live Per-Ticker Execution Progress & Elapsed Time Feedback (Priority: P1) 🎯 MVP

**Goal**: Expose live per-ticker backtest progress telemetry from the FastAPI Gateway and render an interactive progress card (`Evaluating K / N tickers — <SYMBOL>...`), progress bar (`0%–100%`), and live elapsed timer (`0.0s`) in `StrategyLifecycleWorkspace`.

**Independent Test**: Click **Run Backtest** in `StrategyLifecycleWorkspace` and verify `data-testid="strategy-backtest-progress"` immediately displays with `data-testid="strategy-progress-bar"`, `data-testid="strategy-elapsed-time"`, and the live ticker counter message, polling `GET /api/v1/yahoo/strategies/backtest/status` until results render.

### Implementation & Tests for User Story 1

- [X] T004 [US1] Implement thread-safe `_backtest_state` dictionary (protected by `_yahoo_lock`), update `execute_yahoo_strategy_backtest` (`POST /api/v1/yahoo/strategies/backtest`) to record live progress (`RUNNING` -> `COMPLETED` / `FAILED`, `progress_pct`, `elapsed_ms`, `message="Evaluating K / N tickers — <SYMBOL>..."`), and expose `GET /api/v1/yahoo/strategies/backtest/status` in `api_gateway/routes_yahoo.py`
- [X] T005 [US1] Render the Live Backtest Execution Progress Card (`data-testid="strategy-backtest-progress"`, `data-testid="strategy-progress-bar"`, `data-testid="strategy-elapsed-time"`) in `web/src/components/StrategyLifecycleWorkspace.tsx` while `isRunningBacktest` is `true`, with immediate initial state on click, `100ms` client-side elapsed timer, and `200ms` polling of `yahooApi.getBacktestStatus()`
- [X] T006 [P] [US1] Add unit test for `progress_callback` invocation sequence in `strategy_engine/tests/test_yahoo_backtester.py`
- [X] T007 [P] [US1] Add API route tests for `GET /api/v1/yahoo/strategies/backtest/status` (idle, running callback updates, completed, and failed states) in `api_gateway/tests/test_routes_yahoo.py`
- [X] T008 [P] [US1] Add unit test for `yahooApi.getBacktestStatus()` in `web/src/api/yahoo.test.ts`

---

## Phase 4: User Story 2 - Zero Black-Screen Crash Guarantee & Recoverable Workspace Error Boundary (Priority: P1)

**Goal**: Guarantee that `StrategyLifecycleWorkspace` and `App` never unmount into a black screen by adding null/NaN-safe formatters, defaulting initial ticker selection to tickers with `price_bars_count > 0`, displaying an explicit empty-chart overlay (`data-testid="strategy-chart-empty-overlay"`) when 0 bars are plotted, and wrapping workspaces in a recoverable React `ErrorBoundary`.

**Independent Test**: Render `StrategyLifecycleWorkspace` with zero-bar tickers, partial/missing metric fields, open positions, and simulated render errors; verify that fallback values (`$0.00`, `0.00%`, `Open`, `—`), the empty-chart overlay, and the `ErrorBoundary` recovery card (`data-testid="workspace-error-boundary"`) keep the application shell and `StatusRibbon` mounted.

### Implementation & Tests for User Story 2

- [X] T009 [P] [US2] Create reusable `ErrorBoundary` component (`data-testid="workspace-error-boundary"`, `data-testid="workspace-error-reset-btn"`) in `web/src/components/ErrorBoundary.tsx` and wrap workspace tabs in `web/src/App.tsx`
- [X] T010 [US2] Harden all numeric and date formatters (`formatNumber`, `formatCurrency`, `formatSignedPct`), prioritize tickers with `(price_bars_count ?? 0) > 0` for default `singleSymbol` and `batchSymbols`, and render `data-testid="strategy-chart-empty-overlay"` inside the chart container when no bars are plotted in `web/src/components/StrategyLifecycleWorkspace.tsx`
- [X] T011 [P] [US2] Add unit tests for `ErrorBoundary` error capture and reset recovery in `web/src/components/ErrorBoundary.test.tsx` and `web/src/App.test.tsx`
- [X] T012 [US2] Add component tests for live backtest progress bar, elapsed time counter, smart default ticker selection (`price_bars_count > 0`), empty-chart overlay (`NO_DATA`), and null-safe metric/trade rendering in `web/src/components/StrategyLifecycleWorkspace.test.tsx`

---

## Phase 5: User Story 3 - Fast Batch Backtest Execution & Clean Telemetry Proxy (Priority: P2)

**Goal**: Accelerate `DarwinTrendStrategy` multi-asset batch backtests via vectorized indicator precomputation (`_ema_fast`, `_ema_slow`, `_rsi`, `_atr`) and suppress benign client disconnect socket errors (`ECONNABORTED`, `ECONNRESET`, `EPIPE`) on the Vite `/ws` proxy.

**Independent Test**: Run `DarwinTrendStrategy` backtest with precomputed indicator columns in `strategy_engine/tests/test_yahoo_backtester.py` verifying 100% signal/PnL parity, and verify Vite config builds and lints cleanly.

### Implementation & Tests for User Story 3

- [X] T013 [P] [US3] Update `DarwinTrendStrategy.generate_signal()` in `strategy_engine/sample_strategy.py` and `run_single_asset_yahoo_backtest()` in `strategy_engine/yahoo_backtester.py` to precompute `_ema_fast`, `_ema_slow`, `_rsi`, and `_atr` once across the ticker DataFrame while preserving exact signal and SL/TP parity
- [X] T014 [P] [US3] Add `configure` socket error handler on the `/ws` proxy in `web/vite.config.ts` to suppress benign `ECONNABORTED`, `ECONNRESET`, and `EPIPE` errors when browser clients disconnect or reload
- [X] T015 [P] [US3] Add unit test verifying `DarwinTrendStrategy` precomputed indicator signal parity in `strategy_engine/tests/test_yahoo_backtester.py`

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final documentation, changelog, and full-suite verification

- [X] T016 Update `CHANGELOG.md` under `## [Unreleased]` and `.graph/architecture.md` to document live strategy backtest progress telemetry, `ErrorBoundary` crash protection, and vectorized `DarwinTrendStrategy` indicator precomputation
- [X] T017 Run full Python test suite (`pytest api_gateway/tests strategy_engine/tests tui/tests`) and Web verification suite (`npm test`, `npm run lint`, `npm run build` in `web/`) to confirm 100% green pass

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → **Phase 2 (Foundational: T002, T003)** → **Phase 3 (US1: T004–T008)** & **Phase 4 (US2: T009–T012)** & **Phase 5 (US3: T013–T015)** → **Phase 6 (Polish: T016–T017)**.
- Tasks marked `[P]` touch independent files and can be executed in parallel.
