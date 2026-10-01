"""
Unit and BDD Scenario tests for DarwinXZeroTraderStrategy and Registry Wiring.
Covers Scenarios 4, 5, 7, 9, warm-up NaN guards, nominal signal generation, and exit evaluation.
"""
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest

from strategy_engine.backtester import Backtester, MultiStagePosition
from strategy_engine.config import StrategyConfig
from strategy_engine.models import PositionStage, SignalType
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


def test_scenario_1_nominal_two_leg_winning_trade(strategy):
    """
    Scenario 1: Nominal Two-Leg Winning Trade (Flagship Path)
    Given a backtest initialized with strategy "darwinx_zero_trader", initial balance 100000.0, and contract_multiplier 1.0
    And the historical dataset contains:
      | Bar | Time                | Timeframe | Open   | High   | Low    | Close  | HA Color | 21 EMA | 50 SMA | 100 SMA | 200 SMA |
      | W-2 | 2025-02-24 00:00:00 | 1W        | 102.00 | 103.00 | 98.00  | 99.00  | RED      | -      | -      | -       | -       |
      | W-1 | 2025-03-03 00:00:00 | 1W        | 99.00  | 106.00 | 98.50  | 105.00 | GREEN    | -      | -      | -       | -       |
      | H1  | 2025-03-10 00:00:00 | 4H        | 104.00 | 105.50 | 103.50 | 105.00 | -        | 107.00 | 106.50 | 106.00  | 100.00  |
    When the backtester processes bar H1
    Then a BUY trade signal is generated entering 10 units at 105.00
    And the position stage is "FULL" with Stop Loss at 94.50 (entry * 0.90) and TP1 at 110.25 (entry * 1.05)
    When the backtester processes bar H2 with Open 105.00, High 111.00, Low 104.50, Close 110.50
    Then 5 units (50%) are sold at TP1 price 110.25 realizing profit +$26.25
    And the position stage transitions to "PARTIAL" with remaining 5 units
    And the Stop Loss is automatically updated to Break-Even at 105.00
    When the backtester processes bar H3 with Open 110.00, High 110.00, Low 106.00, Close 106.50 and 200 SMA at 108.00
    And the aligned weekly Heikin-Ashi color w1_ha_color_prev1 is RED
    Then evaluate_exit returns SignalType.EXIT_LONG because Close 106.50 < 200 SMA 108.00
    And the remaining 5 units are closed at Market Close 106.50 realizing profit +$7.50
    And the position stage transitions to "CLOSED"
    And the cumulative realized net PnL is +$33.75 ($26.25 + $7.50) with final balance 100033.75
    """
    config = StrategyConfig(strategy_name="DarwinX Zero trader", timeframe="4h")
    backtester = Backtester(strategy, config, initial_balance=100000.0, contract_multiplier=1.0)

    df = pd.DataFrame([
        {
            "timestamp": pd.Timestamp("2025-03-10 00:00:00"),
            "open": 104.00,
            "high": 105.50,
            "low": 103.50,
            "close": 105.00,
            "w1_ha_color_prev1": "GREEN",
            "w1_ha_color_prev2": "RED",
            "21 EMA": 107.00,
            "50 SMA": 106.50,
            "100 SMA": 106.00,
            "200 SMA": 100.00,
        },
        {
            "timestamp": pd.Timestamp("2025-03-10 04:00:00"),
            "open": 105.00,
            "high": 111.00,
            "low": 104.50,
            "close": 110.50,
            "w1_ha_color_prev1": "GREEN",
            "w1_ha_color_prev2": "RED",
            "21 EMA": 107.00,
            "50 SMA": 106.50,
            "100 SMA": 106.00,
            "200 SMA": 100.00,
        },
        {
            "timestamp": pd.Timestamp("2025-03-10 08:00:00"),
            "open": 110.00,
            "high": 110.00,
            "low": 106.00,
            "close": 106.50,
            "w1_ha_color_prev1": "RED",
            "w1_ha_color_prev2": "GREEN",
            "21 EMA": 107.00,
            "50 SMA": 106.50,
            "100 SMA": 106.00,
            "200 SMA": 108.00,
        },
    ])

    res = backtester.run(df)

    assert res["total_trades"] == 2
    assert len(res["trades"]) == 2

    # Leg 1: TP1 partial scale-out
    leg1 = res["trades"][0]
    assert leg1["units"] == 5.0
    assert leg1["entry_price"] == 105.00
    assert leg1["exit_price"] == pytest.approx(110.25)
    assert leg1["pnl"] == pytest.approx(26.25)
    assert leg1["stage"] == PositionStage.PARTIAL

    # Leg 2: Macro exit at close
    leg2 = res["trades"][1]
    assert leg2["units"] == 5.0
    assert leg2["entry_price"] == 105.00
    assert leg2["exit_price"] == 106.50
    assert leg2["pnl"] == pytest.approx(7.50)
    assert leg2["stage"] == PositionStage.CLOSED

    # Final totals
    assert res["total_pnl"] == pytest.approx(33.75)
    assert res["final_balance"] == pytest.approx(100033.75)


