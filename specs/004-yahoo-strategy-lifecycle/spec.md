# Feature Specification: Yahoo Finance Strategy Lifecycle & Backtesting Control Panel

**Feature Branch**: `feat/004-yahoo-strategy-lifecycle`

**Created**: 2026-10-23

**Status**: Approved

**Input**: User description: "Develop the Yahoo Finance strategy lifecycle functionality as a dedicated full-screen workspace in the Web UI. Run registered strategies (Darwin Trend ATR and DarwinX Zero Trader) exclusively against Yahoo Finance data (never Darwinex Zero MT5 data), with a full control panel to switch or batch-select assets, configure strategy and simulation parameters, run on-demand historical backtests, and inspect institutional KPIs, interactive equity/price charts with trade markers, multi-asset comparison tables, and detailed trade logs."

## Clarifications

### Session 2026-10-23

- Q: When you run a strategy on Yahoo Finance data in the new full-screen Strategy Lifecycle panel, how should the execution and lifecycle controls behave? → A: On-demand Historical Backtest only: Replace Start / Pause / Stop with a "Run Backtest" button that evaluates the strategy over a date range and displays performance results and trades.
- Q: How should the full-screen Strategy Control Panel be navigated to in the Web UI (`App.tsx`)? → A: Add a dedicated top-level "Strategy Lifecycle" full-screen tab in the header navigation (alongside "Darwinex MT5" and "Yahoo Finance") and remove the small bottom-right Strategy Lifecycle sidebar card from the main dashboard.
- Q: Which strategies should be available in the Yahoo Finance Strategy Control Panel? → A: Both registered strategies in `STRATEGY_REGISTRY`: "Darwin Trend ATR" (EMA Crossover + RSI + ATR SL/TP) and "DarwinX Zero Trader" (Weekly Heikin-Ashi + Quad-MA Stack + 3-Stage Position Lifecycle), adapted to run on Yahoo Finance `D1`/`W1`/`MN1` data.
- Q: How should asset selection work in the Strategy Control Panel? → A: Support both single-asset mode and multi-asset batch backtesting (e.g., running a strategy across multiple selected Yahoo tickers or a whole sector/market at once).
- Q: Which parameters should be editable in the Strategy Control Panel when configuring a run? → A: Dynamic parameter form: shared simulation settings (Timeframe `D1`/`W1`/`MN1`, From/To Date, Initial Balance, Capital/Risk % per trade) plus strategy-specific inputs (EMA/RSI/ATR params for Darwin Trend; Quad-MA periods and SL/TP1/Partial % for DarwinX Zero Trader), with a "Reset to Defaults" button.
- Q: What result visualizations and tables should be rendered in the full-screen Strategy Lifecycle view after running a strategy? → A: Full institutional results dashboard: (1) KPI Summary Cards (Net Profit $ & %, Realized/Unrealized PnL, Win Rate, Profit Factor, Max Drawdown, Sharpe, Latest Signal), (2) Interactive Chart with toggle between Equity Curve and Price Chart with Buy/Sell markers, (3) Multi-Asset Comparison Table (clickable to drill into any asset), and (4) Detailed Trade Execution Log.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Single-Asset Strategy Backtesting & Parameter Tuning on Yahoo Finance Data (Priority: P1)

As a quantitative trader, I need a dedicated full-screen Strategy Lifecycle workspace where I can select any Yahoo Finance instrument, choose between registered quantitative strategies (`Darwin Trend ATR` and `DarwinX Zero Trader`), customize simulation and indicator parameters, and run an on-demand historical backtest exclusively against Yahoo Finance data so that I can evaluate strategy profitability, risk metrics, and current trade signals before deploying capital.

**Why this priority**: This is the foundational user flow—evaluating a strategy with custom parameters on a Yahoo Finance asset and inspecting its complete financial performance, chart markers, and trade log.

**Independent Test**: Can be fully tested by navigating to the **Strategy Lifecycle** tab, selecting a Yahoo Finance ticker (e.g., `AAPL`), picking `Darwin Trend ATR` or `DarwinX Zero Trader`, adjusting indicator parameters, clicking **Run Backtest**, and verifying that KPIs, the interactive chart, and the trade log render accurately from Yahoo Finance data without touching Darwinex Zero MT5 state.

**Acceptance Scenarios**:

