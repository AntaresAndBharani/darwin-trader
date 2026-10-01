"""
Unit and BDD Scenario tests for DarwinXZeroTraderStrategy and Registry Wiring.
Covers Scenarios 4, 5, 7, 9, warm-up NaN guards, nominal signal generation, and exit evaluation.
"""
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest

from strategy_engine.models import PositionStage, SignalType, TradeSignal
from strategy_engine.strategies.darwinx_zero_trader import DarwinXZeroTraderStrategy
from strategy_engine.strategy_registry import STRATEGY_REGISTRY, get_strategy, list_strategies


@pytest.fixture
def strategy():
    return DarwinXZeroTraderStrategy()


def test_strategy_metadata_and_registry_wiring(strategy):
    """Verifies strategy metadata and registration in STRATEGY_REGISTRY."""
    assert strategy.id == "darwinx_zero_trader"
    assert strategy.name == "DarwinX Zero trader"
    assert strategy.timeframe == "4h"

    assert "darwinx_zero_trader" in STRATEGY_REGISTRY
    assert get_strategy("darwinx_zero_trader") is DarwinXZeroTraderStrategy
    assert "darwinx_zero_trader" in list_strategies()


def test_warmup_nan_guard_weekly_indicators(strategy):
    """Verifies that missing or NaN weekly Heikin-Ashi indicators return HOLD."""
    # Empty DataFrame
    sig_empty = strategy.generate_signal(pd.DataFrame())
    assert sig_empty.signal_type == SignalType.HOLD
    assert "Empty" in sig_empty.reason

    # Missing weekly columns
    df_no_w1 = pd.DataFrame([{
        "close": 105.0,
        "200 SMA": 100.0,
        "100 SMA": 102.0,
        "50 SMA": 103.0,
        "21 EMA": 104.0,
    }])
    sig_no_w1 = strategy.generate_signal(df_no_w1)
    assert sig_no_w1.signal_type == SignalType.HOLD
    assert sig_no_w1.reason == "Insufficient weekly history for Heikin-Ashi lookback"

    # NaN weekly indicators
    df_nan_w1 = pd.DataFrame([{
        "close": 105.0,
        "w1_ha_color_prev1": np.nan,
        "w1_ha_color_prev2": "RED",
        "200 SMA": 100.0,
        "100 SMA": 102.0,
        "50 SMA": 103.0,
        "21 EMA": 104.0,
    }])
    sig_nan = strategy.generate_signal(df_nan_w1)
    assert sig_nan.signal_type == SignalType.HOLD
    assert sig_nan.reason == "Insufficient weekly history for Heikin-Ashi lookback"


def test_warmup_moving_averages(strategy):
    """Verifies that insufficient raw bar history for MA calculation returns HOLD."""
    df_short = pd.DataFrame({
        "close": [100.0 + i for i in range(30)],
        "w1_ha_color_prev1": ["GREEN"] * 30,
        "w1_ha_color_prev2": ["RED"] * 30,
    })
    sig = strategy.generate_signal(df_short)
    assert sig.signal_type == SignalType.HOLD
    assert "Insufficient history for Moving Average" in sig.reason


def test_scenario_4_weekly_ha_rejection(strategy):
    """
    Scenario 4: Rejection by Weekly Heikin-Ashi Watchlist Filter.
    Given Close > 200 SMA and 21 EMA > 50 SMA > 100 SMA > 200 SMA,
    And w1_ha_color_prev2 is GREEN and w1_ha_color_prev1 is GREEN,
    Then signal is HOLD with 'Watchlist filter failed: Week-2 must be RED and Week-1 must be GREEN'.
    """
    df = pd.DataFrame([{
        "close": 105.00,
        "200 SMA": 100.00,
        "100 SMA": 101.00,
        "50 SMA": 102.00,
        "21 EMA": 103.00,
        "w1_ha_color_prev2": "GREEN",
        "w1_ha_color_prev1": "GREEN",
    }])
    signal = strategy.generate_signal(df)
    assert signal.signal_type == SignalType.HOLD
    assert signal.reason == "Watchlist filter failed: Week-2 must be RED and Week-1 must be GREEN"


def test_scenario_5_quad_ma_rejection_50_sma(strategy):
    """
    Scenario 5: Rejection by 4H Quad-MA Trend Alignment.
    Given w1_ha_color_prev2 is RED and w1_ha_color_prev1 is GREEN,
    And Close 105.00 > 200 SMA 100.00, 21 EMA 103.00 > 200 SMA, 100 SMA 101.00 > 200 SMA,
    But 50 SMA is 99.00 (< 200 SMA 100.00),
    Then signal is HOLD with 'Quad-MA stack criteria failed: 50 SMA <= 200 SMA'.
    """
    df = pd.DataFrame([{
        "close": 105.00,
        "200 SMA": 100.00,
        "100 SMA": 101.00,
        "50 SMA": 99.00,
        "21 EMA": 103.00,
        "w1_ha_color_prev2": "RED",
        "w1_ha_color_prev1": "GREEN",
    }])
    signal = strategy.generate_signal(df)
    assert signal.signal_type == SignalType.HOLD
    assert signal.reason == "Quad-MA stack criteria failed: 50 SMA <= 200 SMA"


