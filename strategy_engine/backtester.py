"""
Independent Quantitative Backtester for evaluating strategy performance on historical data.
"""
from typing import List, Dict, Any
import pandas as pd
import numpy as np
from datetime import datetime

from .config import StrategyConfig
from .strategy_base import BaseStrategy
from .sample_strategy import DarwinTrendStrategy
from .models import SignalType, TradeSignal


class Backtester:
    def __init__(self, strategy: BaseStrategy, config: StrategyConfig, initial_balance: float = 100000.0):
        self.strategy = strategy
        self.config = config
        self.initial_balance = initial_balance

    def run(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Executes backtest over historical candles DataFrame.
        """
        balance = self.initial_balance
        equity_curve = [balance]
        trades = []
        open_position = None

        min_bars = max(self.config.slow_ema_period, self.config.rsi_period, self.config.atr_period) + 10

        for i in range(min_bars, len(df)):
            sub_df = df.iloc[:i+1]
            current_bar = df.iloc[i]
            current_price = float(current_bar['close'])
            timestamp = current_bar['timestamp'] if 'timestamp' in current_bar else datetime.utcnow()

            # Manage existing open position
            if open_position is not None:
                pos_type = open_position['type']
                sl = open_position['sl']
                tp = open_position['tp']
                entry_price = open_position['entry_price']
                lots = open_position['lots']

                closed = False
                pnl = 0.0

                if pos_type == 'BUY':
                    if current_bar['low'] <= sl:
                        closed = True
                        pnl = (sl - entry_price) * lots * 100000
                    elif current_bar['high'] >= tp:
                        closed = True
                        pnl = (tp - entry_price) * lots * 100000
                elif pos_type == 'SELL':
                    if current_bar['high'] >= sl:
                        closed = True
                        pnl = (entry_price - sl) * lots * 100000
                    elif current_bar['low'] <= tp:
                        closed = True
                        pnl = (entry_price - tp) * lots * 100000

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
                if signal.signal_type == SignalType.ENTER_LONG:
                    open_position = {
                        'type': 'BUY',
                        'entry_price': current_price,
                        'sl': signal.stop_loss,
                        'tp': signal.take_profit,
                        'lots': 0.1,
                        'entry_time': timestamp
                    }
                elif signal.signal_type == SignalType.ENTER_SHORT:
                    open_position = {
                        'type': 'SELL',
                        'entry_price': current_price,
                        'sl': signal.stop_loss,
                        'tp': signal.take_profit,
                        'lots': 0.1,
                        'entry_time': timestamp
                    }

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
