"""
Independent Quantitative Backtester for evaluating strategy performance on historical data.
"""
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from datetime import datetime

from .config import StrategyConfig
from .strategy_base import BaseStrategy
from .sample_strategy import DarwinTrendStrategy
from .models import SignalType, TradeSignal, PositionStage


class MultiStagePosition:
    """
    Tracks lifecycle state of multi-stage position (e.g. DarwinX Zero Trader):
    FULL -> PARTIAL -> CLOSED.
    """
    def __init__(
        self,
        entry_price: float = 0.0,
        stop_loss: float = 0.0,
        units: float = 10.0,
        partial_take_profit: Optional[float] = None,
        partial_fraction: float = 0.5,
        stage: PositionStage = PositionStage.FULL,
        entry_time: Any = None,
        order_type: str = "BUY",
        realized_pnl: float = 0.0,
        **kwargs: Any,
    ):
        self.entry_price = float(entry_price)
        self.stop_loss = float(stop_loss)
        self.units = float(units)
        self.partial_take_profit = float(partial_take_profit) if partial_take_profit is not None else None
        self.partial_fraction = float(partial_fraction)
        self.stage = stage if isinstance(stage, PositionStage) else PositionStage(str(stage))
        self.entry_time = entry_time
        self.order_type = str(order_type).upper()
        self.realized_pnl = float(realized_pnl)
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def is_open(self) -> bool:
        return self.stage in (PositionStage.FULL, PositionStage.PARTIAL)


def _get_col(bar: pd.Series, *names: str, default: Any = 0.0) -> Any:
    for n in names:
        if n in bar:
            return bar[n]
        if n.lower() in bar:
            return bar[n.lower()]
        if n.upper() in bar:
            return bar[n.upper()]
    return default