def test_scenario_2_immediate_stop_out(strategy):
    """
    Scenario 2: Immediate Stop-Out (-10% Loss)
    Given a backtest initialized with strategy "darwinx_zero_trader", initial balance 100000.0, and contract_multiplier 1.0
    And an open FULL position of 10 units entered at 100.00 with Stop Loss at 90.00
    When the backtester processes a 4H bar with Open 95.00, High 96.00, Low 88.00, Close 89.00
    Then all 10 units are closed at Stop Loss price 90.00
    And the realized loss is -$100.00 (10 * (90.00 - 100.00) * 1.0)
    And the position stage transitions to "CLOSED"
    And no scale-out or Break-Even ratchet occurs
    """
    config = StrategyConfig(strategy_name="DarwinX Zero trader", timeframe="4h")
    backtester = Backtester(strategy, config, initial_balance=100000.0, contract_multiplier=1.0)

    pos = MultiStagePosition(
        entry_price=100.00,
        stop_loss=90.00,
        units=10.0,
        partial_take_profit=105.00,
        partial_fraction=0.5,
        stage=PositionStage.FULL,
    )

    df = pd.DataFrame([{
        "timestamp": pd.Timestamp("2025-03-10 04:00:00"),
        "open": 95.00,
        "high": 96.00,
        "low": 88.00,
        "close": 89.00,
    }])

    res = backtester.run(df, initial_position=pos)

    assert pos.stage == PositionStage.CLOSED
    assert res["total_trades"] == 1
    trade = res["trades"][0]
    assert trade["exit_price"] == 90.00
    assert trade["pnl"] == pytest.approx(-100.00)
    assert trade["units"] == 10.0
    assert res["total_pnl"] == pytest.approx(-100.00)
    assert res["final_balance"] == pytest.approx(99900.00)


def test_scenario_3_scale_out_then_break_even_exit(strategy):
    """
    Scenario 3: Scale-Out (+5%) Followed by Break-Even Stop Loss Exit
    Given an open PARTIAL position of 5 units remaining entered at 100.00 with Stop Loss ratcheted to Break-Even (100.00)
    And previous realized profit from TP1 scale-out is +$25.00 (5 units sold at 105.00)
    When the backtester processes a 4H bar with Open 102.00, High 103.00, Low 99.50, Close 100.50
    Then the remaining 5 units are closed at the Break-Even Stop Loss price 100.00
    And realized PnL for Leg 2 is $0.00
    And the position stage transitions to "CLOSED"
    And total cumulative realized trade PnL is +$25.00 with final balance 100025.00
    """
    config = StrategyConfig(strategy_name="DarwinX Zero trader", timeframe="4h")
    backtester = Backtester(strategy, config, initial_balance=100000.0, contract_multiplier=1.0)

    pos = MultiStagePosition(
        entry_price=100.00,
        stop_loss=100.00,
        units=5.0,
        partial_take_profit=105.00,
        stage=PositionStage.PARTIAL,
        realized_pnl=25.00,
    )

    df = pd.DataFrame([{
        "timestamp": pd.Timestamp("2025-03-10 08:00:00"),
        "open": 102.00,
        "high": 103.00,
        "low": 99.50,
        "close": 100.50,
    }])

    res = backtester.run(df, initial_position=pos)

    assert pos.stage == PositionStage.CLOSED
    assert res["total_trades"] == 1
    trade = res["trades"][0]
    assert trade["exit_price"] == 100.00
    assert trade["pnl"] == pytest.approx(0.00)
    assert trade["units"] == 5.0
    assert res["total_pnl"] == pytest.approx(25.00)
    assert res["final_balance"] == pytest.approx(100025.00)