1. **Given** historical Yahoo Finance price bars exist for a selected ticker, **When** the user selects `Darwin Trend ATR`, sets custom EMA/RSI/ATR parameters, date range, and initial balance, and clicks **Run Backtest**, **Then** the system executes the strategy exclusively against Yahoo Finance data and displays Net Profit ($ and %), Realized PnL ($ and %), Unrealized PnL ($ and %), Final Equity, Win Rate %, Profit Factor, Max Drawdown ($ and %), Sharpe Ratio, and the Latest Bar Signal (`ENTER_LONG`, `ENTER_SHORT`, or `HOLD` with diagnostic reason).
2. **Given** historical Yahoo Finance daily price bars exist for a selected ticker, **When** the user selects `DarwinX Zero Trader` and adjusts Quad-MA periods (`21 EMA`, `50 SMA`, `100 SMA`, `200 SMA`) or stage parameters (`Stop Loss %`, `Partial TP1 %`, `Partial Exit Fraction`), **Then** the system aligns prior closed Weekly Heikin-Ashi candles (`W-2 RED`, `W-1 GREEN`) with zero lookahead bias, evaluates the 3-stage position lifecycle (`FULL` -> `PARTIAL` -> `CLOSED`), and reports all executed trades and mark-to-market metrics.
3. **Given** the user has modified strategy or simulation parameters in the control panel, **When** the user clicks **Reset to Defaults**, **Then** all shared simulation fields and active strategy parameters immediately revert to their canonical default values.

---

### User Story 2 - Multi-Asset & Sector Batch Backtesting with Drill-Down Comparison (Priority: P2)

As a portfolio strategist, I need to run a strategy across multiple selected Yahoo Finance tickers—or an entire filtered Market/Sector—simultaneously and compare per-asset results alongside an aggregated portfolio summary so that I can identify which instruments and sectors perform best under a given strategy configuration.

**Why this priority**: Builds upon the single-asset backtesting engine to enable rapid cross-sectional screening and portfolio-level validation across the Yahoo Finance universe.

**Independent Test**: Can be fully tested by switching the control panel to Multi-Asset / Batch mode (or selecting multiple tickers / a sector filter), clicking **Run Backtest**, verifying the Portfolio Summary KPIs and Multi-Asset Comparison Table, and clicking any asset row in the comparison table to drill down into that asset's individual chart and trade log.

**Acceptance Scenarios**:

1. **Given** the user selects multiple Yahoo Finance tickers (or applies a Market/Sector filter and selects all matching tickers), **When** the user clicks **Run Backtest**, **Then** the system allocates capital equally across valid symbols, computes a forward-filled mark-to-market portfolio equity curve, displays aggregated portfolio KPIs, and populates the Multi-Asset Comparison Table with each symbol's Trades, Win Rate %, Net Profit ($ and %), Realized/Unrealized PnL, Max Drawdown %, and Latest Signal.
2. **Given** a completed multi-asset backtest displaying the Multi-Asset Comparison Table, **When** the user clicks on any ticker row in the comparison table, **Then** the interactive chart and Trade Execution Log immediately update to show that specific ticker's price/equity curve, trade markers, and trade history.
3. **Given** a multi-asset selection where one or more tickers have zero price bars in the requested date range, **When** the backtest runs, **Then** the system gracefully marks those tickers as `NO_DATA` in the breakdown table without failing the batch run and computes portfolio metrics across the remaining valid tickers.

---

### User Story 3 - Full-Screen Workspace Navigation & Interactive Chart Mode Switching (Priority: P3)

As a platform operator, I need a clean top-level **Strategy Lifecycle** tab in the Web Dashboard header (with the legacy small Strategy Lifecycle sidebar card removed from the Darwinex MT5 tab) and an interactive chart that toggles seamlessly between the **Equity Curve** and the **Price Candlestick Chart with Buy/Sell/Exit Markers** so that I can visually audit trade timing and drawdown behavior in full screen.

**Why this priority**: Completes the full-screen visual experience and top-level workspace organization requested by the user.

**Independent Test**: Can be fully tested by launching the Web UI, verifying that the Darwinex MT5 tab no longer shows the small bottom-right Strategy Lifecycle card, switching to the top-level **Strategy Lifecycle** tab, running a backtest, and toggling the chart view between **Equity Curve** and **Price & Trade Markers**.

**Acceptance Scenarios**:

