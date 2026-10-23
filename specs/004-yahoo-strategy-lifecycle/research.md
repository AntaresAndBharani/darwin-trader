# Phase 0 Research: Yahoo Finance Strategy Lifecycle & Backtesting Control Panel

## 1. Zero-Lookahead Multi-Timeframe Alignment for `DarwinXZeroTraderStrategy` on Yahoo Finance Data

- **Decision**: Compute Weekly (`W1`) OHLCV bars from the ticker's daily (`D1`) `stock_prices` in `YahooFinanceDB`, calculate Heikin-Ashi (`ha_open`, `ha_close`, `ha_color`) across the weekly series, and align the prior two completed weekly candle colors (`w1_ha_color_prev1`, `w1_ha_color_prev2`) onto each daily/weekly execution bar using strict `week_end < bar_date` (or prior ISO week index) matching.
- **Rationale**: `DarwinXZeroTraderStrategy` requires `w1_ha_color_prev2 == "RED"` and `w1_ha_color_prev1 == "GREEN"` alongside a 4-MA stack (`ema_21`, `sma_50`, `sma_100`, `sma_200`). Computing Weekly Heikin-Ashi from completed ISO weeks strictly prior to the current bar's ISO week guarantees zero lookahead bias (Principle I of the Darwin Trader Constitution) and works out-of-the-box with `data/yahoo_finance.db` daily OHLCV rows.
- **Alternatives considered**:
  - *Using current unfinished week's Heikin-Ashi color*: Rejected because intra-week daily bars would observe future Friday close data (lookahead violation).
  - *Fetching intraday 4H bars live from Yahoo Finance on every backtest*: Rejected because Yahoo Finance restricts 1h/4h history to 730 days and requires live network calls, whereas `data/yahoo_finance.db` holds 1.31M+ full multi-year daily bars offline (`D1`, `W1`, `MN1`).

## 2. Dynamic Parameterization for Registered Strategies

- **Decision**: Extend `StrategyConfig` (or pass typed parameter overrides into `YahooStrategyBacktester`) so both registered strategies accept dynamic UI parameters:
  - `darwin_trend` (`DarwinTrendStrategy`): `fast_ema_period` (12), `slow_ema_period` (26), `rsi_period` (14), `rsi_overbought` (70.0), `rsi_oversold` (30.0), `atr_period` (14), `atr_multiplier` (2.0).
  - `darwinx_zero_trader` (`DarwinXZeroTraderStrategy`): `ema_period` (21), `sma_fast_period` (50), `sma_mid_period` (100), `sma_slow_period` (200), `stop_loss_pct` (10.0), `partial_tp_pct` (5.0), `partial_fraction` (0.5).
- **Rationale**: Exposing metadata schemas via `GET /api/v1/yahoo/strategies` allows the React control panel to dynamically render typed inputs, validation min/max bounds, and a 1-click "Reset to Defaults" button without duplicating defaults in the frontend.
- **Alternatives considered**:
  - *Hardcoding indicator periods in `DarwinXZeroTraderStrategy`*: Rejected because the user explicitly requested changing strategy parameters in the control panel.

## 3. Capital-Normalized Position Sizing & Mark-to-Market (MTM) Portfolio Aggregation

- **Decision**: Size positions on Yahoo Finance equities/ETFs/indices using percentage capital allocation (`allocated_capital = current_balance * (risk_per_trade_pct / 100.0)`, `units = allocated_capital / entry_price`), and compute per-bar Mark-to-Market equity (`balance + unrealized_pnl`) at every bar close. For multi-asset batches ($N$ valid symbols), allocate `initial_balance / N` per symbol, align per-symbol MTM equity curves over the sorted outer union of dates using `ffill().fillna(capital_k)`, and sum into `portfolio_equity_curve`.
- **Rationale**: Existing `Backtester` used hardcoded `0.1` lots * `100,000` (FX contract size), which distorts stock/index prices ranging from `$10` to `$5,000`. Capital-percentage sizing normalizes returns across all Yahoo Finance instruments and ensures `final_equity == initial_balance + realized_pnl + unrealized_pnl`.
- **Alternatives considered**:
  - *Fixed 100k FX lot multiplier*: Rejected because Yahoo Finance tickers are primarily equities, ETFs, and indices where 1 unit = 1 share.
