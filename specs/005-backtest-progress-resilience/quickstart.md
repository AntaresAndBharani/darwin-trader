# Quickstart & Verification Guide: Live Strategy Backtest Progress & Crash Resilience

**Feature**: `005-backtest-progress-resilience`

## 1. Run Automated Backend & Frontend Verification

```powershell
# 1. Run Python unit & integration tests (Gateway, Strategy Engine, TUI)
pytest api_gateway/tests strategy_engine/tests tui/tests

# 2. Run Web UI unit tests, ESLint, and TypeScript production build
Set-Location web
npm test
npm run lint
npm run build
```

## 2. Interactive End-to-End Verification

1. Launch the Web Dashboard:
   ```powershell
   .\scripts\run-web.ps1
   ```
2. Open `http://localhost:5173` and click the **Strategy Lifecycle** tab in the top navigation bar.
3. Verify that the default selected ticker in **Single Asset** mode is automatically pre-populated with a ticker that has historical price bars (`price_bars_count > 0`), and that the chart card shows a clear instructional overlay before the first run rather than an unexplained black box.
4. Click **Run Backtest** in **Single Asset** mode or switch to **Multi-Asset / Sector** mode, click **Select Filtered**, and click **Run Backtest**:
   - Verify the **Live Backtest Progress Card** (`Evaluating K / N tickers — <SYMBOL>...`) appears immediately with an animated progress bar and live elapsed timer (`0.1s`, `0.2s`, ...).
   - Verify that upon completion, all KPI cards, the Mark-to-Market Equity Curve / Price Chart with trade markers, the Asset Performance Comparison table, and the Trade Execution Log render cleanly without unmounting the screen.
