"""
Unit and integration tests for Deterministic Technical Calculator and Domain Models.
Covers Scenario 1 (Recency & Full Context), Scenario 6 (Cold Start Fail-Closed),
Scenario 7 (Short History Degraded Regime), and Scenario 8 (Benchmark & Staleness Guards).
"""
import pytest
import numpy as np
import pandas as pd

from strategy_engine.historical_db import HistoricalRatesDB
from strategy_engine.models import (
    HistoricalBar,
    HistoricalDataNotFoundError,
    TradeAction,
    MarketRegime,
    CommitteeVerdict,
    CommitteeContext,
    SignalType,
)
from strategy_engine.committee_calculator import (
    CommitteeCalculator,
    calculate_committee_context,
    compute_ema,
    compute_rsi,
    compute_atr,
    identify_swing_pivots,
    compute_fibonacci_grid,
    compute_volume_profile,
)


@pytest.fixture
def temp_db(tmp_path):
    """Provides a fresh isolated HistoricalRatesDB instance for testing."""
    db_file = tmp_path / "data" / "test_rates.db"
    return HistoricalRatesDB(db_path=str(db_file))


def _generate_bars(symbol: str, count: int, timeframe: str = "D1", start_time: int = 1700000000, base_price: float = 100.0):
    """Helper to generate sequential synthetic bars with realistic variations."""
    bars = []
    step = 86400 if timeframe == "D1" else 3600
    for i in range(count):
        t = start_time + i * step
        # deterministic price movement
        sine_offset = 10.0 * np.sin(i / 10.0) + (i * 0.05)
        price = base_price + sine_offset
        high = price + 1.5
        low = price - 1.2
        close = price + 0.3
        open_p = price - 0.2
        vol = 1000 + (i % 20) * 100
        bars.append(HistoricalBar(
            symbol=symbol,
            timeframe=timeframe,
            time=t,
            open=round(open_p, 2),
            high=round(high, 2),
            low=round(low, 2),
            close=round(close, 2),
            tick_volume=vol,
            spread=1,
        ))
    return bars


class TestCommitteeDomainModels:
    """Verifies domain models, enums, non-actionable verdicts, and to_trade_signal helper."""

    def test_enums(self):
        assert TradeAction.ENTER == "ENTER"
        assert TradeAction.WAIT == "WAIT"
        assert TradeAction.EXIT == "EXIT"
        assert TradeAction.SCALE_OUT == "SCALE_OUT"
        assert TradeAction.PASS == "PASS"

        assert MarketRegime.STAGE_1_ACCUMULATION == "STAGE_1_ACCUMULATION"
        assert MarketRegime.STAGE_2_MARKUP == "STAGE_2_MARKUP"
        assert MarketRegime.STAGE_3_DISTRIBUTION == "STAGE_3_DISTRIBUTION"
        assert MarketRegime.STAGE_4_DECLINE == "STAGE_4_DECLINE"
        assert MarketRegime.CHOPPY == "CHOPPY"

    def test_committee_context_model(self):
        ctx = CommitteeContext(
            symbol="AAPL",
            current_price=175.50,
            as_of_time=1700000000,
            d1_bars_count=250,
            h1_bars_count=100,
            ema_20=172.0,
            ema_50=168.0,
            ema_200=160.0,
            rsi_14=55.5,
            atr_14=3.25,
            swing_highs=[180.0, 182.5],
            swing_lows=[165.0, 168.0],
            swing_ceiling=182.5,
            swing_floor=165.0,
            fibonacci_grid={"anchor_high": 182.5, "anchor_low": 165.0},
            vpoc=174.0,
            data_flags=["[PRISTINE]"],
        )
        assert ctx.symbol == "AAPL"
        assert ctx.swing_ceiling == 182.5
        assert ctx.data_flags == ["[PRISTINE]"]
        payload = ctx.model_dump()
        assert payload["current_price"] == 175.50

    def test_committee_verdict_actionable_long_to_trade_signal(self):
        verdict = CommitteeVerdict(
            symbol="NVDA",
            action=TradeAction.ENTER,
            direction="LONG",
            regime=MarketRegime.STAGE_2_MARKUP,
            entry_price=125.50,
            stop_loss=120.00,
            take_profit_1=136.50,
            take_profit_2=145.00,
            risk_reward_ratio=2.0,
            reason="Stage 2 pullback bounce",
        )
        signal = verdict.to_trade_signal()
        assert signal.symbol == "NVDA"
        assert signal.signal_type == SignalType.ENTER_LONG
        assert signal.price == 125.50
        assert signal.stop_loss == 120.00
        assert signal.take_profit == 136.50
        assert "Stage 2 pullback bounce" in signal.reason

    def test_committee_verdict_actionable_short_to_trade_signal(self):
        verdict = CommitteeVerdict(
            symbol="INTC",
            action=TradeAction.ENTER,
            direction="SHORT",
            regime=MarketRegime.STAGE_4_DECLINE,
            entry_price=30.00,
            stop_loss=32.00,
            take_profit_1=26.00,
            risk_reward_ratio=2.0,
        )
        signal = verdict.to_trade_signal()
        assert signal.symbol == "INTC"
        assert signal.signal_type == SignalType.ENTER_SHORT
        assert signal.price == 30.00
        assert signal.stop_loss == 32.00

    def test_committee_verdict_non_actionable_wait_and_pass(self):
        # Non-actionable fields can be None
        verdict_wait = CommitteeVerdict(
            symbol="TSLA",
            action=TradeAction.WAIT,
            direction="NEUTRAL",
            reason="Awaiting consolidation breakout",
        )
        assert verdict_wait.entry_price is None
        assert verdict_wait.stop_loss is None
        assert verdict_wait.take_profit_1 is None

        sig_wait = verdict_wait.to_trade_signal()
        assert sig_wait.signal_type == SignalType.HOLD
        assert sig_wait.price == 0.0

        verdict_pass = CommitteeVerdict(
            symbol="TSLA",
            action=TradeAction.PASS,
            reason="R:R unfavorable 1:1.5",
        )
        sig_pass = verdict_pass.to_trade_signal()
        assert sig_pass.signal_type == SignalType.HOLD


