"""
Reference Darwinex Zero Quantitative Strategy:
EMA Trend Crossover + RSI Momentum + ATR Volatility Dynamic SL/TP.
Designed for low drawdowns and high consistency to optimize Darwinex D-Score.
"""
import pandas as pd
from datetime import datetime
from .strategy_base import BaseStrategy
from .models import TradeSignal, SignalType
from .config import StrategyConfig


class DarwinTrendStrategy(BaseStrategy):
    def generate_signal(self, df: pd.DataFrame) -> TradeSignal:
        if len(df) < max(self.config.slow_ema_period, self.config.rsi_period, self.config.atr_period) + 5:
            return TradeSignal(
                symbol=self.config.symbol,
                signal_type=SignalType.HOLD,
                price=0.0,
                reason="Insufficient historical data"
            )

        df = df.copy()
        df['ema_fast'] = self.calculate_ema(df['close'], self.config.fast_ema_period)
        df['ema_slow'] = self.calculate_ema(df['close'], self.config.slow_ema_period)
        df['rsi'] = self.calculate_rsi(df['close'], self.config.rsi_period)
        df['atr'] = self.calculate_atr(df, self.config.atr_period)

        current = df.iloc[-1]
        previous = df.iloc[-2]

        current_price = float(current['close'])
        current_atr = float(current['atr'])

        # Bullish Crossover: Fast EMA crosses above Slow EMA & RSI > 50 & RSI < Overbought
        bullish_cross = (previous['ema_fast'] <= previous['ema_slow']) and (current['ema_fast'] > current['ema_slow'])
        bullish_rsi = (current['rsi'] > 50.0) and (current['rsi'] < self.config.rsi_overbought)

        # Bearish Crossover: Fast EMA crosses below Slow EMA & RSI < 50 & RSI > Oversold
        bearish_cross = (previous['ema_fast'] >= previous['ema_slow']) and (current['ema_fast'] < current['ema_slow'])
        bearish_rsi = (current['rsi'] < 50.0) and (current['rsi'] > self.config.rsi_oversold)

        if bullish_cross and bullish_rsi:
            sl = current_price - (current_atr * self.config.atr_multiplier)
            tp = current_price + (current_atr * self.config.atr_multiplier * 1.8)
            return TradeSignal(
                symbol=self.config.symbol,
                signal_type=SignalType.ENTER_LONG,
                price=current_price,
                stop_loss=round(sl, 5),
                take_profit=round(tp, 5),
                timestamp=datetime.utcnow(),
                reason=f"Bullish EMA Crossover (Fast={current['ema_fast']:.5f}, Slow={current['ema_slow']:.5f}, RSI={current['rsi']:.1f})"
            )

        if bearish_cross and bearish_rsi:
            sl = current_price + (current_atr * self.config.atr_multiplier)
            tp = current_price - (current_atr * self.config.atr_multiplier * 1.8)
            return TradeSignal(
                symbol=self.config.symbol,
                signal_type=SignalType.ENTER_SHORT,
                price=current_price,
                stop_loss=round(sl, 5),
                take_profit=round(tp, 5),
                timestamp=datetime.utcnow(),
                reason=f"Bearish EMA Crossover (Fast={current['ema_fast']:.5f}, Slow={current['ema_slow']:.5f}, RSI={current['rsi']:.1f})"
            )

        return TradeSignal(
            symbol=self.config.symbol,
            signal_type=SignalType.HOLD,
            price=current_price,
            timestamp=datetime.utcnow(),
            reason="No trade setup triggers met"
        )