def test_scenario_9_quad_ma_rejection_100_sma(strategy):
    """
    Scenario 9: 4H Quad-MA Conjunction Failure — Single MA Misalignment.
    Given W-2 RED and W-1 GREEN,
    And Close > 200 SMA, 21 EMA > 200 SMA, and 50 SMA > 200 SMA,
    But 100 SMA is 98.00 (<= 200 SMA 100.00),
    Then signal is HOLD with 'Quad-MA stack criteria failed: 100 SMA <= 200 SMA'.
    """
    df = pd.DataFrame([{
        "close": 105.00,
        "200 SMA": 100.00,
        "100 SMA": 98.00,
        "50 SMA": 102.00,
        "21 EMA": 103.00,
        "w1_ha_color_prev2": "RED",
        "w1_ha_color_prev1": "GREEN",
    }])
    signal = strategy.generate_signal(df)
    assert signal.signal_type == SignalType.HOLD
    assert signal.reason == "Quad-MA stack criteria failed: 100 SMA <= 200 SMA"


def test_quad_ma_rejection_close_and_21_ema(strategy):
    """Verifies MA stack rejection when Close <= 200 SMA or 21 EMA <= 200 SMA."""
    # Close <= 200 SMA
    df_close = pd.DataFrame([{
        "close": 99.00,
        "200 SMA": 100.00,
        "100 SMA": 101.00,
        "50 SMA": 102.00,
        "21 EMA": 103.00,
        "w1_ha_color_prev2": "RED",
        "w1_ha_color_prev1": "GREEN",
    }])
    sig_close = strategy.generate_signal(df_close)
    assert sig_close.signal_type == SignalType.HOLD
    assert sig_close.reason == "Quad-MA stack criteria failed: Close <= 200 SMA"

    # 21 EMA <= 200 SMA
    df_ema = pd.DataFrame([{
        "close": 105.00,
        "200 SMA": 100.00,
        "100 SMA": 101.00,
        "50 SMA": 102.00,
        "21 EMA": 99.50,
        "w1_ha_color_prev2": "RED",
        "w1_ha_color_prev1": "GREEN",
    }])
    sig_ema = strategy.generate_signal(df_ema)
    assert sig_ema.signal_type == SignalType.HOLD
    assert sig_ema.reason == "Quad-MA stack criteria failed: 21 EMA <= 200 SMA"


def test_scenario_7_flat_position_guard(strategy):
    """
    Scenario 7: Flat Position Guard & No Over-Accumulation.
    Given an open position (stage FULL or PARTIAL),
    When subsequent 4H bars fulfill all weekly and 4H entry criteria,
    Then strategy does not emit additional ENTER_LONG signals and returns HOLD.
    """
    df = pd.DataFrame([{
        "close": 105.00,
        "200 SMA": 100.00,
        "100 SMA": 101.00,
        "50 SMA": 102.00,
        "21 EMA": 103.00,
        "w1_ha_color_prev2": "RED",
        "w1_ha_color_prev1": "GREEN",
    }])

    # Guard with FULL stage position
    pos_full = SimpleNamespace(stage=PositionStage.FULL, units=10.0)
    sig_full = strategy.generate_signal(df, position=pos_full)
    assert sig_full.signal_type == SignalType.HOLD
    assert "Position already open" in sig_full.reason

    # Guard with PARTIAL stage position
    pos_partial = SimpleNamespace(stage=PositionStage.PARTIAL, units=5.0)
    sig_partial = strategy.generate_signal(df, position=pos_partial)
    assert sig_partial.signal_type == SignalType.HOLD
    assert "Position already open" in sig_partial.reason

    # No guard when CLOSED or None -> emits ENTER_LONG
    pos_closed = SimpleNamespace(stage=PositionStage.CLOSED, units=0.0)
    sig_closed = strategy.generate_signal(df, position=pos_closed)
    assert sig_closed.signal_type == SignalType.ENTER_LONG


def test_nominal_buy_signal_generation(strategy):
    """Verifies valid BUY trade signal generation with units, SL, and TP1."""
    df = pd.DataFrame([{
        "close": 105.00,
        "200 SMA": 100.00,
        "100 SMA": 106.00,
        "50 SMA": 106.50,
        "21 EMA": 107.00,
        "w1_ha_color_prev2": "RED",
        "w1_ha_color_prev1": "GREEN",
    }])
    signal = strategy.generate_signal(df)
    assert signal.signal_type == SignalType.ENTER_LONG
    assert signal.type == SignalType.ENTER_LONG
    assert signal.price == 105.00
    assert signal.stop_loss == pytest.approx(94.50)
    assert signal.units == 10.0
    assert signal.partial_take_profit == pytest.approx(110.25)
    assert signal.partial_fraction == 0.5
    assert signal.reason == "DarwinX entry criteria met"


def test_evaluate_exit_macro_conditions(strategy):
    """Verifies evaluate_exit macro rules for PARTIAL and FULL position stages."""
    df_exit = pd.DataFrame([{
        "close": 106.50,
        "sma_200": 108.00,
        "w1_ha_color_prev1": "RED",
    }])

    # Stage PARTIAL + RED weekly HA + Close < 200 SMA -> EXIT_LONG
    pos_partial = SimpleNamespace(stage=PositionStage.PARTIAL)
    assert strategy.evaluate_exit(df_exit, pos_partial) == SignalType.EXIT_LONG

    # Close >= 200 SMA -> None (hold)
    df_no_exit_close = pd.DataFrame([{
        "close": 109.00,
        "sma_200": 108.00,
        "w1_ha_color_prev1": "RED",
    }])
    assert strategy.evaluate_exit(df_no_exit_close, pos_partial) is None

    # Weekly HA is GREEN -> None (hold)
    df_no_exit_ha = pd.DataFrame([{
        "close": 106.50,
        "sma_200": 108.00,
        "w1_ha_color_prev1": "GREEN",
    }])
    assert strategy.evaluate_exit(df_no_exit_ha, pos_partial) is None

    # Stage FULL -> None (macro exit only applies to PARTIAL stage)
    pos_full = SimpleNamespace(stage=PositionStage.FULL)
    assert strategy.evaluate_exit(df_exit, pos_full) is None
