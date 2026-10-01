"""
DarwinX Zero Trader Strategy:
Multi-Timeframe 1W Heikin-Ashi Pullback-Reversal Filter with 4H Quad-MA Trend Alignment
and 3-Stage Position Lifecycle.
"""
from typing import Any, Optional
import pandas as pd

from strategy_engine.config import StrategyConfig
from strategy_engine.indicators import compute_ema, compute_sma
from strategy_engine.models import PositionStage, SignalType, TradeSignal
from strategy_engine.strategy_base import BaseStrategy


class DarwinXZeroTraderStrategy(BaseStrategy):
    """
    Automated multi-timeframe swing trading strategy ("DarwinX Zero trader").
    Evaluates 1W Heikin-Ashi reversal (W-2 RED, W-1 GREEN) and 4H Quad-MA stack
    (Close > 200 SMA, 21 EMA > 200 SMA, 50 SMA > 200 SMA, 100 SMA > 200 SMA).
    """

    id: str = "darwinx_zero_trader"
    name: str = "DarwinX Zero trader"
    timeframe: str = "4h"

    def __init__(self, config: Optional[StrategyConfig] = None):
        if config is None:
            config = StrategyConfig(
                strategy_name="DarwinX Zero trader",
                timeframe="4h",
            )
        super().__init__(config)
        self.id = "darwinx_zero_trader"
        self.name = "DarwinX Zero trader"
        self.timeframe = "4h"

    def generate_signal(self, df: pd.DataFrame, position: Optional[Any] = None) -> TradeSignal:
        """
        Generates trade signal from 4H bar DataFrame enriched with weekly HA indicators.
        """
        symbol = self.config.symbol if self.config else "EURUSD"
        if df.empty:
            return TradeSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                price=0.0,
                reason="Empty dataframe",
            )

        curr = df.iloc[-1]
        current_close = float(curr["close"])

        # Check flat position guard (Scenario 7)
        if position is not None:
            stage = getattr(position, "stage", None)
            if stage in (PositionStage.FULL, PositionStage.PARTIAL, "FULL", "PARTIAL"):
                return TradeSignal(
                    symbol=symbol,
                    signal_type=SignalType.HOLD,
                    price=current_close,
                    reason="Position already open (stage FULL or PARTIAL)",
                )

        # 1. Warm-up & Weekly Heikin-Ashi availability check
        prev1 = curr.get("w1_ha_color_prev1") if "w1_ha_color_prev1" in curr else curr.get("ha_color_prev1")
        prev2 = curr.get("w1_ha_color_prev2") if "w1_ha_color_prev2" in curr else curr.get("ha_color_prev2")

        if prev1 is None or prev2 is None or pd.isna(prev1) or pd.isna(prev2):
            return TradeSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                price=current_close,
                reason="Insufficient weekly history for Heikin-Ashi lookback",
            )

        # 2. Moving Average indicator resolution
        sma_200 = curr.get("sma_200") if "sma_200" in curr else (curr.get("200 SMA") if "200 SMA" in curr else None)
        sma_100 = curr.get("sma_100") if "sma_100" in curr else (curr.get("100 SMA") if "100 SMA" in curr else None)
        sma_50 = curr.get("sma_50") if "sma_50" in curr else (curr.get("50 SMA") if "50 SMA" in curr else None)
        ema_21 = curr.get("ema_21") if "ema_21" in curr else (curr.get("21 EMA") if "21 EMA" in curr else None)

        if sma_200 is None:
            if len(df) < 200:
                return TradeSignal(
                    symbol=symbol,
                    signal_type=SignalType.HOLD,
                    price=current_close,
                    reason="Insufficient history for Moving Average warm-up",
                )
            sma_200 = float(compute_sma(df["close"], 200).iloc[-1])
        else:
            sma_200 = float(sma_200)

        if sma_100 is None:
            if len(df) < 100:
                return TradeSignal(
                    symbol=symbol,
                    signal_type=SignalType.HOLD,
                    price=current_close,
                    reason="Insufficient history for Moving Average warm-up",
                )
            sma_100 = float(compute_sma(df["close"], 100).iloc[-1])
        else:
            sma_100 = float(sma_100)

        if sma_50 is None:
            if len(df) < 50:
                return TradeSignal(
                    symbol=symbol,
                    signal_type=SignalType.HOLD,
                    price=current_close,
                    reason="Insufficient history for Moving Average warm-up",
                )
            sma_50 = float(compute_sma(df["close"], 50).iloc[-1])
        else:
            sma_50 = float(sma_50)

        if ema_21 is None:
            if len(df) < 21:
                return TradeSignal(
                    symbol=symbol,
                    signal_type=SignalType.HOLD,
                    price=current_close,
                    reason="Insufficient history for Moving Average warm-up",
                )
            ema_21 = float(compute_ema(df["close"], 21).iloc[-1])
        else:
            ema_21 = float(ema_21)

        # Check for NaN in MAs
        if any(pd.isna([sma_200, sma_100, sma_50, ema_21])):
            return TradeSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                price=current_close,
                reason="Insufficient history for Moving Average warm-up",
            )

        # 3. Weekly Heikin-Ashi Watchlist Filter (Scenario 4)
        if not (str(prev2).upper() == "RED" and str(prev1).upper() == "GREEN"):
            return TradeSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                price=current_close,
                reason="Watchlist filter failed: Week-2 must be RED and Week-1 must be GREEN",
            )

        # 4. 4H Quad-MA Trend Alignment Conjunction Checks (Scenarios 5, 9)
        if current_close <= sma_200:
            return TradeSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                price=current_close,
                reason="Quad-MA stack criteria failed: Close <= 200 SMA",
            )
        if ema_21 <= sma_200:
            return TradeSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                price=current_close,
                reason="Quad-MA stack criteria failed: 21 EMA <= 200 SMA",
            )
        if sma_50 <= sma_200:
            return TradeSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                price=current_close,
                reason="Quad-MA stack criteria failed: 50 SMA <= 200 SMA",
            )
        if sma_100 <= sma_200:
            return TradeSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                price=current_close,
                reason="Quad-MA stack criteria failed: 100 SMA <= 200 SMA",
            )

        # 5. Nominal Entry Signal (10 units, SL -10%, TP1 +5%, 50% fraction)
        return TradeSignal(
            symbol=symbol,
            signal_type=SignalType.ENTER_LONG,
            price=current_close,
            stop_loss=current_close * 0.90,
            units=10.0,
            partial_take_profit=current_close * 1.05,
            partial_fraction=0.5,
            reason="DarwinX entry criteria met",
        )

    def evaluate_exit(self, sub_df: pd.DataFrame, position: Any) -> Optional[SignalType]:
        """
        Macro Heikin-Ashi exit hook:
        If position is in PARTIAL stage, and weekly HA is RED, and 4H Close < 200 SMA,
        signal EXIT_LONG.
        """
        if getattr(position, "stage", None) in (PositionStage.PARTIAL, "PARTIAL"):
            if sub_df.empty:
                return None
            curr = sub_df.iloc[-1]
            ha_color = curr.get("w1_ha_color_prev1") if "w1_ha_color_prev1" in curr else curr.get("ha_color_prev1")
            close_val = float(curr["close"])
            sma_200 = curr.get("sma_200") if "sma_200" in curr else (curr.get("200 SMA") if "200 SMA" in curr else None)
            if sma_200 is None:
                if len(sub_df) >= 200:
                    sma_200 = float(compute_sma(sub_df["close"], 200).iloc[-1])
                else:
                    return None
            else:
                sma_200 = float(sma_200)

            if str(ha_color).upper() == "RED" and close_val < sma_200:
                return SignalType.EXIT_LONG
        return None