class TestTechnicalIndicatorHelpers:
    """Verifies pure mathematical helper functions directly."""

    def test_indicator_helpers(self):
        series = pd.Series([10.0 + i for i in range(30)])
        ema = compute_ema(series, 20)
        assert ema is not None
        assert ema > 10.0

        # Short series fallback
        assert compute_ema(series[:10], 20) is None

        rsi = compute_rsi(series, 14)
        assert rsi is not None
        assert rsi > 50.0  # Monotonically increasing prices have high RSI
        assert compute_rsi(series[:5], 14) is None

        highs = series + 1.0
        lows = series - 1.0
        atr = compute_atr(highs, lows, series, 14)
        assert atr is not None
        assert atr > 0.0
        assert compute_atr(highs[:5], lows[:5], series[:5], 14) is None

        # Swing pivots
        h_arr = np.array([10, 11, 12, 13, 14, 20, 14, 13, 12, 11, 10], dtype=float)
        l_arr = np.array([8, 9, 10, 11, 12, 18, 12, 11, 10, 9, 8], dtype=float)
        sh, sl = identify_swing_pivots(h_arr, l_arr, k=2)
        assert 20.0 in sh

        # Fibonacci grid
        bars = [
            HistoricalBar(
                symbol="FIB_TEST",
                timeframe="D1",
                time=1700000000 + i * 86400,
                open=100.0,
                high=150.0 if i == 10 else 110.0,
                low=50.0 if i == 5 else 90.0,
                close=100.0,
                tick_volume=100,
                spread=1,
            )
            for i in range(20)
        ]
        grid = compute_fibonacci_grid(bars, lookback=20)
        assert grid["anchor_high"] == 150.0
        assert grid["anchor_low"] == 50.0
        assert grid["0.5"] == 100.0