def test_scenario_8_intrabar_volatility_priority(strategy):
    """
    Scenario 8: Intrabar Volatility Priority (SL Takes Precedence Over TP1)
    Given an open FULL position of 10 units entered at 100.00 with SL at 90.00 and TP1 at 105.00
    When a high-volatility bar arrives with Open 98.00, High 106.00, Low 88.00, Close 95.00
    Then the position is closed at Stop Loss price 90.00
    And no partial take-profit is executed
    """
    config = StrategyConfig(strategy_name="DarwinX Zero trader", timeframe="4h")
    backtester = Backtester(strategy, config, initial_balance=100000.0, contract_multiplier=1.0)

    pos = MultiStagePosition(
        entry_price=100.00,
        stop_loss=90.00,
        units=10.0,
        partial_take_profit=105.00,
        stage=PositionStage.FULL,
    )

    df = pd.DataFrame([{
        "timestamp": pd.Timestamp("2025-03-10 04:00:00"),
        "open": 98.00,
        "high": 106.00,
        "low": 88.00,
        "close": 95.00,
    }])

    res = backtester.run(df, initial_position=pos)

    assert pos.stage == PositionStage.CLOSED
    assert res["total_trades"] == 1
    trade = res["trades"][0]
    assert trade["exit_price"] == 90.00
    assert trade["pnl"] == pytest.approx(-100.00)
    assert trade["units"] == 10.0
    assert res["total_pnl"] == pytest.approx(-100.00)
    assert res["final_balance"] == pytest.approx(99900.00)


def test_scenario_10_same_bar_tp1_to_break_even(strategy):
    """
    Scenario 10: Same-Bar TP1 (+5%) to Break-Even Order Execution Sequence
    Given an open FULL position of 10 units entered at 100.00 with SL at 90.00 and TP1 at 105.00
    When a 4H bar arrives with Open 102.00, High 106.00, Low 99.00, Close 101.00
    Then 5 units are sold at TP1 105.00 (+5% gain, +$25.00 profit)
    And Stop Loss for the remaining 5 units is ratcheted to 100.00 (Break-Even)
    And because bar Low 99.00 <= 100.00, the remaining 5 units are closed at 100.00 ($0 PnL) on the exact same bar
    And the position stage transitions from FULL -> PARTIAL -> CLOSED in the same bar
    And total trade PnL is +$25.00
    """
    config = StrategyConfig(strategy_name="DarwinX Zero trader", timeframe="4h")
    backtester = Backtester(strategy, config, initial_balance=100000.0, contract_multiplier=1.0)

    pos = MultiStagePosition(
        entry_price=100.00,
        stop_loss=90.00,
        units=10.0,
        partial_take_profit=105.00,
        partial_fraction=0.5,
        stage=PositionStage.FULL,
    )

    df = pd.DataFrame([{
        "timestamp": pd.Timestamp("2025-03-10 04:00:00"),
        "open": 102.00,
        "high": 106.00,
        "low": 99.00,
        "close": 101.00,
    }])

    res = backtester.run(df, initial_position=pos)

    assert pos.stage == PositionStage.CLOSED
    assert res["total_trades"] == 2
    assert res["trades"][0]["exit_price"] == 105.00
    assert res["trades"][0]["pnl"] == pytest.approx(25.00)
    assert res["trades"][0]["units"] == 5.0
    assert res["trades"][0]["stage"] == PositionStage.PARTIAL

    assert res["trades"][1]["exit_price"] == 100.00
    assert res["trades"][1]["pnl"] == pytest.approx(0.00)
    assert res["trades"][1]["units"] == 5.0
    assert res["trades"][1]["stage"] == PositionStage.CLOSED

    assert res["total_pnl"] == pytest.approx(25.00)
    assert res["final_balance"] == pytest.approx(100025.00)

