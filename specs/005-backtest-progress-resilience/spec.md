# Feature Specification: Live Strategy Backtest Progress Telemetry & Black-Screen Crash Resilience

**Feature Branch**: `feat/005-backtest-progress-resilience`

**Created**: 2026-10-27

**Status**: Approved

**Input**: User description: "When I click on run strategy the screen goes black so I don't know if the app is doing something or not. Provide a live per-ticker progress bar (e.g., 'Evaluating 14 / 50 tickers — AAPL...'), elapsed time counter, and automatic fallback error boundary so the screen never goes black."

## Clarifications

### Session 2026-10-27

- Q: While fixing the black-screen crash, what level of execution feedback should be displayed when clicking "Run Backtest"? → A: Live per-ticker progress bar (e.g., "Evaluating 14 / 50 tickers — AAPL..."), elapsed time counter, and automatic fallback error boundary so the screen never goes black.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Live Per-Ticker Execution Progress & Elapsed Time Feedback (Priority: P1)

As a quantitative trader running a single-asset or multi-asset strategy backtest in the Strategy Lifecycle workspace, I need immediate, real-time visual feedback showing how many tickers have been evaluated, which ticker is currently being processed, an animated progress bar (`0%–100%`), and a live elapsed timer so that I always know the application is actively computing and how close the run is to completion.

**Why this priority**: Directly addresses the user's core pain point ("I don't know if the app is doing something or not") during both quick single-asset runs and multi-second sector/market batch backtests.

**Independent Test**: Can be fully tested by navigating to the **Strategy Lifecycle** tab, selecting single-asset or multi-asset mode, clicking **Run Backtest**, and verifying that an active execution progress card immediately appears in the results dashboard displaying the strategy name, timeframe, live ticker progress counter (`Evaluating X / Y tickers — <SYMBOL>...`), progress bar percentage, and elapsed time counter until the final results render.

**Acceptance Scenarios**:

1. **Given** the user is on the **Strategy Lifecycle** workspace and clicks **Run Backtest**, **When** the backtest calculation begins, **Then** the results dashboard immediately renders a high-contrast **Live Backtest Progress Banner/Card** (instead of a blank black area) showing the selected strategy, timeframe, elapsed timer (`0.0s` incrementing live), progress percentage (`0%–100%`), and ticker progress status (`Evaluating K / N tickers — <SYMBOL>...`).
2. **Given** a multi-asset or sector batch backtest is in flight across $N$ tickers, **When** the workspace polls or receives execution status updates from the backend, **Then** the completed ticker count, current ticker symbol, and progress bar width update dynamically as each ticker finishes evaluation.
3. **Given** a completed backtest is already displayed on screen, **When** the user modifies parameters and clicks **Run Backtest** again, **Then** the live progress banner appears cleanly at the top of the results dashboard without blanking out or unmounting the workspace until the new results replace the prior snapshot.

---

### User Story 2 - Zero Black-Screen Crash Guarantee & Recoverable Workspace Error Boundary (Priority: P1)

As a platform operator, I need the Strategy Lifecycle workspace and Web Dashboard to be protected against unexpected data payload variations, missing numeric fields, zero-bar tickers, and rendering errors so that clicking **Run Backtest** (or switching chart modes) never unmounts the application to a solid black screen or drops live telemetry connections.

**Why this priority**: Eliminates the catastrophic failure mode where an uncaught rendering exception unmounts the entire web application into an unresponsive black viewport and disconnects live telemetry.

**Independent Test**: Can be tested by feeding partial/edge-case backtest payloads (e.g., missing optional metrics, open mark-to-market trades with null exit dates, tickers with zero historical bars, or simulated render exceptions) into the Strategy Lifecycle workspace and verifying that the top navigation header and status ribbon remain intact while the workspace either formats fallback values safely or displays a recoverable error card with a **Reset / Retry** action.

**Acceptance Scenarios**:

