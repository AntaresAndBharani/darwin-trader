# Quickstart Validation Guide: Yahoo Finance Strategy Lifecycle & Backtesting Control Panel

## Prerequisites
- Python 3.11+ with project dependencies installed (`pip install -r strategy_engine/requirements.txt -r api_gateway/requirements.txt`).
- Node.js 20+ with Web dependencies installed (`cd web && npm install`).
- Local Yahoo Finance database `data/yahoo_finance.db` (automatically initialized by `YahooFinanceDB`).

## 1. Run Backend Unit & API Integration Tests
```powershell
pytest api_gateway/tests strategy_engine/tests tui/tests -v
```
Expected: 100% passing tests covering:
- `GET /api/v1/yahoo/strategies` catalog and parameter schemas.
- `POST /api/v1/yahoo/strategies/backtest` single-asset and multi-asset batch backtesting on `YahooFinanceDB`.
- Custom strategy parameters for `darwin_trend` and `darwinx_zero_trader` (including zero-lookahead Weekly Heikin-Ashi alignment).
- Mark-to-market accounting invariant (`final_equity == initial_balance + realized_pnl + unrealized_pnl`).
- Strict isolation from Darwinex Zero MT5 (`routes_strategy.py` and `historical_rates.db`).

## 2. Run Web Frontend Unit Tests, Linter & Production Build
```powershell
cd web
npm test -- --run
npm run lint
npm run build
```
Expected: All Vitest component tests (including `StrategyLifecycleWorkspace.test.tsx` and `App.test.tsx`), ESLint checks, and TypeScript production build succeed with zero errors.

## 3. Launch Full-Stack Web Application
```powershell
powershell .\scripts\run-web.ps1
```
1. Open the browser at `http://localhost:5173`.
2. Verify the top header navigation displays three tabs: **Darwinex MT5**, **Yahoo Finance**, and **Strategy Lifecycle**, and the legacy small `StrategySidebar` card is gone from **Darwinex MT5**.
3. Click **Strategy Lifecycle** to open the full-screen Strategy Control Panel.
4. Select a Yahoo Finance ticker (or switch to Multi-Asset Batch mode), pick **Darwin Trend ATR** or **DarwinX Zero Trader**, adjust parameters, and click **Run Backtest**.
5. Inspect the KPI Summary Cards, toggle the chart between **Equity Curve** and **Price & Trade Markers**, click rows in the Multi-Asset Comparison Table to drill down, and inspect the Trade Execution Log.