1. **Given** the Web Dashboard is loaded, **When** the user views the **Darwinex MT5** tab, **Then** the legacy bottom-right `StrategySidebar` card is absent and the `PositionsGrid` occupies the full width, while the header navigation displays three top-level tabs: **Darwinex MT5**, **Yahoo Finance**, and **Strategy Lifecycle**.
2. **Given** a completed backtest in the **Strategy Lifecycle** tab, **When** the user toggles the chart mode between **Equity Curve** and **Price & Trade Markers**, **Then** the chart switches between the mark-to-market equity time series and the OHLCV candlestick chart annotated with entry/exit trade markers and indicator overlays.

### Edge Cases

- **Insufficient warm-up bars before `from_date`**: The system automatically loads available pre-range bars from the Yahoo Finance store to warm up moving averages, RSI, ATR, and Weekly Heikin-Ashi indicators so trading and equity tracking start strictly on or after `from_date` without consuming in-range bars.
- **Zero executed trades in date window**: If strategy conditions are never triggered during the selected period, all ratio metrics (`Win Rate`, `Profit Factor`, `Sharpe Ratio`) return `0.0` (never `NaN`, `Infinity`, or division-by-zero errors), Net Profit reports `$0.00 (0.00%)`, and the trade log displays a clean `"No trades executed in the selected period"` state.
- **Open position at the end of the backtest window**: Any position still open on the final bar is marked to market at the final bar's close price, with its unrealized gain/loss reported separately in `Unrealized PnL ($ and %)` and included in `Final Equity` and `Total Net Profit ($ and %)`.
- **Inverted date range or invalid parameter bounds**: If `from_date > to_date`, `fast_ema_period >= slow_ema_period`, `rsi_oversold >= rsi_overbought`, or `initial_balance <= 0`, the system returns a clear validation error (`400 Bad Request` / inline UI alert) before running the calculation.
- **Strict data-provider isolation**: Running any strategy or modifying any parameter in the Strategy Lifecycle workspace never modifies `global_config` in the Darwinex MT5 live connector (`routes_strategy.py`) and never reads from `data/historical_rates.db`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a catalog endpoint (`GET /api/v1/yahoo/strategies`) returning all registered Yahoo Finance-compatible strategies (`darwin_trend` and `darwinx_zero_trader`), their human-readable names, descriptions, and typed parameter schemas with default values and validation bounds.
- **FR-002**: System MUST provide an on-demand backtest execution endpoint (`POST /api/v1/yahoo/strategies/backtest`) that executes a selected strategy over one or more Yahoo Finance tickers from `YahooFinanceDB` (`data/yahoo_finance.db`) across `D1`, `W1`, or `MN1` timeframes within an optional `from_date` and `to_date` range.
- **FR-003**: System MUST support dynamic parameter overrides per backtest request:
  - Shared simulation parameters: `symbols` (1..N or sector/market filter), `timeframe` (`D1`, `W1`, `MN1`), `from_date`, `to_date` (defaulting to latest available date / today), `initial_balance` (default `100000.0`), and `risk_per_trade_pct` (default `10.0%` capital allocation per position or strategy sizing).
  - `darwin_trend` parameters: `fast_ema_period` (default `12`), `slow_ema_period` (default `26`), `rsi_period` (default `14`), `rsi_overbought` (default `70.0`), `rsi_oversold` (default `30.0`), `atr_period` (default `14`), `atr_multiplier` (default `2.0`).
  - `darwinx_zero_trader` parameters: `ema_period` (default `21`), `sma_fast_period` (default `50`), `sma_mid_period` (default `100`), `sma_slow_period` (default `200`), `stop_loss_pct` (default `10.0`), `partial_tp_pct` (default `5.0`), `partial_fraction` (default `0.5`).
