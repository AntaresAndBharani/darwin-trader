# Phase 1 Data Model: Yahoo Finance Strategy Lifecycle & Backtesting Control Panel

## 1. Strategy Catalog Models

### `StrategyParameterSpec`
Describes a single configurable parameter for a strategy.
- `key: str` — Parameter field identifier (e.g., `"fast_ema_period"`, `"sma_slow_period"`).
- `label: str` — Human-readable label (e.g., `"Fast EMA Period"`).
- `type: Literal["int", "float"]` — Numeric input type.
- `default: float | int` — Canonical default value.
- `min_value: float | int` — Minimum allowed value.
- `max_value: float | int` — Maximum allowed value.
- `step: float | int` — UI increment step.
- `description: str` — Tooltip/help text explaining the parameter's effect.

### `YahooStrategyDefinition`
Describes a registered strategy exposed by `GET /api/v1/yahoo/strategies`.
- `id: str` — Registry key (`"darwin_trend"` or `"darwinx_zero_trader"`).
- `name: str` — Display name (`"Darwin Trend ATR"` or `"DarwinX Zero Trader"`).
- `description: str` — Concise quantitative summary of entry/exit rules.
- `supported_timeframes: list[str]` — `["D1", "W1", "MN1"]`.
- `default_timeframe: str` — `"D1"`.
- `parameters: list[StrategyParameterSpec]` — Ordered list of editable strategy parameters.

---

## 2. Backtest Execution Request & Response Models

### `YahooBacktestRequest`
Payload accepted by `POST /api/v1/yahoo/strategies/backtest`.
- `strategy_id: str` — Must be a valid registered strategy ID (`"darwin_trend"` or `"darwinx_zero_trader"`).
- `symbols: list[str]` — Explicit list of Yahoo Finance ticker symbols (1..N). Optional if `market` or `sector` filter is used.
- `market: Optional[str]` — Optional market filter for batch selection.
- `sector: Optional[str]` — Optional sector filter for batch selection.
- `timeframe: Literal["D1", "W1", "MN1"]` — Default `"D1"`.
- `from_date: Optional[str]` — Start date `YYYY-MM-DD` (inclusive). Defaults to 2 years prior to latest available date if omitted.
- `to_date: Optional[str]` — End date `YYYY-MM-DD` (inclusive). Defaults to today / latest available date.
- `initial_balance: float` — Starting capital in USD (default `100000.0`, must be `> 0`).
- `risk_per_trade_pct: float` — Capital allocation % per trade (default `10.0`, bounds `0.5` to `100.0`).
- `strategy_params: dict[str, float | int]` — Strategy-specific parameter overrides.

### `YahooTradeRecord`
Represents a single executed trade or partial scale-out event.
- `symbol: str`
- `type: Literal["BUY", "SELL"]`
- `stage: Literal["FULL", "PARTIAL", "CLOSED"]`
- `entry_date: str` (`YYYY-MM-DD`)
- `entry_time: int` (UTC epoch seconds)
- `entry_price: float`
- `exit_date: Optional[str]` (`YYYY-MM-DD` or `None` if open at end of period)
- `exit_time: Optional[int]`
- `exit_price: float`
- `units: float`
- `pnl: float`
- `pnl_pct: float`
- `balance_after: float`
- `reason: str`

### `YahooEquityPoint`
- `time: int` (UTC epoch seconds)
- `date: str` (`YYYY-MM-DD`)
- `equity: float` (Mark-to-market equity)
- `balance: float` (Realized cash balance)
- `drawdown_pct: float` (Underwater drawdown percentage $\le 0$)

### `YahooBacktestSummaryMetrics`
Shared KPI metrics structure for both single-asset and aggregated portfolio summaries.
- `initial_balance: float`
- `final_equity: float`
- `net_profit: float`
- `net_profit_pct: float`
- `realized_pnl: float`
- `realized_pnl_pct: float`
- `unrealized_pnl: float`
- `unrealized_pnl_pct: float`
- `total_trades: int`
- `winning_trades: int`
- `losing_trades: int`
- `win_rate_pct: float`
- `profit_factor: float`
- `max_drawdown: float`
- `max_drawdown_pct: float`
- `sharpe_ratio: float`

### `YahooAssetBacktestResult`
Per-ticker result returned in `asset_results`.
- `symbol: str`
- `name: str`
- `market: str`
- `sector: str`
- `status: Literal["READY", "NO_DATA", "INSUFFICIENT_DATA"]`
- `bars_count: int`
- `effective_from_date: Optional[str]`
- `effective_to_date: Optional[str]`
- `latest_signal: Literal["ENTER_LONG", "ENTER_SHORT", "HOLD", "NO_DATA"]`
- `latest_signal_reason: str`
- `metrics: YahooBacktestSummaryMetrics`
- `equity_curve: list[YahooEquityPoint]`
- `bars: list[YahooPriceBar]`
- `trades: list[YahooTradeRecord]`

### `YahooPortfolioBacktestResponse`
Top-level response from `POST /api/v1/yahoo/strategies/backtest`.
- `strategy_id: str`
- `strategy_name: str`
- `timeframe: str`
- `from_date: Optional[str]`
- `to_date: Optional[str]`
- `applied_params: dict[str, float | int]`
- `total_symbols_requested: int`
- `valid_symbols_count: int`
- `portfolio_metrics: YahooBacktestSummaryMetrics`
- `portfolio_equity_curve: list[YahooEquityPoint]`
- `asset_results: list[YahooAssetBacktestResult]`
