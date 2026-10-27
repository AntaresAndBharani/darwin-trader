"""
Yahoo Finance Strategy Lifecycle & Backtesting Engine.
Executes registered strategies (`darwin_trend` and `darwinx_zero_trader`) exclusively
against Yahoo Finance historical OHLCV data (`YahooFinanceDB`), supporting dynamic
parameter overrides, zero-lookahead Weekly Heikin-Ashi alignment, mark-to-market (MTM)
equity curves, and multi-asset portfolio aggregation.
"""
from datetime import datetime
import math
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from strategy_engine.backtester import MultiStagePosition
from strategy_engine.config import StrategyConfig
from strategy_engine.indicators import compute_ema, compute_heikin_ashi, compute_sma
from strategy_engine.models import PositionStage, SignalType, TradeSignal
from strategy_engine.sample_strategy import DarwinTrendStrategy
from strategy_engine.strategies.darwinx_zero_trader import DarwinXZeroTraderStrategy
from strategy_engine.yahoo_db import (
    SUPPORTED_YAHOO_TIMEFRAMES,
    YahooFinanceDB,
    parse_market_symbol,
)


def _finite_float(val: Any, default: float = 0.0, ndigits: int = 2) -> float:
    """Safely converts a numeric value to a finite rounded float (never NaN/Inf)."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(f):
        return default
    return round(f, ndigits)


YAHOO_STRATEGY_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "darwin_trend",
        "name": "Darwin Trend ATR",
        "description": "EMA Trend Crossover + RSI Momentum + ATR Volatility Dynamic SL/TP.",
        "supported_timeframes": list(SUPPORTED_YAHOO_TIMEFRAMES),
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
                "description": "Short-term exponential moving average lookback period.",
            },
            {
                "key": "slow_ema_period",
                "label": "Slow EMA Period",
                "type": "int",
                "default": 26,
                "min_value": 5,
                "max_value": 400,
                "step": 1,
                "description": "Long-term exponential moving average lookback period.",
            },
            {
                "key": "rsi_period",
                "label": "RSI Period",
                "type": "int",
                "default": 14,
                "min_value": 2,
                "max_value": 100,
                "step": 1,
                "description": "Relative Strength Index lookback period.",
            },
            {
                "key": "rsi_overbought",
                "label": "RSI Overbought",
                "type": "float",
                "default": 70.0,
                "min_value": 51.0,
                "max_value": 95.0,
                "step": 1.0,
                "description": "Upper RSI threshold capping bullish entries.",
            },
            {
                "key": "rsi_oversold",
                "label": "RSI Oversold",
                "type": "float",
                "default": 30.0,
                "min_value": 5.0,
                "max_value": 49.0,
                "step": 1.0,
                "description": "Lower RSI threshold capping bearish entries.",
            },
            {
                "key": "atr_period",
                "label": "ATR Period",
                "type": "int",
                "default": 14,
                "min_value": 2,
                "max_value": 100,
                "step": 1,
                "description": "Average True Range volatility lookback period.",
            },
            {
                "key": "atr_multiplier",
                "label": "ATR Stop Multiplier",
                "type": "float",
                "default": 2.0,
                "min_value": 0.5,
                "max_value": 10.0,
                "step": 0.1,
                "description": "Stop-loss distance in multiples of ATR (TP = 1.8x SL).",
            },
        ],
    },
    {
        "id": "darwinx_zero_trader",
        "name": "DarwinX Zero Trader",
        "description": "Multi-Timeframe 1W Heikin-Ashi Pullback-Reversal Filter with Quad-MA Trend Alignment and 3-Stage Position Lifecycle.",
        "supported_timeframes": list(SUPPORTED_YAHOO_TIMEFRAMES),
        "default_timeframe": "D1",
        "parameters": [
            {
                "key": "ema_period",
                "label": "Fast EMA Period",
                "type": "int",
                "default": 21,
                "min_value": 2,
                "max_value": 150,
                "step": 1,
                "description": "Fast EMA period in the Quad-MA stack.",
            },
            {
                "key": "sma_fast_period",
                "label": "Fast SMA Period",
                "type": "int",
                "default": 50,
                "min_value": 5,
                "max_value": 250,
                "step": 1,
                "description": "Fast SMA period in the Quad-MA stack.",
            },
            {
                "key": "sma_mid_period",
                "label": "Mid SMA Period",
                "type": "int",
                "default": 100,
                "min_value": 10,
                "max_value": 350,
                "step": 1,
                "description": "Medium SMA period in the Quad-MA stack.",
            },
            {
                "key": "sma_slow_period",
                "label": "Slow Baseline SMA Period",
                "type": "int",
                "default": 200,
                "min_value": 20,
                "max_value": 500,
                "step": 5,
                "description": "Anchor trend SMA period; price and all faster MAs must exceed this level.",
            },
            {
                "key": "stop_loss_pct",
                "label": "Stop Loss (%)",
                "type": "float",
                "default": 10.0,
                "min_value": 0.5,
                "max_value": 50.0,
                "step": 0.5,
                "description": "Initial protective stop-loss percentage below entry.",
            },
            {
                "key": "partial_tp_pct",
                "label": "Partial Take Profit TP1 (%)",
                "type": "float",
                "default": 5.0,
                "min_value": 0.5,
                "max_value": 100.0,
                "step": 0.5,
                "description": "First target gain percentage to scale out partial profit and ratchet stop to break-even.",
            },
            {
                "key": "partial_fraction",
                "label": "Partial Scale-Out Fraction",
                "type": "float",
                "default": 0.5,
                "min_value": 0.1,
                "max_value": 0.9,
                "step": 0.05,
                "description": "Fraction of position closed at TP1 (0.5 = 50%).",
            },
        ],
    },
]


def get_yahoo_strategies_catalog() -> List[Dict[str, Any]]:
    """Returns a deep-copied list of registered Yahoo Finance strategy definitions."""
    return [
        {
            **s,
            "supported_timeframes": list(s["supported_timeframes"]),
            "parameters": [dict(p) for p in s["parameters"]],
        }
        for s in YAHOO_STRATEGY_CATALOG
    ]


def validate_and_build_strategy_config(
    strategy_id: str,
    timeframe: str = "D1",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    initial_balance: float = 100000.0,
    risk_per_trade_pct: float = 10.0,
    strategy_params: Optional[Dict[str, Any]] = None,
) -> Tuple[StrategyConfig, Dict[str, Any], Dict[str, Any]]:
    """
    Validates backtest inputs and constructs an isolated StrategyConfig instance
    plus the resolved parameter dictionary.
    Raises ValueError on any invalid input.
    """
    catalog_map = {s["id"]: s for s in YAHOO_STRATEGY_CATALOG}
    if strategy_id not in catalog_map:
        raise ValueError(
            f"Unknown strategy_id '{strategy_id}'. Available: {', '.join(catalog_map.keys())}"
        )

    tf_norm = (timeframe or "D1").strip().upper()
    if tf_norm not in SUPPORTED_YAHOO_TIMEFRAMES:
        raise ValueError(
            f"Unsupported timeframe '{timeframe}'. Supported: {', '.join(SUPPORTED_YAHOO_TIMEFRAMES)}"
        )

    if initial_balance is None or float(initial_balance) <= 0:
        raise ValueError("initial_balance must be greater than 0.")

    if risk_per_trade_pct is None or not (0.5 <= float(risk_per_trade_pct) <= 100.0):
        raise ValueError("risk_per_trade_pct must be between 0.5 and 100.0.")

    from_clean: Optional[str] = None
    to_clean: Optional[str] = None
    if from_date and str(from_date).strip():
        from_clean = str(from_date).strip()[:10]
        try:
            datetime.strptime(from_clean, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"Invalid from_date '{from_date}'. Expected YYYY-MM-DD.") from exc

    if to_date and str(to_date).strip():
        to_clean = str(to_date).strip()[:10]
        try:
            datetime.strptime(to_clean, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"Invalid to_date '{to_date}'. Expected YYYY-MM-DD.") from exc

    if from_clean and to_clean and from_clean > to_clean:
        raise ValueError(
            f"Invalid date range: from_date ({from_clean}) cannot be after to_date ({to_clean})."
        )

    strategy_def = catalog_map[strategy_id]
    raw_params = strategy_params or {}
    applied_params: Dict[str, Any] = {}

    for param_spec in strategy_def["parameters"]:
        key = param_spec["key"]
        raw_val = raw_params.get(key, param_spec["default"])
        try:
            val = int(raw_val) if param_spec["type"] == "int" else float(raw_val)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid numeric value for parameter '{key}': {raw_val}") from exc

        min_v = param_spec["min_value"]
        max_v = param_spec["max_value"]
        if val < min_v or val > max_v:
            raise ValueError(
                f"Parameter '{key}' ({val}) out of bounds [{min_v}, {max_v}]."
            )
        applied_params[key] = val

    if strategy_id == "darwin_trend":
        if applied_params["fast_ema_period"] >= applied_params["slow_ema_period"]:
            raise ValueError(
                "fast_ema_period must be strictly less than slow_ema_period."
            )
        if applied_params["rsi_oversold"] >= applied_params["rsi_overbought"]:
            raise ValueError(
                "rsi_oversold must be strictly less than rsi_overbought."
            )
    elif strategy_id == "darwinx_zero_trader":
        if applied_params["ema_period"] >= applied_params["sma_slow_period"]:
            raise ValueError(
                "ema_period must be strictly less than sma_slow_period."
            )

    config = StrategyConfig(
        strategy_name=strategy_def["name"],
        timeframe=tf_norm,
        mock_mode=True,
        risk_per_trade_pct=float(risk_per_trade_pct),
        **applied_params,
    )
    return config, applied_params, strategy_def


def enrich_weekly_heikin_ashi(
    bars_df: pd.DataFrame, weekly_bars: List[Dict[str, Any]]
) -> pd.DataFrame:
    """
    Computes Weekly (W1) Heikin-Ashi colors from `weekly_bars` and aligns `w1_ha_color_prev1`
    and `w1_ha_color_prev2` onto `bars_df` using a strict zero-lookahead rule:
    only completed ISO weeks strictly prior to the execution bar's ISO week are visible.
    """
    df = bars_df.copy()
    if df.empty or len(weekly_bars) < 2:
        df["w1_ha_color_prev1"] = pd.Series([None] * len(df), index=df.index, dtype=object)
        df["w1_ha_color_prev2"] = pd.Series([None] * len(df), index=df.index, dtype=object)
        return df

    w_df = pd.DataFrame(weekly_bars)
    ha_w = compute_heikin_ashi(w_df)

    week_keys: List[Tuple[int, int]] = []
    week_colors: List[str] = []
    for idx, row in ha_w.iterrows():
        d_str = str(w_df.loc[idx, "date"])[:10]
        dt = datetime.strptime(d_str, "%Y-%m-%d")
        iso_y, iso_w, _ = dt.isocalendar()
        week_keys.append((iso_y, iso_w))
        color = "GREEN" if float(row["ha_close"]) > float(row["ha_open"]) else "RED"
        week_colors.append(color)

    prev1_list: List[Optional[str]] = []
    prev2_list: List[Optional[str]] = []

    w_idx = 0
    n_weeks = len(week_keys)

    for _, row in df.iterrows():
        d_str = str(row["date"])[:10]
        dt = datetime.strptime(d_str, "%Y-%m-%d")
        bar_iso = (dt.isocalendar()[0], dt.isocalendar()[1])

        # Advance w_idx while week_keys[w_idx] is strictly prior to bar_iso
        while w_idx < n_weeks and week_keys[w_idx] < bar_iso:
            w_idx += 1

        # Now week_keys[:w_idx] are all completed weeks strictly before bar_iso
        if w_idx >= 2:
            prev1_list.append(week_colors[w_idx - 1])
            prev2_list.append(week_colors[w_idx - 2])
        else:
            prev1_list.append(None)
            prev2_list.append(None)

    # Explicit object dtype keeps `None` sentinels intact (pandas 3 string inference coerces them to NaN)
    df["w1_ha_color_prev1"] = pd.Series(prev1_list, index=df.index, dtype=object)
    df["w1_ha_color_prev2"] = pd.Series(prev2_list, index=df.index, dtype=object)
    return df


def _compute_summary_metrics(
    initial_balance: float,
    realized_pnl: float,
    unrealized_pnl: float,
    trades: List[Dict[str, Any]],
    equity_curve: List[Dict[str, Any]],
    timeframe: str = "D1",
) -> Dict[str, Any]:
    """Calculates standardized MTM summary KPIs from trades and equity curve."""
    init_bal = float(initial_balance)
    real_pnl = float(realized_pnl)
    unreal_pnl = float(unrealized_pnl)
    net_profit = real_pnl + unreal_pnl
    final_equity = init_bal + net_profit

    net_profit_pct = (net_profit / init_bal * 100.0) if init_bal > 0 else 0.0
    realized_pnl_pct = (real_pnl / init_bal * 100.0) if init_bal > 0 else 0.0
    unrealized_pnl_pct = (unreal_pnl / init_bal * 100.0) if init_bal > 0 else 0.0

    closed_trades = [t for t in trades if t.get("stage") != "OPEN"]
    total_trades = len(closed_trades)
    winning_trades = [t for t in closed_trades if float(t.get("pnl", 0.0)) > 0]
    losing_trades = [t for t in closed_trades if float(t.get("pnl", 0.0)) < 0]

    win_rate = (len(winning_trades) / total_trades * 100.0) if total_trades > 0 else 0.0
    gross_profit = sum(float(t.get("pnl", 0.0)) for t in winning_trades)
    gross_loss = abs(sum(float(t.get("pnl", 0.0)) for t in losing_trades))
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = 99.99
    else:
        profit_factor = 0.0

    if equity_curve:
        eq_vals = np.array([init_bal] + [float(pt["equity"]) for pt in equity_curve], dtype=float)
        peaks = np.maximum.accumulate(eq_vals)
        dd_dollars = peaks - eq_vals
        dd_pcts = np.where(peaks > 0, (dd_dollars / peaks) * 100.0, 0.0)
        max_dd = float(np.max(dd_dollars)) if len(dd_dollars) > 0 else 0.0
        max_dd_pct = float(np.max(dd_pcts)) if len(dd_pcts) > 0 else 0.0

        # Sharpe ratio from period-over-period MTM equity returns
        if len(eq_vals) >= 3:
            prev_eq = eq_vals[:-1]
            rets = np.where(prev_eq > 0, np.diff(eq_vals) / prev_eq, 0.0)
            std_ret = float(np.std(rets, ddof=1))
            if std_ret > 1e-12:
                ann_factor = {"D1": 252.0, "W1": 52.0, "MN1": 12.0}.get(timeframe.upper(), 252.0)
                rf_per_period = 0.02 / ann_factor
                sharpe = float((np.mean(rets) - rf_per_period) / std_ret * math.sqrt(ann_factor))
            else:
                sharpe = 0.0
        else:
            sharpe = 0.0
    else:
        max_dd = 0.0
        max_dd_pct = 0.0
        sharpe = 0.0

    return {
        "initial_balance": _finite_float(init_bal, 0.0, 2),
        "final_equity": _finite_float(final_equity, 0.0, 2),
        "net_profit": _finite_float(net_profit, 0.0, 2),
        "net_profit_pct": _finite_float(net_profit_pct, 0.0, 2),
        "realized_pnl": _finite_float(real_pnl, 0.0, 2),
        "realized_pnl_pct": _finite_float(realized_pnl_pct, 0.0, 2),
        "unrealized_pnl": _finite_float(unreal_pnl, 0.0, 2),
        "unrealized_pnl_pct": _finite_float(unrealized_pnl_pct, 0.0, 2),
        "total_trades": int(total_trades),
        "winning_trades": int(len(winning_trades)),
        "losing_trades": int(len(losing_trades)),
        "win_rate_pct": _finite_float(win_rate, 0.0, 2),
        "profit_factor": _finite_float(profit_factor, 0.0, 2),
        "max_drawdown": _finite_float(max_dd, 0.0, 2),
        "max_drawdown_pct": _finite_float(max_dd_pct, 0.0, 2),
        "sharpe_ratio": _finite_float(sharpe, 0.0, 2),
    }


def run_single_asset_yahoo_backtest(
    db: YahooFinanceDB,
    symbol: str,
    strategy_id: str = "darwin_trend",
    timeframe: str = "D1",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    initial_balance: float = 100000.0,
    risk_per_trade_pct: float = 10.0,
    strategy_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Executes a mark-to-market historical backtest for a single Yahoo Finance ticker.
    Never accesses Darwinex MT5 state or `historical_rates.db`.
    """
    sym, _ = parse_market_symbol(symbol)
    config, applied_params, _ = validate_and_build_strategy_config(
        strategy_id=strategy_id,
        timeframe=timeframe,
        from_date=from_date,
        to_date=to_date,
        initial_balance=initial_balance,
        risk_per_trade_pct=risk_per_trade_pct,
        strategy_params=strategy_params,
    )
    config.symbol = sym

    ticker_meta = db.get_ticker(sym) or {
        "symbol": sym,
        "name": sym,
        "market": "",
        "sector": "",
        "industry": "",
    }

    if strategy_id == "darwin_trend":
        warmup_bars = (
            max(
                int(config.slow_ema_period),
                int(config.rsi_period),
                int(config.atr_period),
            )
            + 15
        )
    else:
        warmup_bars = (
            max(
                int(config.sma_slow_period),
                int(config.sma_mid_period),
                int(config.sma_fast_period),
                int(config.ema_period),
            )
            + 10
        )

    raw_bars = db.get_price_history_range(
        symbol=sym,
        timeframe=config.timeframe,
        from_date=from_date,
        to_date=to_date,
        warmup_bars=warmup_bars,
    )

    in_range_bars = [b for b in raw_bars if b.get("in_range", True)]
    if not raw_bars or not in_range_bars:
        empty_metrics = _compute_summary_metrics(
            initial_balance=initial_balance,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            trades=[],
            equity_curve=[],
            timeframe=config.timeframe,
        )
        return {
            "symbol": sym,
            "name": ticker_meta.get("name") or sym,
            "market": ticker_meta.get("market") or "",
            "sector": ticker_meta.get("sector") or "",
            "status": "NO_DATA",
            "bars_count": 0,
            "effective_from_date": None,
            "effective_to_date": None,
            "latest_signal": "NO_DATA",
            "latest_signal_reason": f"No Yahoo Finance price data available for {sym} in selected period.",
            "metrics": empty_metrics,
            "equity_curve": [],
            "bars": [],
            "trades": [],
        }

    df = pd.DataFrame(raw_bars)
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)

    if strategy_id == "darwinx_zero_trader":
        weekly_bars = db.get_price_history_range(
            symbol=sym,
            timeframe="W1",
            from_date=None,
            to_date=to_date,
            warmup_bars=0,
        )
        df = enrich_weekly_heikin_ashi(df, weekly_bars)
        # Precompute moving averages across full series (causal rolling/ewm) for O(1) bar evaluation
        df["_ma_slow"] = compute_sma(df["close"], int(config.sma_slow_period))
        df["_ma_mid"] = compute_sma(df["close"], int(config.sma_mid_period))
        df["_ma_fast"] = compute_sma(df["close"], int(config.sma_fast_period))
        df["_ma_ema"] = compute_ema(df["close"], int(config.ema_period))
        strategy = DarwinXZeroTraderStrategy(config=config)
    else:
        strategy = DarwinTrendStrategy(config=config)
        df["_ema_fast"] = strategy.calculate_ema(df["close"], int(config.fast_ema_period))
        df["_ema_slow"] = strategy.calculate_ema(df["close"], int(config.slow_ema_period))
        df["_rsi"] = strategy.calculate_rsi(df["close"], int(config.rsi_period))
        df["_atr"] = strategy.calculate_atr(df, int(config.atr_period))

    balance = float(initial_balance)
    trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []
    peak_equity = float(initial_balance)
    open_position: Optional[Any] = None

    latest_signal_str = "HOLD"
    latest_signal_reason = "No trade setup triggers met"

    # Determine first in-range index
    in_range_indices = [idx for idx, val in enumerate(df["in_range"].tolist()) if val]
    first_in_range_idx = in_range_indices[0]

    for i in range(first_in_range_idx, len(df)):
        current_bar = df.iloc[i]
        bar_date = str(current_bar["date"])[:10]
        bar_time = int(current_bar["time"])
        bar_open = float(current_bar["open"])
        bar_high = float(current_bar["high"])
        bar_low = float(current_bar["low"])
        bar_close = float(current_bar["close"])

        # Prepare window slice for strategy evaluation
        window_start = max(0, i - warmup_bars - 5)
        sub_df = df.iloc[window_start : i + 1]

        # 1. Manage existing open position on current bar
        if open_position is not None:
            if isinstance(open_position, MultiStagePosition):
                pos = open_position
                entry_price = pos.entry_price
                if pos.stage == PositionStage.FULL:
                    if bar_low <= pos.stop_loss:
                        pnl = (pos.stop_loss - entry_price) * pos.units
                        pnl_pct = ((pos.stop_loss - entry_price) / entry_price * 100.0) if entry_price > 0 else 0.0
                        balance += pnl
                        pos.realized_pnl += pnl
                        pos.stage = PositionStage.CLOSED
                        trades.append(
                            {
                                "symbol": sym,
                                "type": pos.order_type,
                                "stage": "CLOSED",
                                "entry_date": pos.entry_date,
                                "entry_time": pos.entry_time,
                                "entry_price": _finite_float(entry_price, 0.0, 4),
                                "exit_date": bar_date,
                                "exit_time": bar_time,
                                "exit_price": _finite_float(pos.stop_loss, 0.0, 4),
                                "units": _finite_float(pos.units, 0.0, 4),
                                "pnl": _finite_float(pnl, 0.0, 2),
                                "pnl_pct": _finite_float(pnl_pct, 0.0, 2),
                                "balance_after": _finite_float(balance, 0.0, 2),
                                "reason": "Stop Loss Hit",
                            }
                        )
                        open_position = None
                    elif pos.partial_take_profit is not None and bar_high >= pos.partial_take_profit:
                        scale_units = pos.units * pos.partial_fraction
                        rem_units = pos.units - scale_units
                        pnl_tp1 = (pos.partial_take_profit - entry_price) * scale_units
                        pnl_tp1_pct = (
                            ((pos.partial_take_profit - entry_price) / entry_price * 100.0)
                            if entry_price > 0
                            else 0.0
                        )
                        balance += pnl_tp1
                        pos.realized_pnl += pnl_tp1
                        pos.units = rem_units
                        pos.stage = PositionStage.PARTIAL
                        pos.stop_loss = entry_price

                        trades.append(
                            {
                                "symbol": sym,
                                "type": pos.order_type,
                                "stage": "PARTIAL",
                                "entry_date": pos.entry_date,
                                "entry_time": pos.entry_time,
                                "entry_price": _finite_float(entry_price, 0.0, 4),
                                "exit_date": bar_date,
                                "exit_time": bar_time,
                                "exit_price": _finite_float(pos.partial_take_profit, 0.0, 4),
                                "units": _finite_float(scale_units, 0.0, 4),
                                "pnl": _finite_float(pnl_tp1, 0.0, 2),
                                "pnl_pct": _finite_float(pnl_tp1_pct, 0.0, 2),
                                "balance_after": _finite_float(balance, 0.0, 2),
                                "reason": "Partial Take Profit (TP1) + Break-Even Ratchet",
                            }
                        )

                        is_bearish = bar_close < bar_open
                        same_bar_be = (is_bearish and bar_low <= entry_price) or (bar_close <= entry_price)
                        if same_bar_be:
                            pos.stage = PositionStage.CLOSED
                            trades.append(
                                {
                                    "symbol": sym,
                                    "type": pos.order_type,
                                    "stage": "CLOSED",
                                    "entry_date": pos.entry_date,
                                    "entry_time": pos.entry_time,
                                    "entry_price": _finite_float(entry_price, 0.0, 4),
                                    "exit_date": bar_date,
                                    "exit_time": bar_time,
                                    "exit_price": _finite_float(entry_price, 0.0, 4),
                                    "units": _finite_float(rem_units, 0.0, 4),
                                    "pnl": 0.0,
                                    "pnl_pct": 0.0,
                                    "balance_after": _finite_float(balance, 0.0, 2),
                                    "reason": "Same-Bar Break-Even Stop Exit",
                                }
                            )
                            open_position = None
                        else:
                            exit_sig = strategy.evaluate_exit(sub_df, pos)
                            if exit_sig in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT):
                                pnl_macro = (bar_close - entry_price) * rem_units
                                pnl_macro_pct = (
                                    ((bar_close - entry_price) / entry_price * 100.0)
                                    if entry_price > 0
                                    else 0.0
                                )
                                balance += pnl_macro
                                pos.realized_pnl += pnl_macro
                                pos.stage = PositionStage.CLOSED
                                trades.append(
                                    {
                                        "symbol": sym,
                                        "type": pos.order_type,
                                        "stage": "CLOSED",
                                        "entry_date": pos.entry_date,
                                        "entry_time": pos.entry_time,
                                        "entry_price": _finite_float(entry_price, 0.0, 4),
                                        "exit_date": bar_date,
                                        "exit_time": bar_time,
                                        "exit_price": _finite_float(bar_close, 0.0, 4),
                                        "units": _finite_float(rem_units, 0.0, 4),
                                        "pnl": _finite_float(pnl_macro, 0.0, 2),
                                        "pnl_pct": _finite_float(pnl_macro_pct, 0.0, 2),
                                        "balance_after": _finite_float(balance, 0.0, 2),
                                        "reason": "Macro Weekly HA Reversal Exit",
                                    }
                                )
                                open_position = None
                elif pos.stage == PositionStage.PARTIAL:
                    if bar_low <= pos.stop_loss:
                        exit_price = pos.stop_loss
                        pnl = (exit_price - entry_price) * pos.units
                        pnl_pct = ((exit_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0.0
                        balance += pnl
                        pos.realized_pnl += pnl
                        pos.stage = PositionStage.CLOSED
                        trades.append(
                            {
                                "symbol": sym,
                                "type": pos.order_type,
                                "stage": "CLOSED",
                                "entry_date": pos.entry_date,
                                "entry_time": pos.entry_time,
                                "entry_price": _finite_float(entry_price, 0.0, 4),
                                "exit_date": bar_date,
                                "exit_time": bar_time,
                                "exit_price": _finite_float(exit_price, 0.0, 4),
                                "units": _finite_float(pos.units, 0.0, 4),
                                "pnl": _finite_float(pnl, 0.0, 2),
                                "pnl_pct": _finite_float(pnl_pct, 0.0, 2),
                                "balance_after": _finite_float(balance, 0.0, 2),
                                "reason": "Break-Even Stop Exit",
                            }
                        )
                        open_position = None
                    else:
                        exit_sig = strategy.evaluate_exit(sub_df, pos)
                        if exit_sig in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT):
                            exit_price = bar_close
                            pnl = (exit_price - entry_price) * pos.units
                            pnl_pct = ((exit_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0.0
                            balance += pnl
                            pos.realized_pnl += pnl
                            pos.stage = PositionStage.CLOSED
                            trades.append(
                                {
                                    "symbol": sym,
                                    "type": pos.order_type,
                                    "stage": "CLOSED",
                                    "entry_date": pos.entry_date,
                                    "entry_time": pos.entry_time,
                                    "entry_price": _finite_float(entry_price, 0.0, 4),
                                    "exit_date": bar_date,
                                    "exit_time": bar_time,
                                    "exit_price": _finite_float(exit_price, 0.0, 4),
                                    "units": _finite_float(pos.units, 0.0, 4),
                                    "pnl": _finite_float(pnl, 0.0, 2),
                                    "pnl_pct": _finite_float(pnl_pct, 0.0, 2),
                                    "balance_after": _finite_float(balance, 0.0, 2),
                                    "reason": "Macro Weekly HA Reversal Exit",
                                }
                            )
                            open_position = None
            else:
                pos_type = open_position["type"]
                sl = open_position["sl"]
                tp = open_position["tp"]
                entry_price = open_position["entry_price"]
                units = open_position["units"]

                closed = False
                exit_price = bar_close
                exit_reason = ""

                if pos_type == "BUY":
                    if bar_low <= sl:
                        closed = True
                        exit_price = sl
                        exit_reason = "Stop Loss Hit"
                    elif bar_high >= tp:
                        closed = True
                        exit_price = tp
                        exit_reason = "Take Profit Hit"
                elif pos_type == "SELL":
                    if bar_high >= sl:
                        closed = True
                        exit_price = sl
                        exit_reason = "Stop Loss Hit"
                    elif bar_low <= tp:
                        closed = True
                        exit_price = tp
                        exit_reason = "Take Profit Hit"

                if closed:
                    pnl = (
                        (exit_price - entry_price) * units
                        if pos_type == "BUY"
                        else (entry_price - exit_price) * units
                    )
                    pnl_pct = (
                        ((exit_price - entry_price) / entry_price * 100.0)
                        if pos_type == "BUY" and entry_price > 0
                        else (((entry_price - exit_price) / entry_price * 100.0) if entry_price > 0 else 0.0)
                    )
                    balance += pnl
                    trades.append(
                        {
                            "symbol": sym,
                            "type": pos_type,
                            "stage": "CLOSED",
                            "entry_date": open_position["entry_date"],
                            "entry_time": open_position["entry_time"],
                            "entry_price": _finite_float(entry_price, 0.0, 4),
                            "exit_date": bar_date,
                            "exit_time": bar_time,
                            "exit_price": _finite_float(exit_price, 0.0, 4),
                            "units": _finite_float(units, 0.0, 4),
                            "pnl": _finite_float(pnl, 0.0, 2),
                            "pnl_pct": _finite_float(pnl_pct, 0.0, 2),
                            "balance_after": _finite_float(balance, 0.0, 2),
                            "reason": exit_reason,
                        }
                    )
                    open_position = None

        # 2. Evaluate strategy signal on current bar
        if isinstance(strategy, DarwinXZeroTraderStrategy):
            signal: TradeSignal = strategy.generate_signal(sub_df, position=open_position)
        else:
            signal = strategy.generate_signal(sub_df)

        if i == len(df) - 1:
            latest_signal_str = signal.signal_type.value
            latest_signal_reason = signal.reason or ""

        if open_position is None and signal.signal_type in (
            SignalType.ENTER_LONG,
            SignalType.ENTER_SHORT,
        ):
            is_buy = signal.signal_type == SignalType.ENTER_LONG
            allocated_capital = max(balance, 0.0) * (float(config.risk_per_trade_pct) / 100.0)
            units = (allocated_capital / bar_close) if bar_close > 0 else 0.0

            if units > 0:
                if signal.partial_take_profit is not None and signal.partial_fraction > 0.0:
                    open_position = MultiStagePosition(
                        entry_price=bar_close,
                        stop_loss=signal.stop_loss,
                        units=units,
                        partial_take_profit=signal.partial_take_profit,
                        partial_fraction=signal.partial_fraction,
                        stage=PositionStage.FULL,
                        entry_time=bar_time,
                        entry_date=bar_date,
                        order_type="BUY" if is_buy else "SELL",
                        reason=signal.reason,
                    )
                else:
                    open_position = {
                        "type": "BUY" if is_buy else "SELL",
                        "entry_price": bar_close,
                        "sl": float(signal.stop_loss or 0.0),
                        "tp": float(signal.take_profit or 0.0),
                        "units": units,
                        "entry_time": bar_time,
                        "entry_date": bar_date,
                        "reason": signal.reason,
                    }

        # 3. Compute Mark-to-Market (MTM) unrealized PnL and equity at bar close
        unrealized_bar_pnl = 0.0
        if open_position is not None:
            if isinstance(open_position, MultiStagePosition):
                if open_position.order_type == "BUY":
                    unrealized_bar_pnl = (bar_close - open_position.entry_price) * open_position.units
                else:
                    unrealized_bar_pnl = (open_position.entry_price - bar_close) * open_position.units
            else:
                if open_position["type"] == "BUY":
                    unrealized_bar_pnl = (bar_close - open_position["entry_price"]) * open_position["units"]
                else:
                    unrealized_bar_pnl = (open_position["entry_price"] - bar_close) * open_position["units"]

        mtm_equity = balance + unrealized_bar_pnl
        if mtm_equity > peak_equity:
            peak_equity = mtm_equity
        dd_pct = ((mtm_equity - peak_equity) / peak_equity * 100.0) if peak_equity > 0 else 0.0

        equity_curve.append(
            {
                "time": bar_time,
                "date": bar_date,
                "equity": _finite_float(mtm_equity, 0.0, 2),
                "balance": _finite_float(balance, 0.0, 2),
                "drawdown_pct": _finite_float(dd_pct, 0.0, 2),
            }
        )

    # Terminal bar accounting for any remaining open position
    realized_pnl = balance - float(initial_balance)
    terminal_unrealized_pnl = 0.0
    if open_position is not None and len(df) > 0:
        last_bar = df.iloc[-1]
        last_close = float(last_bar["close"])
        if isinstance(open_position, MultiStagePosition):
            entry_p = open_position.entry_price
            rem_u = open_position.units
            terminal_unrealized_pnl = (
                (last_close - entry_p) * rem_u
                if open_position.order_type == "BUY"
                else (entry_p - last_close) * rem_u
            )
            unr_pct = ((last_close - entry_p) / entry_p * 100.0) if entry_p > 0 else 0.0
            trades.append(
                {
                    "symbol": sym,
                    "type": open_position.order_type,
                    "stage": open_position.stage.value,
                    "entry_date": open_position.entry_date,
                    "entry_time": open_position.entry_time,
                    "entry_price": _finite_float(entry_p, 0.0, 4),
                    "exit_date": None,
                    "exit_time": None,
                    "exit_price": _finite_float(last_close, 0.0, 4),
                    "units": _finite_float(rem_u, 0.0, 4),
                    "pnl": _finite_float(terminal_unrealized_pnl, 0.0, 2),
                    "pnl_pct": _finite_float(unr_pct, 0.0, 2),
                    "balance_after": _finite_float(balance + terminal_unrealized_pnl, 0.0, 2),
                    "reason": "Open Position (Marked to Market)",
                }
            )
        else:
            entry_p = open_position["entry_price"]
            rem_u = open_position["units"]
            pos_t = open_position["type"]
            terminal_unrealized_pnl = (
                (last_close - entry_p) * rem_u if pos_t == "BUY" else (entry_p - last_close) * rem_u
            )
            unr_pct = (
                ((last_close - entry_p) / entry_p * 100.0)
                if pos_t == "BUY" and entry_p > 0
                else (((entry_p - last_close) / entry_p * 100.0) if entry_p > 0 else 0.0)
            )
            trades.append(
                {
                    "symbol": sym,
                    "type": pos_t,
                    "stage": "FULL",
                    "entry_date": open_position["entry_date"],
                    "entry_time": open_position["entry_time"],
                    "entry_price": _finite_float(entry_p, 0.0, 4),
                    "exit_date": None,
                    "exit_time": None,
                    "exit_price": _finite_float(last_close, 0.0, 4),
                    "units": _finite_float(rem_u, 0.0, 4),
                    "pnl": _finite_float(terminal_unrealized_pnl, 0.0, 2),
                    "pnl_pct": _finite_float(unr_pct, 0.0, 2),
                    "balance_after": _finite_float(balance + terminal_unrealized_pnl, 0.0, 2),
                    "reason": "Open Position (Marked to Market)",
                }
            )

    metrics = _compute_summary_metrics(
        initial_balance=initial_balance,
        realized_pnl=realized_pnl,
        unrealized_pnl=terminal_unrealized_pnl,
        trades=trades,
        equity_curve=equity_curve,
        timeframe=config.timeframe,
    )

    clean_bars = [
        {
            "time": int(b["time"]),
            "date": str(b["date"])[:10],
            "open": _finite_float(b["open"], 0.0, 4),
            "high": _finite_float(b["high"], 0.0, 4),
            "low": _finite_float(b["low"], 0.0, 4),
            "close": _finite_float(b["close"], 0.0, 4),
            "volume": int(b.get("volume") or 0),
        }
        for b in in_range_bars
    ]

    return {
        "symbol": sym,
        "name": ticker_meta.get("name") or sym,
        "market": ticker_meta.get("market") or "",
        "sector": ticker_meta.get("sector") or "",
        "status": "READY",
        "bars_count": len(clean_bars),
        "effective_from_date": clean_bars[0]["date"] if clean_bars else None,
        "effective_to_date": clean_bars[-1]["date"] if clean_bars else None,
        "latest_signal": latest_signal_str,
        "latest_signal_reason": latest_signal_reason,
        "metrics": metrics,
        "equity_curve": equity_curve,
        "bars": clean_bars,
        "trades": trades,
    }


def run_yahoo_portfolio_backtest(
    db: YahooFinanceDB,
    strategy_id: str = "darwin_trend",
    symbols: Optional[List[str]] = None,
    market: Optional[str] = None,
    sector: Optional[str] = None,
    timeframe: str = "D1",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    initial_balance: float = 100000.0,
    risk_per_trade_pct: float = 10.0,
    strategy_params: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> Dict[str, Any]:
    """
    Executes single-asset or multi-asset/sector batch backtesting on Yahoo Finance data.
    Allocates `initial_balance / N` across the N valid symbols, aligns per-symbol MTM
    equity curves across the union of dates using `ffill().fillna(capital_k)`, and
    returns both the aggregated portfolio summary and per-asset results.
    """
    config, applied_params, strategy_def = validate_and_build_strategy_config(
        strategy_id=strategy_id,
        timeframe=timeframe,
        from_date=from_date,
        to_date=to_date,
        initial_balance=initial_balance,
        risk_per_trade_pct=risk_per_trade_pct,
        strategy_params=strategy_params,
    )

    target_symbols: List[str] = []
    if symbols:
        seen = set()
        for raw_s in symbols:
            sym, _ = parse_market_symbol(raw_s)
            if sym and sym not in seen:
                seen.add(sym)
                target_symbols.append(sym)
    elif market or sector:
        matched_tickers = db.get_tickers(market=market, sector=sector, active_only=True)
        target_symbols = [t["symbol"] for t in matched_tickers if t.get("symbol")]

    if not target_symbols:
        raise ValueError(
            "At least one Yahoo Finance ticker symbol (or a matching market/sector filter) must be provided."
        )

    # First check data availability per symbol to allocate capital_k equally across valid symbols
    data_ranges = db.get_data_ranges(target_symbols)
    from_clean = str(from_date).strip()[:10] if (from_date and str(from_date).strip()) else None
    to_clean = str(to_date).strip()[:10] if (to_date and str(to_date).strip()) else None

    prelim_valid: List[str] = []
    for sym in target_symbols:
        rng = data_ranges.get(sym)
        if not rng or not rng[0] or not rng[1]:
            continue
        min_d, max_d = rng
        if from_clean and max_d < from_clean:
            continue
        if to_clean and min_d > to_clean:
            continue
        prelim_valid.append(sym)

    valid_count = len(prelim_valid)
    capital_per_symbol = (
        float(initial_balance) / valid_count if valid_count > 0 else float(initial_balance)
    )

    total_targets = len(target_symbols)
    asset_results: List[Dict[str, Any]] = []
    for idx, sym in enumerate(target_symbols):
        if progress_callback is not None:
            progress_callback(sym, idx, total_targets)

        sym_init_bal = capital_per_symbol if sym in prelim_valid else 0.0
        if sym_init_bal <= 0.0:
            ticker_meta = db.get_ticker(sym) or {
                "symbol": sym,
                "name": sym,
                "market": "",
                "sector": "",
            }
            empty_metrics = _compute_summary_metrics(
                initial_balance=0.0,
                realized_pnl=0.0,
                unrealized_pnl=0.0,
                trades=[],
                equity_curve=[],
                timeframe=config.timeframe,
            )
            asset_results.append(
                {
                    "symbol": sym,
                    "name": ticker_meta.get("name") or sym,
                    "market": ticker_meta.get("market") or "",
                    "sector": ticker_meta.get("sector") or "",
                    "status": "NO_DATA",
                    "bars_count": 0,
                    "effective_from_date": None,
                    "effective_to_date": None,
                    "latest_signal": "NO_DATA",
                    "latest_signal_reason": f"No Yahoo Finance price data available for {sym} in selected period.",
                    "metrics": empty_metrics,
                    "equity_curve": [],
                    "bars": [],
                    "trades": [],
                }
            )
        else:
            res = run_single_asset_yahoo_backtest(
                db=db,
                symbol=sym,
                strategy_id=strategy_id,
                timeframe=config.timeframe,
                from_date=from_date,
                to_date=to_date,
                initial_balance=sym_init_bal,
                risk_per_trade_pct=risk_per_trade_pct,
                strategy_params=applied_params,
            )
            asset_results.append(res)

        if progress_callback is not None:
            progress_callback(sym, idx + 1, total_targets)

    ready_results = [r for r in asset_results if r["status"] == "READY" and r["equity_curve"]]
    if not ready_results:
        empty_portfolio_metrics = _compute_summary_metrics(
            initial_balance=initial_balance,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            trades=[],
            equity_curve=[],
            timeframe=config.timeframe,
        )
        return {
            "strategy_id": strategy_id,
            "strategy_name": strategy_def["name"],
            "timeframe": config.timeframe,
            "from_date": from_clean,
            "to_date": to_clean,
            "applied_params": applied_params,
            "total_symbols_requested": len(target_symbols),
            "valid_symbols_count": 0,
            "portfolio_metrics": empty_portfolio_metrics,
            "portfolio_equity_curve": [],
            "asset_results": asset_results,
        }

    if len(ready_results) == 1 and valid_count == 1:
        single = ready_results[0]
        return {
            "strategy_id": strategy_id,
            "strategy_name": strategy_def["name"],
            "timeframe": config.timeframe,
            "from_date": from_clean or single["effective_from_date"],
            "to_date": to_clean or single["effective_to_date"],
            "applied_params": applied_params,
            "total_symbols_requested": len(target_symbols),
            "valid_symbols_count": 1,
            "portfolio_metrics": single["metrics"],
            "portfolio_equity_curve": single["equity_curve"],
            "asset_results": asset_results,
        }

    # Align multiple equity curves on the sorted outer union of dates using ffill().fillna(capital_k)
    all_dates_map: Dict[str, int] = {}
    for r in ready_results:
        for pt in r["equity_curve"]:
            d_str = pt["date"]
            if d_str not in all_dates_map:
                all_dates_map[d_str] = int(pt["time"])

    sorted_dates = sorted(all_dates_map.keys())
    union_index = pd.Index(sorted_dates, name="date")

    eq_df = pd.DataFrame(index=union_index)
    bal_df = pd.DataFrame(index=union_index)

    for r in ready_results:
        sym = r["symbol"]
        cap_k = float(r["metrics"]["initial_balance"])
        s_eq = pd.Series(
            {pt["date"]: float(pt["equity"]) for pt in r["equity_curve"]},
             name=sym,
        )
        s_bal = pd.Series(
            {pt["date"]: float(pt["balance"]) for pt in r["equity_curve"]},
            name=sym,
        )
        eq_df[sym] = s_eq.reindex(union_index).ffill().fillna(cap_k)
        bal_df[sym] = s_bal.reindex(union_index).ffill().fillna(cap_k)

    # Capital allocated to symbols that produced no in-range bars stays idle as cash
    idle_capital = float(initial_balance) - capital_per_symbol * len(ready_results)
    port_eq_series = eq_df.sum(axis=1) + idle_capital
    port_bal_series = bal_df.sum(axis=1) + idle_capital

    portfolio_equity_curve: List[Dict[str, Any]] = []
    peak_eq = float(initial_balance)
    for d_str in sorted_dates:
        eq_v = float(port_eq_series.loc[d_str])
        bal_v = float(port_bal_series.loc[d_str])
        if eq_v > peak_eq:
            peak_eq = eq_v
        dd_p = ((eq_v - peak_eq) / peak_eq * 100.0) if peak_eq > 0 else 0.0
        portfolio_equity_curve.append(
            {
                "time": all_dates_map[d_str],
                "date": d_str,
                "equity": _finite_float(eq_v, 0.0, 2),
                "balance": _finite_float(bal_v, 0.0, 2),
                "drawdown_pct": _finite_float(dd_p, 0.0, 2),
            }
        )

    total_realized = sum(float(r["metrics"]["realized_pnl"]) for r in ready_results)
    total_unrealized = sum(float(r["metrics"]["unrealized_pnl"]) for r in ready_results)
    all_trades: List[Dict[str, Any]] = []
    for r in ready_results:
        all_trades.extend(r["trades"])

    portfolio_metrics = _compute_summary_metrics(
        initial_balance=initial_balance,
        realized_pnl=total_realized,
        unrealized_pnl=total_unrealized,
        trades=all_trades,
        equity_curve=portfolio_equity_curve,
        timeframe=config.timeframe,
    )

    return {
        "strategy_id": strategy_id,
        "strategy_name": strategy_def["name"],
        "timeframe": config.timeframe,
        "from_date": sorted_dates[0] if sorted_dates else from_clean,
        "to_date": sorted_dates[-1] if sorted_dates else to_clean,
        "applied_params": applied_params,
        "total_symbols_requested": len(target_symbols),
        "valid_symbols_count": len(ready_results),
        "portfolio_metrics": portfolio_metrics,
        "portfolio_equity_curve": portfolio_equity_curve,
        "asset_results": asset_results,
    }
