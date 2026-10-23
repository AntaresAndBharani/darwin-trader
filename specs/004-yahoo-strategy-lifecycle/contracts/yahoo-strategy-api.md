# API Contracts: Yahoo Finance Strategy Lifecycle & Backtesting

Base Prefix: `/api/v1/yahoo`

## 1. `GET /api/v1/yahoo/strategies`

Returns the catalog of registered Yahoo Finance strategies and their configurable parameter schemas.

### Response `200 OK`
```json
{
  "strategies": [
    {
      "id": "darwin_trend",
      "name": "Darwin Trend ATR",
      "description": "EMA Trend Crossover + RSI Momentum + ATR Volatility Dynamic SL/TP.",
      "supported_timeframes": ["D1", "W1", "MN1"],
      "default_timeframe": "D1",
      "parameters": [
        {
          "key": "fast_ema_period",
          "label": "Fast EMA Period",
          "type": "int",
          "default": 12,
          "min_value": 2,
          "max_value": 200,
          "step": 1,
          "description": "Short-term exponential moving average lookback period."
        },
        {
          "key": "slow_ema_period",
          "label": "Slow EMA Period",
          "type": "int",
          "default": 26,
          "min_value": 5,
          "max_value": 400,
          "step": 1,
          "description": "Long-term exponential moving average lookback period."
        },
        {
          "key": "rsi_period",
          "label": "RSI Period",
          "type": "int",
          "default": 14,
          "min_value": 2,
          "max_value": 100,
          "step": 1,
          "description": "Relative Strength Index lookback period."
        },
        {
          "key": "rsi_overbought",
          "label": "RSI Overbought",
          "type": "float",
          "default": 70.0,
          "min_value": 51.0,
          "max_value": 95.0,
          "step": 1.0,
          "description": "Upper RSI threshold capping bullish entries."
        },
        {
          "key": "rsi_oversold",
          "label": "RSI Oversold",
          "type": "float",
          "default": 30.0,
          "min_value": 5.0,
          "max_value": 49.0,
          "step": 1.0,
          "description": "Lower RSI threshold capping bearish entries."
        },
        {
          "key": "atr_period",
          "label": "ATR Period",
          "type": "int",
          "default": 14,
          "min_value": 2,
          "max_value": 100,
          "step": 1,
          "description": "Average True Range volatility lookback period."
        },
        {
          "key": "atr_multiplier",
          "label": "ATR Stop Multiplier",
          "type": "float",
          "default": 2.0,
          "min_value": 0.5,
          "max_value": 10.0,
          "step": 0.1,
          "description": "Stop-loss distance in multiples of ATR (TP = 1.8x SL)."
        }
      ]
    },
    {
      "id": "darwinx_zero_trader",
      "name": "DarwinX Zero Trader",
      "description": "Multi-Timeframe 1W Heikin-Ashi Pullback-Reversal Filter with Quad-MA Trend Alignment and 3-Stage Position Lifecycle.",
      "supported_timeframes": ["D1", "W1", "MN1"],
      "default_timeframe": "D1",
      "parameters": [
        {
          "key": "ema_period",
          "label": "Fast EMA Period",
          "type": "int",
          "default": 21,
          "min_value": 5,
          "max_value": 100,
          "step": 1,
          "description": "Fast EMA period in the Quad-MA stack."
        },
        {
          "key": "sma_fast_period",
          "label": "Fast SMA Period",
          "type": "int",
          "default": 50,
          "min_value": 10,
          "max_value": 200,
          "step": 1,
          "description": "Fast SMA period in the Quad-MA stack."
        },
        {
          "key": "sma_mid_period",
          "label": "Mid SMA Period",
          "type": "int",
          "default": 100,
          "min_value": 20,
          "max_value": 300,
          "step": 1,
          "description": "Medium SMA period in the Quad-MA stack."
        },
        {
          "key": "sma_slow_period",
          "label": "Slow Baseline SMA Period",
          "type": "int",
          "default": 200,
          "min_value": 50,
          "max_value": 500,
          "step": 5,
          "description": "Anchor trend SMA period; price and all faster MAs must exceed this level."
        },
        {
          "key": "stop_loss_pct",
          "label": "Stop Loss (%)",
          "type": "float",
          "default": 10.0,
          "min_value": 1.0,
          "max_value": 50.0,
          "step": 0.5,
          "description": "Initial protective stop-loss percentage below entry."
        },
        {
          "key": "partial_tp_pct",
          "label": "Partial Take Profit TP1 (%)",
          "type": "float",
          "default": 5.0,
          "min_value": 0.5,
          "max_value": 50.0,
          "step": 0.5,
          "description": "First target gain percentage to scale out partial profit and ratchet stop to break-even."
        },
        {
          "key": "partial_fraction",
          "label": "Partial Scale-Out Fraction",
          "type": "float",
          "default": 0.5,
          "min_value": 0.1,
          "max_value": 0.9,
          "step": 0.05,
          "description": "Fraction of position closed at TP1 (0.5 = 50%)."
        }
      ]
    }
  ]
}
```

---

## 2. `POST /api/v1/yahoo/strategies/backtest`

Executes a historical backtest on Yahoo Finance data (`data/yahoo_finance.db`) for one or more tickers.

### Request Body
```json
{
  "strategy_id": "darwin_trend",
  "symbols": ["AAPL", "MSFT"],
  "market": null,
  "sector": null,
  "timeframe": "D1",
  "from_date": "2024-01-01",
  "to_date": "2026-10-23",
  "initial_balance": 100000.0,
  "risk_per_trade_pct": 10.0,
  "strategy_params": {
    "fast_ema_period": 12,
    "slow_ema_period": 26,
    "rsi_period": 14,
    "rsi_overbought": 70.0,
    "rsi_oversold": 30.0,
    "atr_period": 14,
    "atr_multiplier": 2.0
  }
}
```

### Error Responses
- `400 Bad Request`: Unknown `strategy_id`, invalid timeframe, inverted date range (`from_date > to_date`), invalid parameter bounds (e.g., `fast_ema_period >= slow_ema_period`), or empty symbol selection.

### Response `200 OK`
Returns `YahooPortfolioBacktestResponse` containing `portfolio_metrics`, `portfolio_equity_curve`, and `asset_results` (each with `metrics`, `latest_signal`, `latest_signal_reason`, `equity_curve`, `bars`, and `trades`).