1. **Given** a backtest response contains open positions (where `exit_date` and `exit_time` are empty/null), zero trades, or missing optional numeric fields, **When** the results dashboard renders KPI cards, chart markers, comparison rows, and the trade execution log, **Then** all numeric values and dates format safely with deterministic fallbacks (`$0.00`, `0.00%`, `Open`, `—`) without throwing any runtime `TypeError`.
2. **Given** an unexpected rendering exception occurs inside a workspace tab, **When** the workspace error boundary catches the error, **Then** the top-level **Status Ribbon**, **Header Navigation Tabs**, and live WebSocket connection remain mounted and operational, and the affected workspace renders a clear **Workspace Recovery Card** displaying the error message and a **Reset Workspace** button that restores normal operation in one click.
3. **Given** the Strategy Lifecycle workspace loads the initial ticker catalog where some tickers have zero stored price bars, **When** default single-asset and batch selections are initialized, **Then** the workspace automatically defaults to tickers that contain historical price bars (`price_bars_count > 0`) when available, and displays an explicit informational overlay inside the chart container whenever a selected result has zero price bars (`NO_DATA`) instead of showing an unexplained black box.

---

### User Story 3 - Fast Batch Backtest Execution & Clean Telemetry Proxy (Priority: P2)

As a portfolio strategist running `Darwin Trend ATR` or `DarwinX Zero Trader` across multi-ticker universes, I need indicator series to be precomputed once per ticker rather than recalculated on every historical bar, and WebSocket proxy disconnections on browser reload to be handled cleanly without console crash dumps.

**Why this priority**: Accelerates multi-asset backtest throughput by ~4x for `Darwin Trend ATR` so batch runs finish rapidly while keeping the terminal console free of spurious socket abort stack traces.

**Independent Test**: Can be tested by running a 20-ticker batch backtest with `Darwin Trend ATR` and verifying that per-bar evaluation uses precomputed EMA/RSI/ATR columns with identical trade signals and metrics in a fraction of the time.

**Acceptance Scenarios**:

1. **Given** a user runs `Darwin Trend ATR` across a multi-ticker batch, **When** the backtest engine evaluates each ticker's price history, **Then** the fast EMA, slow EMA, RSI, and ATR series are precomputed vectorially across the ticker's DataFrame prior to bar-by-bar simulation, producing identical trade entries, exits, and PnL metrics with significantly lower latency.
2. **Given** the Web Dashboard is running via the local dev server proxy, **When** a browser tab refreshes or closes an active `/ws/live` WebSocket connection, **Then** benign client-side socket close/abort events (`ECONNABORTED` / `ECONNRESET`) are handled gracefully without printing noisy unhandled stack traces in the terminal.

### Edge Cases

- **Ticker with zero historical price bars (`NO_DATA`)**: When the user runs a backtest on a ticker with 0 stored bars in the selected date range, the chart area displays an explicit overlay message (`No historical price bars available for <SYMBOL> in the selected period`) rather than an empty black canvas.
- **Instant single-asset backtest (< 250ms)**: Even when a single-asset backtest completes before the second status poll fires, the UI immediately shows the initial progress state (`Evaluating 1 / 1 tickers — <SYMBOL>...`, `0.0s`) on click and transitions smoothly to the rendered results upon response completion.
- **Malformed or partial API response**: All numeric formatters (`formatCurrency`, `formatSignedPct`, `formatNumber`) and string/date formatters guard against `null`, `undefined`, and `NaN` values so no missing field can ever trigger a render crash.
- **Concurrent backtest status queries during execution**: Progress status queries return the latest thread-safe snapshot (`RUNNING`, `completed_symbols`, `total_symbols`, `current_symbol`, `progress_pct`, `elapsed_ms`, `message`) while the backtest worker executes on a background thread.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose a live backtest status endpoint (`GET /api/v1/yahoo/strategies/backtest/status`) returning thread-safe execution telemetry: `status` (`IDLE`, `RUNNING`, `COMPLETED`, `FAILED`), `strategy_id`, `strategy_name`, `timeframe`, `total_symbols`, `completed_symbols`, `current_symbol`, `progress_pct` (`0.0` to `100.0`), `elapsed_ms`, and human-readable `message` (e.g., `"Evaluating 14 / 50 tickers — AAPL..."`).
- **FR-002**: Backtest execution engine (`run_yahoo_portfolio_backtest`) MUST invoke a progress callback before and after evaluating each target symbol so that `completed_symbols`, `current_symbol`, `progress_pct`, and `elapsed_ms` update in real time throughout single-asset and multi-asset runs.
- **FR-003**: While a strategy backtest is executing (`isRunningBacktest === true`), the Strategy Lifecycle workspace MUST render a prominent **Live Execution Progress Card** (`data-testid="strategy-backtest-progress"`) displaying:
  - Status headline and current ticker message (`Evaluating K / N tickers — <SYMBOL>...`)
  - Strategy name and timeframe badges
  - Animated progress bar (`data-testid="strategy-progress-bar"`) reflecting `progress_pct`
  - Live elapsed time counter (`data-testid="strategy-elapsed-time"`, updated every 100ms on the client and synchronized with backend telemetry)