class Backtester:
    def __init__(
        self,
        strategy: BaseStrategy,
        config: StrategyConfig,
        initial_balance: float = 100000.0,
        contract_multiplier: float = 100000.0,
    ):
        self.strategy = strategy
        self.config = config
        self.initial_balance = initial_balance
        self.contract_multiplier = contract_multiplier
        self.open_position: Optional[Any] = None

    def run(self, df: pd.DataFrame, initial_position: Optional[Any] = None) -> Dict[str, Any]:
        """
        Executes backtest over historical candles DataFrame.
        """
        balance = self.initial_balance
        trades = []
        open_position = initial_position if initial_position is not None else getattr(self, "open_position", None)
        if open_position is not None and getattr(open_position, "realized_pnl", 0.0):
            balance += open_position.realized_pnl
        equity_curve = [balance]

        if (
            isinstance(self.strategy, DarwinTrendStrategy)
            and open_position is None
            and len(df) > max(self.config.slow_ema_period, self.config.rsi_period, self.config.atr_period) + 10
        ):
            start_bar = max(self.config.slow_ema_period, self.config.rsi_period, self.config.atr_period) + 10
        else:
            start_bar = 0

        for i in range(start_bar, len(df)):
            sub_df = df.iloc[:i+1]
            current_bar = df.iloc[i]
            bar_open = float(_get_col(current_bar, 'open', default=0.0))
            bar_high = float(_get_col(current_bar, 'high', default=0.0))
            bar_low = float(_get_col(current_bar, 'low', default=0.0))
            bar_close = float(_get_col(current_bar, 'close', default=0.0))
            current_price = bar_close
            timestamp = current_bar['timestamp'] if 'timestamp' in current_bar else datetime.utcnow()

            # Manage existing open position
            if open_position is not None:
                if isinstance(open_position, MultiStagePosition):
                    pos = open_position
                    pos_type = pos.order_type
                    entry_price = pos.entry_price

                    if pos_type == 'BUY':
                        if pos.stage == PositionStage.FULL:
                            # 1. Intrabar SL check (SL takes precedence over TP1)
                            if bar_low <= pos.stop_loss:
                                pnl = (pos.stop_loss - entry_price) * pos.units * self.contract_multiplier
                                balance += pnl
                                pos.realized_pnl += pnl
                                pos.stage = PositionStage.CLOSED
                                trades.append({
                                    'entry_time': pos.entry_time,
                                    'exit_time': timestamp,
                                    'type': pos_type,
                                    'entry_price': entry_price,
                                    'exit_price': pos.stop_loss,
                                    'units': pos.units,
                                    'pnl': pnl,
                                    'balance': balance,
                                    'stage': PositionStage.CLOSED,
                                })
                                open_position = None
                            # 2. Check TP1
                            elif pos.partial_take_profit is not None and bar_high >= pos.partial_take_profit:
                                scale_units = pos.units * pos.partial_fraction
                                rem_units = pos.units - scale_units
                                pnl_tp1 = (pos.partial_take_profit - entry_price) * scale_units * self.contract_multiplier
                                balance += pnl_tp1
                                pos.realized_pnl += pnl_tp1
                                pos.units = rem_units
                                pos.stage = PositionStage.PARTIAL
                                pos.stop_loss = entry_price  # Ratchet to Break-Even

                                trades.append({
                                    'entry_time': pos.entry_time,
                                    'exit_time': timestamp,
                                    'type': pos_type,
                                    'entry_price': entry_price,
                                    'exit_price': pos.partial_take_profit,
                                    'units': scale_units,
                                    'pnl': pnl_tp1,
                                    'balance': balance,
                                    'stage': PositionStage.PARTIAL,
                                })

                                # Same-bar Break-Even check
                                is_bearish = bar_close < bar_open
                                same_bar_be = (is_bearish and bar_low <= entry_price) or (bar_close <= entry_price)
                                if same_bar_be:
                                    pnl_be = (entry_price - entry_price) * rem_units * self.contract_multiplier
                                    balance += pnl_be
                                    pos.realized_pnl += pnl_be
                                    pos.stage = PositionStage.CLOSED
                                    trades.append({
                                        'entry_time': pos.entry_time,
                                        'exit_time': timestamp,
                                        'type': pos_type,
                                        'entry_price': entry_price,
                                        'exit_price': entry_price,
                                        'units': rem_units,
                                        'pnl': pnl_be,
                                        'balance': balance,
                                        'stage': PositionStage.CLOSED,
                                    })
                                    open_position = None
                                else:
                                    exit_sig = self.strategy.evaluate_exit(sub_df, pos)
                                    if exit_sig in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT):
                                        exit_price = current_price
                                        pnl_macro = (exit_price - entry_price) * rem_units * self.contract_multiplier
                                        balance += pnl_macro
                                        pos.realized_pnl += pnl_macro
                                        pos.stage = PositionStage.CLOSED
                                        trades.append({
                                            'entry_time': pos.entry_time,
                                            'exit_time': timestamp,
                                            'type': pos_type,
                                            'entry_price': entry_price,
                                            'exit_price': exit_price,
                                            'units': rem_units,
                                            'pnl': pnl_macro,
                                            'balance': balance,
                                            'stage': PositionStage.CLOSED,
                                        })
                                        open_position = None

                        elif pos.stage == PositionStage.PARTIAL:
                            # 1. Intrabar SL (BE) check
                            if bar_low <= pos.stop_loss:
                                exit_price = pos.stop_loss
                                pnl = (exit_price - entry_price) * pos.units * self.contract_multiplier
                                balance += pnl
                                pos.realized_pnl += pnl
                                pos.stage = PositionStage.CLOSED
                                trades.append({
                                    'entry_time': pos.entry_time,
                                    'exit_time': timestamp,
                                    'type': pos_type,
                                    'entry_price': entry_price,
                                    'exit_price': exit_price,
                                    'units': pos.units,
                                    'pnl': pnl,
                                    'balance': balance,
                                    'stage': PositionStage.CLOSED,
                                })
                                open_position = None
                            else:
                                exit_sig = self.strategy.evaluate_exit(sub_df, pos)
                                if exit_sig in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT):
                                    exit_price = current_price
                                    pnl = (exit_price - entry_price) * pos.units * self.contract_multiplier
                                    balance += pnl
                                    pos.realized_pnl += pnl
                                    pos.stage = PositionStage.CLOSED
                                    trades.append({
                                        'entry_time': pos.entry_time,
                                        'exit_time': timestamp,
                                        'type': pos_type,
                                        'entry_price': entry_price,
                                        'exit_price': exit_price,
                                        'units': pos.units,
                                        'pnl': pnl,
                                        'balance': balance,
                                        'stage': PositionStage.CLOSED,
                                    })
                                    open_position = None

                    elif pos_type == 'SELL':
                        if pos.stage == PositionStage.FULL:
                            if bar_high >= pos.stop_loss:
                                pnl = (entry_price - pos.stop_loss) * pos.units * self.contract_multiplier
                                balance += pnl
                                pos.realized_pnl += pnl
                                pos.stage = PositionStage.CLOSED
                                trades.append({
                                    'entry_time': pos.entry_time,
                                    'exit_time': timestamp,
                                    'type': pos_type,
                                    'entry_price': entry_price,
                                    'exit_price': pos.stop_loss,
                                    'units': pos.units,
                                    'pnl': pnl,
                                    'balance': balance,
                                    'stage': PositionStage.CLOSED,
                                })
                                open_position = None
                            elif pos.partial_take_profit is not None and bar_low <= pos.partial_take_profit:
                                scale_units = pos.units * pos.partial_fraction
                                rem_units = pos.units - scale_units
                                pnl_tp1 = (entry_price - pos.partial_take_profit) * scale_units * self.contract_multiplier
                                balance += pnl_tp1
                                pos.realized_pnl += pnl_tp1
                                pos.units = rem_units
                                pos.stage = PositionStage.PARTIAL
                                pos.stop_loss = entry_price

                                trades.append({
                                    'entry_time': pos.entry_time,
                                    'exit_time': timestamp,
                                    'type': pos_type,
                                    'entry_price': entry_price,
                                    'exit_price': pos.partial_take_profit,
                                    'units': scale_units,
                                    'pnl': pnl_tp1,
                                    'balance': balance,
                                    'stage': PositionStage.PARTIAL,
                                })

                                is_bullish = bar_close > bar_open
                                same_bar_be = (is_bullish and bar_high >= entry_price) or (bar_close >= entry_price)
                                if same_bar_be:
                                    pnl_be = 0.0
                                    balance += pnl_be
                                    pos.realized_pnl += pnl_be
                                    pos.stage = PositionStage.CLOSED
                                    trades.append({
                                        'entry_time': pos.entry_time,
                                        'exit_time': timestamp,
                                        'type': pos_type,
                                        'entry_price': entry_price,
                                        'exit_price': entry_price,
                                        'units': rem_units,
                                        'pnl': pnl_be,
                                        'balance': balance,
                                        'stage': PositionStage.CLOSED,
                                    })
                                    open_position = None
                                else:
                                    exit_sig = self.strategy.evaluate_exit(sub_df, pos)
                                    if exit_sig in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT):
                                        exit_price = current_price
                                        pnl_macro = (entry_price - exit_price) * rem_units * self.contract_multiplier
                                        balance += pnl_macro
                                        pos.realized_pnl += pnl_macro
                                        pos.stage = PositionStage.CLOSED
                                        trades.append({
                                            'entry_time': pos.entry_time,
                                            'exit_time': timestamp,
                                            'type': pos_type,
                                            'entry_price': entry_price,
                                            'exit_price': exit_price,
                                            'units': rem_units,
                                            'pnl': pnl_macro,
                                            'balance': balance,
                                            'stage': PositionStage.CLOSED,
                                        })
                                        open_position = None

                        elif pos.stage == PositionStage.PARTIAL:
                            if bar_high >= pos.stop_loss:
                                exit_price = pos.stop_loss
                                pnl = (entry_price - exit_price) * pos.units * self.contract_multiplier
                                balance += pnl
                                pos.realized_pnl += pnl
                                pos.stage = PositionStage.CLOSED
                                trades.append({
                                    'entry_time': pos.entry_time,
                                    'exit_time': timestamp,
                                    'type': pos_type,
                                    'entry_price': entry_price,
                                    'exit_price': exit_price,
                                    'units': pos.units,
                                    'pnl': pnl,
                                    'balance': balance,
                                    'stage': PositionStage.CLOSED,
                                })
                                open_position = None
                            else:
                                exit_sig = self.strategy.evaluate_exit(sub_df, pos)
                                if exit_sig in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT):
                                    exit_price = current_price
                                    pnl = (entry_price - exit_price) * pos.units * self.contract_multiplier
                                    balance += pnl
                                    pos.realized_pnl += pnl
                                    pos.stage = PositionStage.CLOSED
                                    trades.append({
                                        'entry_time': pos.entry_time,
                                        'exit_time': timestamp,
                                        'type': pos_type,
                                        'entry_price': entry_price,
                                        'exit_price': exit_price,
                                        'units': pos.units,
                                        'pnl': pnl,
                                        'balance': balance,
                                        'stage': PositionStage.CLOSED,
                                    })
                                    open_position = None
                else:
                    pos_type = open_position['type']
                    sl = open_position['sl']
                    tp = open_position['tp']
                    entry_price = open_position['entry_price']
                    lots = open_position['lots']

                    closed = False
                    pnl = 0.0

                    if pos_type == 'BUY':
                        if bar_low <= sl:
                            closed = True
                            pnl = (sl - entry_price) * lots * self.contract_multiplier
                        elif bar_high >= tp:
                            closed = True
                            pnl = (tp - entry_price) * lots * self.contract_multiplier
                    elif pos_type == 'SELL':
                        if bar_high >= sl:
                            closed = True
                            pnl = (entry_price - sl) * lots * self.contract_multiplier
                        elif bar_low <= tp:
                            closed = True
                            pnl = (entry_price - tp) * lots * self.contract_multiplier

                    if closed:
                        balance += pnl
                        trades.append({
                            'entry_time': open_position['entry_time'],
                            'exit_time': timestamp,
                            'type': pos_type,
                            'entry_price': entry_price,
                            'pnl': pnl,
                            'balance': balance
                        })
                        open_position = None

            # Generate strategy signal if no open position
            if open_position is None:
                signal: TradeSignal = self.strategy.generate_signal(sub_df)
                if signal.signal_type in (SignalType.ENTER_LONG, SignalType.ENTER_SHORT):
                    is_buy = signal.signal_type == SignalType.ENTER_LONG
                    if signal.partial_take_profit is not None and signal.partial_fraction > 0.0:
                        open_position = MultiStagePosition(
                            entry_price=current_price,
                            stop_loss=signal.stop_loss,
                            units=signal.units or 10.0,
                            partial_take_profit=signal.partial_take_profit,
                            partial_fraction=signal.partial_fraction,
                            stage=PositionStage.FULL,
                            entry_time=timestamp,
                            order_type='BUY' if is_buy else 'SELL'
                        )
                    else:
                        open_position = {
                            'type': 'BUY' if is_buy else 'SELL',
                            'entry_price': current_price,
                            'sl': signal.stop_loss,
                            'tp': signal.take_profit,
                            'lots': 0.1,
                            'entry_time': timestamp
                        }

            self.open_position = open_position
            equity_curve.append(balance)

        # Performance summary metrics
        total_trades = len(trades)
        winning_trades = [t for t in trades if t['pnl'] > 0]
        losing_trades = [t for t in trades if t['pnl'] < 0]

        win_rate = (len(winning_trades) / total_trades * 100.0) if total_trades > 0 else 0.0
        total_pnl = balance - self.initial_balance

        gross_profit = sum(t['pnl'] for t in winning_trades)
        gross_loss = abs(sum(t['pnl'] for t in losing_trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)

        # Max Drawdown calculation
        eq_series = pd.Series(equity_curve)
        rolling_max = eq_series.cummax()
        drawdowns = (eq_series - rolling_max) / rolling_max * 100.0
        max_drawdown_pct = abs(drawdowns.min()) if len(drawdowns) > 0 else 0.0

        return {
            'initial_balance': self.initial_balance,
            'final_balance': balance,
            'total_pnl': total_pnl,
            'total_trades': total_trades,
            'win_rate_pct': round(win_rate, 2),
            'profit_factor': round(profit_factor, 2),
            'max_drawdown_pct': round(max_drawdown_pct, 2),
            'trades': trades,
            'equity_curve': equity_curve
        }


def generate_mock_ohlcv(bars: int = 500) -> pd.DataFrame:
    """Generates synthetic OHLCV prices for testing backtester logic."""
    np.random.seed(42)
    dates = pd.date_range(end=datetime.utcnow(), periods=bars, freq='15min')
    returns = np.random.normal(0.0001, 0.001, bars)
    price_paths = 1.0850 * np.exp(np.cumsum(returns))

    df = pd.DataFrame({
        'timestamp': dates,
        'open': price_paths,
        'high': price_paths * (1 + np.abs(np.random.normal(0, 0.0005, bars))),
        'low': price_paths * (1 - np.abs(np.random.normal(0, 0.0005, bars))),
        'close': price_paths * (1 + np.random.normal(0, 0.0003, bars)),
        'volume': np.random.randint(100, 5000, bars)
    })
    return df