- **FR-004**: When executing `darwinx_zero_trader` on Yahoo Finance data, the engine MUST deterministically compute Weekly (`W1`) Heikin-Ashi candles from the ticker's daily Yahoo Finance bars and align the prior two closed weekly candle colors (`w1_ha_color_prev1`, `w1_ha_color_prev2`) onto each execution bar with zero lookahead bias.
- **FR-005**: The backtesting engine MUST compute mark-to-market (MTM) equity on every bar (`balance + unrealized_pnl`) and return comprehensive per-asset and portfolio metrics: `initial_balance`, `final_equity`, `net_profit`, `net_profit_pct`, `realized_pnl`, `realized_pnl_pct`, `unrealized_pnl`, `unrealized_pnl_pct`, `total_trades`, `winning_trades`, `losing_trades`, `win_rate_pct`, `profit_factor`, `max_drawdown`, `max_drawdown_pct`, `sharpe_ratio`, `latest_signal`, `latest_signal_reason`, `equity_curve` (date-indexed points), `price_bars` (with trade markers), and `trades` (detailed execution records).
- **FR-006**: In multi-asset batch mode ($N > 1$ symbols), the engine MUST allocate `initial_balance / N` across each valid symbol, align per-symbol MTM equity curves across the sorted union of dates using forward-fill (`ffill`) and initial-capital seeding (`fillna(capital_k)`), and return both the aggregated portfolio summary and the per-symbol comparison breakdown.
- **FR-007**: Web Dashboard (`App.tsx`) MUST expose three top-level workspace tabs—**Darwinex MT5**, **Yahoo Finance**, and **Strategy Lifecycle**—and MUST remove the legacy `StrategySidebar` component from the **Darwinex MT5** tab.
- **FR-008**: Web Dashboard MUST provide a full-screen `StrategyLifecycleWorkspace` component containing:
  - Asset Selection Control (Single-Ticker searchable selector and Multi-Asset / Sector batch selector sourced from Yahoo Finance tickers).
  - Strategy Selector (`Darwin Trend ATR` vs `DarwinX Zero Trader`) and Dynamic Parameter Form with **Reset to Defaults** and **Run Backtest** actions.
  - KPI Summary Ribbon/Cards showing Net Profit ($ and %), Realized PnL ($ and %), Unrealized PnL ($ and %), Final Equity, Win Rate %, Profit Factor, Max Drawdown ($ and %), Sharpe Ratio, and Latest Signal badge.
  - Interactive Chart (`lightweight-charts`) supporting toggle between **Equity Curve** and **Price Chart with Trade Entry/Exit Markers**.
  - Multi-Asset Comparison Table (sortable, clickable rows to inspect individual asset charts/logs) and Detailed Trade Execution Log Table.

### Key Entities

- **YahooStrategyDefinition**: Metadata and parameter schema for a registered strategy (`id`, `name`, `description`, `default_timeframe`, `parameters`).
- **YahooBacktestRequest**: Payload specifying `strategy_id`, `symbols` (or `market`/`sector` filter), `timeframe`, `from_date`, `to_date`, `initial_balance`, `risk_per_trade_pct`, and `strategy_params`.
- **YahooAssetBacktestResult**: Complete single-asset backtest output (`symbol`, `name`, `market`, `sector`, `status`, `bars_count`, KPI metrics, `latest_signal`, `latest_signal_reason`, `equity_curve`, `bars`, `trades`).
- **YahooPortfolioBacktestResponse**: Top-level response containing `strategy_id`, `timeframe`, `from_date`, `to_date`, aggregated `portfolio_summary` KPIs, `portfolio_equity_curve`, and `asset_results` list.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can select a Yahoo Finance ticker, customize strategy parameters, and execute a multi-year daily (`D1`) or weekly (`W1`) backtest in under 500 milliseconds for a single asset and under 3 seconds for a 25-asset sector batch.
- **SC-002**: 100% of backtest executions run strictly against `data/yahoo_finance.db` with zero side effects on Darwinex Zero MT5 connection state, live strategy status, or `data/historical_rates.db`.
- **SC-003**: Every backtest result satisfies strict accounting invariants: `final_equity == initial_balance + realized_pnl + unrealized_pnl` and `net_profit == realized_pnl + unrealized_pnl` (within `$0.01` floating-point rounding), with zero `NaN` or `Infinity` values in any serialized JSON response.
- **SC-004**: All automated Python unit/API tests (`pytest`) and Web UI component tests (`vitest`, `eslint`, `tsc -b`) pass at 100%.

## Assumptions

- The Yahoo Finance SQLite database (`data/yahoo_finance.db`) and `/api/v1/yahoo` router from the Yahoo Finance integration branch (`feat/002-yahoo-finance-workspace`) serve as the underlying data store for all tickers and daily OHLCV bars.
- All Yahoo Finance backtest metrics are denominated in the instrument's quoted currency normalized to the user's configured starting capital (`initial_balance`, default `$100,000.00`), using percentage capital allocation (`risk_per_trade_pct`) to size positions consistently across stocks, ETFs, indices, and forex pairs regardless of nominal share price.
- The Textual TUI (`tui/`) remains dedicated to Darwinex MT5 operations and is out of scope for this Web UI workspace feature.
