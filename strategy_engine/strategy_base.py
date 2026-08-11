"""
Abstract Base Strategy class with indicator utilities for technical analysis.
"""
from abc import ABC, abstractmethod
from typing import List, Optional
import pandas as pd
import numpy as np

from .models import Candle, TradeSignal, SignalType
from .config import StrategyConfig


class BaseStrategy(ABC):
    def __init__(self, config: StrategyConfig):
        self.config = config

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame) -> TradeSignal:
        """
        Calculates indicators on DataFrame `df` (containing columns: open, high, low, close, volume)
        and returns a TradeSignal object.
        """
        pass

    @staticmethod
    def calculate_ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50)

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df['high']
        low = df['low']
        close = df['close']
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr.bfill()
