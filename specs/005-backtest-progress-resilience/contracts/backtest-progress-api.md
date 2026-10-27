# API & UI Contracts: Live Strategy Backtest Progress Telemetry

**Feature**: `005-backtest-progress-resilience`  
**Base Prefix**: `/api/v1/yahoo`

## 1. `GET /api/v1/yahoo/strategies/backtest/status`

Returns the real-time progress snapshot of the currently running (or most recently finished) Yahoo Finance strategy backtest.

### Response `200 OK` (While Running)

```json
{
  "status": "RUNNING",
  "strategy_id": "darwin_trend",
  "strategy_name": "Darwin Trend ATR",
  "timeframe": "D1",
  "total_symbols": 50,
  "completed_symbols": 13,
  "current_symbol": "AAPL",
  "progress_pct": 26.0,
  "elapsed_ms": 420,
  "message": "Evaluating 14 / 50 tickers — AAPL..."
}
```

### Response `200 OK` (Completed)

```json
{
  "status": "COMPLETED",
  "strategy_id": "darwin_trend",
  "strategy_name": "Darwin Trend ATR",
  "timeframe": "D1",
  "total_symbols": 50,
  "completed_symbols": 50,
  "current_symbol": "MSFT",
  "progress_pct": 100.0,
  "elapsed_ms": 1150,
  "message": "Completed 50 / 50 tickers"
}
```

---

## 2. Web UI Test IDs & Visual Contracts

| `data-testid` | Component | Contract |
|---------------|-----------|----------|
| `strategy-backtest-progress` | `StrategyLifecycleWorkspace` | Visible whenever `isRunningBacktest === true`; displays live ticker counter, current symbol, strategy badge, progress bar, and elapsed timer. |
| `strategy-progress-bar` | `StrategyLifecycleWorkspace` | Inner progress fill bar with `style={{ width: '${progressPct}%' }}` and `aria-valuenow`. |
| `strategy-elapsed-time` | `StrategyLifecycleWorkspace` | Live elapsed time badge formatted in seconds (e.g., `0.4s`). |
| `strategy-chart-empty-overlay` | `StrategyLifecycleWorkspace` | Informational overlay inside the `360px` chart container when no backtest has run yet, while a first backtest is in flight, or when the active asset has `0` price bars (`NO_DATA`). |
| `workspace-error-boundary` | `ErrorBoundary` | Recovery card rendered if a child component throws during render, providing `workspace-error-reset-btn` to recover without unmounting `<App />`. |