class TestDeterministicCommitteeCalculator:
    """Verifies all BDD acceptance scenarios for the deterministic technical calculator."""

    def test_scenario_1_recency_and_full_context_generation(self, temp_db):
        """
        Scenario 1: Deterministic Technical Context Generation with Recency Verification
        Given asset "NVDA" has 1,500 cached historical daily bars in SQLite
        When the deterministic committee calculator executes for "NVDA"
        Then it fetches the latest 250 daily bars using limit=250, descending=True
        And reverses the sequence via list(reversed(raw_bars)) into ascending chronological order (time ASC)
        And asserts that the timestamp of the last element bars[-1].time equals the maximum timestamp in SQLite
        And computes exact mathematical values for EMA 20, 50, 200, RSI(14), and ATR(14)
        And identifies swing pivots using rolling local extrema with parameter k=5 bars
        And establishes the dominant Fibonacci grid using the absolute swing high and low over a 60-bar lookback window
        And calculates Volume Profile VPOC using 50-bin numpy.histogram on Typical Price (H+L+C)/3 weighted by tick_volume.
        """
        d1_bars = _generate_bars("NVDA", 1500, timeframe="D1", start_time=1600000000, base_price=100.0)
        temp_db.insert_rates(d1_bars)
        h1_bars = _generate_bars("NVDA", 250, timeframe="H1", start_time=d1_bars[-1].time - 250 * 3600, base_price=150.0)
        temp_db.insert_rates(h1_bars)

        spy_bars = _generate_bars("SPY", 300, timeframe="D1", start_time=d1_bars[-300].time, base_price=450.0)
        temp_db.insert_rates(spy_bars)

        max_ts_db = temp_db.get_latest_timestamp("NVDA", "D1")
        assert max_ts_db == d1_bars[-1].time

        calc = CommitteeCalculator(db=temp_db)
        ctx = calc.calculate("NVDA", benchmark_symbol="SPY", now=max_ts_db + 86400)

        # Recency assertions
        assert ctx.symbol == "NVDA"
        assert ctx.d1_bars_count == 250
        assert ctx.h1_bars_count == 250
        assert ctx.as_of_time == max_ts_db
        assert ctx.current_price == d1_bars[-1].close

        # Indicators computed
        assert ctx.ema_20 is not None and ctx.ema_20 > 0
        assert ctx.ema_50 is not None and ctx.ema_50 > 0
        assert ctx.ema_200 is not None and ctx.ema_200 > 0
        assert ctx.rsi_14 is not None and 0 <= ctx.rsi_14 <= 100
        assert ctx.atr_14 is not None and ctx.atr_14 > 0

        # Swing pivots (k=5)
        assert len(ctx.swing_highs) > 0
        assert len(ctx.swing_lows) > 0
        assert ctx.swing_ceiling is not None
        assert ctx.swing_floor is not None
        assert ctx.swing_ceiling >= ctx.swing_floor

        # Fibonacci grid (60-bar lookback)
        assert "anchor_high" in ctx.fibonacci_grid
        assert "anchor_low" in ctx.fibonacci_grid
        assert "0.382" in ctx.fibonacci_grid
        assert "0.5" in ctx.fibonacci_grid
        assert "0.618" in ctx.fibonacci_grid
        assert "0.786" in ctx.fibonacci_grid
        assert "1.618" in ctx.fibonacci_grid
        assert ctx.fibonacci_grid["anchor_high"] >= ctx.fibonacci_grid["anchor_low"]

        # Volume Profile
        assert ctx.vpoc is not None and ctx.vpoc > 0
        assert len(ctx.hvn) > 0

    def test_scenario_6_fail_closed_on_zero_cached_bars(self, temp_db):
        """
        Scenario 6: Pure Calculator Fail-Closed on Zero Cached Bars (Cold Start)
        Given asset "UNKNOWN_TICKER" contains zero records in `data/historical_rates.db`
        When the deterministic committee calculator executes for "UNKNOWN_TICKER"
        Then it immediately raises `HistoricalDataNotFoundError` without importing or attempting MT5 network calls
        """
        calc = CommitteeCalculator(db=temp_db)
        with pytest.raises(HistoricalDataNotFoundError) as exc_info:
            calc.calculate("UNKNOWN_TICKER")

        assert "UNKNOWN_TICKER" in str(exc_info.value)

    def test_scenario_7_degraded_regime_for_short_history_assets(self, temp_db):
        """
        Scenario 7: Degraded Regime for Short-History Assets (< 200 Bars)
        Given newly listed asset "ARM" has only 95 daily bars cached in `data/historical_rates.db`
        When the deterministic committee calculator executes for "ARM"
        Then it successfully computes EMA 20, EMA 50, RSI, and ATR
        And sets `ema_200 = None` without raising exceptions
        And flags `data_flags` with `[REGIME: SHORT_HISTORY_DEGRADED]` in the generated context.
        """
        bars = _generate_bars("ARM", 95, timeframe="D1", start_time=1700000000, base_price=50.0)
        temp_db.insert_rates(bars)

        ctx = calculate_committee_context("ARM", db=temp_db, now=bars[-1].time + 86400)

        assert ctx.d1_bars_count == 95
        assert ctx.ema_20 is not None
        assert ctx.ema_50 is not None
        assert ctx.ema_200 is None
        assert ctx.rsi_14 is not None
        assert ctx.atr_14 is not None
        assert "[REGIME: SHORT_HISTORY_DEGRADED]" in ctx.data_flags

    def test_scenario_8_benchmark_overlap_and_staleness_detection(self, temp_db):
        """
        Scenario 8: Benchmark Insufficient Overlap & Staleness Detection
        Given asset "XYZ" has daily bars where the latest bar timestamp is older than 5 trading days
        When the deterministic committee calculator evaluates the asset
        Then it flags `data_flags` with `[DATA_STALE]`
        And when overlapping trading days between "XYZ" and SPY are fewer than 20 bars
        Then it sets `benchmark_beta = None` and flags `[BENCHMARK: INSUFFICIENT_OVERLAP]`
        And when SPY is completely missing from SQLite, it flags `[BENCHMARK: UNCACHED (STANDALONE REGIME)]`.
        """
        base_time = 1700000000
        bars_xyz = _generate_bars("XYZ", 50, timeframe="D1", start_time=base_time, base_price=80.0)
        temp_db.insert_rates(bars_xyz)

        # 1. SPY completely missing from SQLite
        # Latest bar is 6 days older than now
        eval_now_stale = bars_xyz[-1].time + 6 * 86400
        ctx_no_spy = calculate_committee_context("XYZ", db=temp_db, now=eval_now_stale)
        assert "[DATA_STALE]" in ctx_no_spy.data_flags
        assert ctx_no_spy.benchmark_beta is None
        assert "[BENCHMARK: UNCACHED (STANDALONE REGIME)]" in ctx_no_spy.data_flags

        # 2. Overlap fewer than 20 bars
        # SPY only has 10 overlapping bars
        bars_spy_short = _generate_bars("SPY", 10, timeframe="D1", start_time=bars_xyz[-10].time, base_price=450.0)
        temp_db.insert_rates(bars_spy_short)

        ctx_insufficient = calculate_committee_context("XYZ", db=temp_db, now=bars_xyz[-1].time + 86400)
        assert "[DATA_STALE]" not in ctx_insufficient.data_flags
        assert ctx_insufficient.benchmark_beta is None
        assert "[BENCHMARK: INSUFFICIENT_OVERLAP]" in ctx_insufficient.data_flags

        # 3. Sufficient overlap (>= 20 bars)
        bars_spy_full = _generate_bars("SPY", 50, timeframe="D1", start_time=base_time, base_price=450.0)
        temp_db.insert_rates(bars_spy_full)

        ctx_sufficient = calculate_committee_context("XYZ", db=temp_db, now=bars_xyz[-1].time + 86400)
        assert ctx_sufficient.benchmark_beta is not None
        assert isinstance(ctx_sufficient.benchmark_beta, float)
        assert "[BENCHMARK: INSUFFICIENT_OVERLAP]" not in ctx_sufficient.data_flags
        assert "[BENCHMARK: UNCACHED (STANDALONE REGIME)]" not in ctx_sufficient.data_flags

    def test_recency_sorting_invariance(self, temp_db):
        """Asserts that regardless of DB return order, bars in calculator are chronologically ascending."""
        bars = _generate_bars("TEST_ORDER", 50, timeframe="D1", start_time=1700000000)
        temp_db.insert_rates(bars)

        calc = CommitteeCalculator(db=temp_db)
        ctx = calc.calculate("TEST_ORDER", now=bars[-1].time + 3600)
        assert ctx.as_of_time == bars[-1].time

    def test_volume_profile_zero_volume_fallback(self):
        """Volume profile should handle zero tick volume gracefully without divide-by-zero."""
        bars = [
            HistoricalBar(
                symbol="ZERO_VOL",
                timeframe="D1",
                time=1700000000 + i * 86400,
                open=100.0 + i,
                high=102.0 + i,
                low=99.0 + i,
                close=101.0 + i,
                tick_volume=0,
                spread=1,
            )
            for i in range(30)
        ]
        vpoc, hvn, lvn = compute_volume_profile(bars, bins=50)
        assert vpoc is not None
        assert len(hvn) > 0

    def test_scenario_3_uncached_benchmark_and_flag_deduplication(self, temp_db):
        """
        Scenario 3: Graceful Invariant on Uncached Benchmark & Telemetry Flag Deduplication.
        Given an asset symbol "NVDA" with 250 bars in SQLite storage and an uncached benchmark "SPY" (0 bars)
        When compute_kalman_dynamic_beta is called via the committee calculator
        Then it returns kalman_beta = None, benchmark_beta = None
        And appends the data flag "[BENCHMARK: UNCACHED (STANDALONE REGIME)]" exactly once
        And asserts data_flags.count("[BENCHMARK: UNCACHED (STANDALONE REGIME)]") == 1.
        """
        bars_nvda = _generate_bars("NVDA", 250, timeframe="D1", start_time=1700000000, base_price=120.0)
        temp_db.insert_rates(bars_nvda)

        calc = CommitteeCalculator(db=temp_db)
        ctx = calc.calculate("NVDA", benchmark_symbol="SPY", now=bars_nvda[-1].time + 86400)

        assert ctx.kalman_beta is None
        assert ctx.kalman_alpha is None
        assert ctx.benchmark_beta is None
        assert "[BENCHMARK: UNCACHED (STANDALONE REGIME)]" in ctx.data_flags
        assert ctx.data_flags.count("[BENCHMARK: UNCACHED (STANDALONE REGIME)]") == 1

    def test_committee_calculator_kalman_integration_and_overlap_deduplication(self, temp_db):
        """
        Verifies CommitteeContext populates lean Kalman scalars (kalman_beta, kalman_alpha, kalman_trend)
        and deduplicates [BENCHMARK: INSUFFICIENT_OVERLAP] flag when overlap < 20 bars.
        """
        base_time = 1700000000
        bars_nvda = _generate_bars("NVDA", 50, timeframe="D1", start_time=base_time, base_price=120.0)
        temp_db.insert_rates(bars_nvda)

        # 1. Insufficient overlap (< 20 bars) -> deduplicated flag
        bars_spy_short = _generate_bars("SPY", 10, timeframe="D1", start_time=bars_nvda[-10].time, base_price=450.0)
        temp_db.insert_rates(bars_spy_short)

        calc = CommitteeCalculator(db=temp_db)
        ctx_short = calc.calculate("NVDA", benchmark_symbol="SPY", now=bars_nvda[-1].time + 86400)
        assert ctx_short.kalman_beta is None
        assert ctx_short.benchmark_beta is None
        assert ctx_short.data_flags.count("[BENCHMARK: INSUFFICIENT_OVERLAP]") == 1

        # 2. Sufficient overlap (50 bars) -> lean Kalman scalars populated
        temp_db.clear_rates("SPY")
        bars_spy_full = _generate_bars("SPY", 50, timeframe="D1", start_time=base_time, base_price=450.0)
        temp_db.insert_rates(bars_spy_full)

        ctx_full = calc.calculate("NVDA", benchmark_symbol="SPY", now=bars_nvda[-1].time + 86400)
        assert ctx_full.kalman_beta is not None
        assert isinstance(ctx_full.kalman_beta, float)
        assert ctx_full.kalman_alpha is not None
        assert isinstance(ctx_full.kalman_alpha, float)
        assert ctx_full.kalman_trend in ("EXPANDING", "CONTRACTING", "STABLE")
        assert ctx_full.benchmark_beta is not None
        assert ctx_full.data_flags.count("[BENCHMARK: INSUFFICIENT_OVERLAP]") == 0
        assert ctx_full.data_flags.count("[BENCHMARK: UNCACHED (STANDALONE REGIME)]") == 0
