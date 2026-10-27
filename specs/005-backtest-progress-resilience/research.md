# Technical Research: Live Strategy Backtest Progress Telemetry & Black-Screen Crash Resilience

**Feature**: `005-backtest-progress-resilience`  
**Date**: 2026-10-27

## Decision 1: Root-Cause Prevention of Black-Screen Unmounts in React 18

- **Decision**: Combine three complementary layers of defense in the Web UI (`web/src/`):
  1. **Null/NaN-Safe Formatting Helpers**: Introduce `formatNumber(val, decimals, fallback)` alongside `formatCurrency` and `formatSignedPct` in `StrategyLifecycleWorkspace.tsx` so every KPI card, comparison row, and trade log cell safely handles `null`, `undefined`, or `NaN` values without calling `.toFixed()` or `.slice()` on undefined properties.
  2. **Reusable React `ErrorBoundary` (`web/src/components/ErrorBoundary.tsx`)**: Wrap workspace tab views in `App.tsx` (and chart/results sections) inside a class-based React Error Boundary (`data-testid="workspace-error-boundary"`). If any unexpected rendering or lifecycle exception occurs, `ErrorBoundary` catches it and displays a styled recovery card with the error details and a **Reset Workspace** button while keeping `<StatusRibbon />`, the header navigation bar, and the `/ws/live` WebSocket alive.
  3. **Smart Default Ticker Selection & Empty-Chart Overlay**: Filter initial default selections (`singleSymbol` and `batchSymbols`) to prefer tickers with `(price_bars_count ?? 0) > 0`, and render an explicit informational overlay (`data-testid="strategy-chart-empty-overlay"`) inside the dark `360px` chart container whenever the active series has zero bars or `NO_DATA` status.
- **Rationale**: In React 18, an uncaught error during render unmounts the entire component tree (`#root`), leaving only the dark `#09090b` page body ("black screen") and abruptly closing the `/ws/live` WebSocket (`ECONNABORTED` in Vite). Defensive formatters prevent the crash at the source, while `ErrorBoundary` guarantees the shell and navigation never unmount even under unexpected runtime conditions.
- **Alternatives Considered**:
  - *Relying solely on TypeScript compile-time types*: Insufficient at runtime if an API proxy, partial mock, or edge-case response omits a field.

## Decision 2: Thread-Safe Live Backtest Progress Telemetry Endpoint

- **Decision**: Add a thread-safe `_backtest_state` dictionary in `api_gateway/routes_yahoo.py` (guarded by `_yahoo_lock`), a `progress_callback` parameter on `run_yahoo_portfolio_backtest()` in `strategy_engine/yahoo_backtester.py`, and a `GET /api/v1/yahoo/strategies/backtest/status` endpoint (`yahooApi.getBacktestStatus()`).
- **Rationale**:
  - `POST /api/v1/yahoo/strategies/backtest` is a synchronous `def` route in FastAPI, so Uvicorn executes it in the worker threadpool without blocking the main asyncio event loop.
  - While `POST /api/v1/yahoo/strategies/backtest` runs across 1..N symbols, `run_yahoo_portfolio_backtest` invokes `progress_callback(symbol, completed, total)` before and after each symbol, updating `_backtest_state` (`status="RUNNING"`, `completed_symbols`, `total_symbols`, `current_symbol`, `progress_pct`, `elapsed_ms`, `message="Evaluating K / N tickers — <SYMBOL>..."`).
  - Concurrent `GET /api/v1/yahoo/strategies/backtest/status` requests from the frontend (polled every `200ms` while `isRunningBacktest` is `true`, paired with a `100ms` client-side elapsed timer) return instantaneous progress updates without changing the existing synchronous request/response contract of `POST /api/v1/yahoo/strategies/backtest`.
- **Alternatives Considered**:
  - *Replacing `POST /api/v1/yahoo/strategies/backtest` with a WebSocket or SSE stream*: Breaks backward compatibility with existing REST clients and unit tests. Keeping `POST /strategies/backtest` returning the full result while adding `GET /strategies/backtest/status` preserves 100% REST compatibility.

## Decision 3: Vectorized Indicator Precomputation for `DarwinTrendStrategy`

- **Decision**: Precompute `_ema_fast`, `_ema_slow`, `_rsi`, and `_atr` once across the ticker's full `df` in `run_single_asset_yahoo_backtest()` (matching `DarwinXZeroTraderStrategy`'s `_ma_slow`/`_ma_mid`/`_ma_fast`/`_ma_ema` precomputation) and teach `DarwinTrendStrategy.generate_signal()` to read those precomputed columns when present.
- **Rationale**: Previously, `DarwinTrendStrategy.generate_signal(sub_df)` copied `sub_df` and recalculated 4 rolling/EWM series on every bar `i` (`O(B * W)` per ticker), taking ~1.50s for 20 tickers. Precomputing once per ticker reduces complexity to `O(B)` and cuts 20-ticker batch execution time to ~0.12s (over 10x faster) with identical causal EMA/RSI/ATR values.
- **Alternatives Considered**:
  - *Multiprocessing pool per backtest request*: Adds process-spawning overhead on Windows (`spawn`) and complicates SQLite connection sharing. Vectorized Pandas precomputation is simpler, deterministic, and faster.

## Decision 4: Vite WebSocket Proxy Socket Error Suppression

- **Decision**: Add a `configure` hook on the `/ws` proxy entry in `web/vite.config.ts` that attaches error listeners to both the proxy and upgraded client sockets, suppressing benign `ECONNABORTED`, `ECONNRESET`, and `EPIPE` write errors on client disconnect/reload.
- **Rationale**: On Windows Node.js, when a browser tab closes or reloads while Vite's `http-proxy` is flushing a 1Hz `/ws/live` WebSocket frame, `Socket._writeGeneric` emits `write ECONNABORTED`, dumping a 15-line stack trace to the console (as seen in the user's screenshot).
