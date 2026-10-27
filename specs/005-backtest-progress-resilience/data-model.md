# Data Model: Live Strategy Backtest Progress Telemetry & Black-Screen Crash Resilience

**Feature**: `005-backtest-progress-resilience`  
**Date**: 2026-10-27

## 1. Backend / API Models (`api_gateway/routes_yahoo.py` & `strategy_engine/yahoo_backtester.py`)

### `YahooBacktestProgressState` (In-Memory Telemetry Snapshot)

Protected by `_yahoo_lock` (`threading.Lock`) in `api_gateway/routes_yahoo.py`:

| Field | Type | Description |
|-------|------|-------------|
| `status` | `Literal["IDLE", "RUNNING", "COMPLETED", "FAILED"]` | Current lifecycle status of the strategy backtest engine. |
| `strategy_id` | `str` | Active or last executed strategy identifier (`"darwin_trend"` or `"darwinx_zero_trader"`). |
| `strategy_name` | `str` | Human-readable strategy name. |
| `timeframe` | `str` | Execution timeframe (`"D1"`, `"W1"`, `"MN1"`). |
| `total_symbols` | `int` | Total number of target Yahoo Finance symbols in the run (`>= 0`). |
| `completed_symbols` | `int` | Number of symbols completed so far (`0 <= completed_symbols <= total_symbols`). |
| `current_symbol` | `str` | Ticker symbol currently being evaluated (e.g. `"AAPL"`), or `""` when idle. |
| `progress_pct` | `float` | Completion percentage (`0.0` to `100.0`, rounded to 1 decimal place). |
| `elapsed_ms` | `int` | Elapsed wall-clock time in milliseconds since the backtest started. |
| `message` | `str` | Human-readable status string (e.g. `"Evaluating 14 / 50 tickers — AAPL..."` or `"Completed 50 / 50 tickers in 0.85s"`). |

### State Transitions (`_backtest_state`)

```text
IDLE ──(POST /api/v1/yahoo/strategies/backtest starts)──> RUNNING (completed=0..N-1, current_symbol=<SYM>)
  │                                                          │
  │                                                          ├──(All symbols evaluated)──> COMPLETED (completed=N, progress_pct=100.0)
  │                                                          └──(Validation / runtime error)──> FAILED (message=error detail)
```

---

## 2. Frontend TypeScript Interfaces (`web/src/api/yahoo.ts`)

```ts
export interface YahooBacktestStatusResponse {
  status: 'IDLE' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  strategy_id: string;
  strategy_name: string;
  timeframe: string;
  total_symbols: number;
  completed_symbols: number;
  current_symbol: string;
  progress_pct: number;
  elapsed_ms: number;
  message: string;
}
```

---

## 3. UI Component State (`web/src/components/ErrorBoundary.tsx`)

### `ErrorBoundaryProps` & `ErrorBoundaryState`

| Property | Type | Description |
|----------|------|-------------|
| `fallbackTitle` | `string` (optional) | Title shown in the recovery card if a child component throws during render. |
| `onReset` | `() => void` (optional) | Optional callback invoked when the operator clicks **Reset Workspace**. |
| `hasError` | `boolean` | Whether an uncaught error was trapped in the child subtree. |
| `errorMessage` | `string` | Extracted diagnostic error message displayed in the recovery alert. |