- **FR-004**: When a backtest result has zero price bars or `NO_DATA` status on the active chart, the Strategy Lifecycle chart card MUST display a clear contextual empty-chart state (`data-testid="strategy-chart-empty-overlay"`) over the dark chart container explaining why no candles/equity curve are plotted.
- **FR-005**: When initializing default ticker selections in the Strategy Lifecycle workspace, the system MUST prioritize tickers that have stored price history (`price_bars_count > 0`) over zero-bar metadata stubs.
- **FR-006**: Every numeric and date/string formatting operation in `StrategyLifecycleWorkspace` MUST be null/undefined/NaN-safe (`formatNumber`, `formatCurrency`, `formatSignedPct`, safe date fallback), and the workspace MUST be wrapped in a reusable `ErrorBoundary` component (`data-testid="workspace-error-boundary"`) that prevents any child rendering error from unmounting the application root (`App`) or disconnecting the top-level status ribbon.
- **FR-007**: `DarwinTrendStrategy` and `run_single_asset_yahoo_backtest` MUST support precomputing fast EMA, slow EMA, RSI, and ATR series once per ticker DataFrame (matching `DarwinXZeroTraderStrategy`'s precomputed MA optimization) to accelerate multi-asset batch backtesting while preserving 100% identical signal and PnL semantics.
- **FR-008**: The development proxy for `/ws` MUST attach socket error handlers so benign client disconnect/abort events (`ECONNABORTED`, `ECONNRESET`, `EPIPE`) do not emit raw Node.js stack traces to the operator terminal.

### Key Entities

- **YahooBacktestProgressStatus**: Real-time state snapshot of the active or most recent strategy backtest run (`status`, `strategy_id`, `strategy_name`, `timeframe`, `total_symbols`, `completed_symbols`, `current_symbol`, `progress_pct`, `elapsed_ms`, `message`).
- **WorkspaceErrorBoundaryState**: Recoverable UI boundary state capturing any unexpected child render error (`hasError`, `errorMessage`) and exposing a one-click reset callback without tearing down global app navigation or live telemetry.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0% of backtest executions—including zero-bar tickers, open mark-to-market positions, multi-asset sector batches, and malformed/partial payloads—result in an unmounted black screen.
- **SC-002**: Within 100ms of clicking **Run Backtest**, users see an active visual progress card with a live elapsed timer and ticker counter (`Evaluating K / N tickers...`) that updates continuously until results render.
- **SC-003**: Multi-asset batch backtest execution time for `Darwin Trend ATR` improves by at least 3x on a 20-ticker universe through vectorized indicator precomputation while maintaining 100% signal parity.
- **SC-004**: 100% of Python (`pytest`) and Web (`vitest`, `eslint`, `tsc -b`, `vite build`) test suites pass with zero errors.

## Assumptions

- Strategy backtests in the Web UI are initiated by a single interactive operator session against the local FastAPI Gateway (`127.0.0.1:8000`), so a module-level thread-safe `_backtest_state` dictionary protected by `_yahoo_lock` accurately reflects the active backtest run.
- Because `execute_yahoo_strategy_backtest` is declared as a standard synchronous `def` endpoint in FastAPI, Uvicorn executes it in the worker threadpool, allowing concurrent `GET /api/v1/yahoo/strategies/backtest/status` polling requests to be served immediately without event-loop blocking.
