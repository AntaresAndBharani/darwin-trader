"""
Unit test suite for strategy_engine.indicators.
Verifies Gherkin Scenarios 1 through 6, degenerate boundaries, and analytical benchmarks.
"""
import math
import time
import pytest
import numpy as np

from strategy_engine.indicators import (
    compute_yang_zhang_volatility,
    compute_amihud_illiquidity,
    compute_vwap_and_bands,
    compute_roll_spread,
    compute_roll_spread_metrics,
    compute_asset_metrics,
    RollSpread,
)
from strategy_engine.models import HistoricalBar, InstitutionalMetrics


def _generate_synthetic_bars(
    count: int = 25,
    base_price: float = 100.0,
    seed: int = 42,
    constant: bool = False,
    zero_volume: bool = False,
) -> list[HistoricalBar]:
    """Helper generating deterministic synthetic HistoricalBar sequence."""
    rng = np.random.default_rng(seed)
    bars = []
    current_price = base_price
    base_time = 1700000000

    for i in range(count):
        bar_time = base_time + i * 86400
        if constant:
            c_open = c_high = c_low = c_close = base_price
            vol = 0 if zero_volume else 1000
        else:
            ret = rng.normal(0.0, 0.01)
            c_open = current_price * (1.0 + rng.normal(0.0, 0.002))
            c_close = current_price * (1.0 + ret)
            c_high = max(c_open, c_close) * (1.0 + abs(rng.normal(0.0, 0.004)))
            c_low = min(c_open, c_close) * (1.0 - abs(rng.normal(0.0, 0.004)))
            vol = 0 if zero_volume else int(rng.integers(500, 2000))
            current_price = c_close

        bars.append(
            HistoricalBar(
                symbol="TEST",
                timeframe="D1",
                time=bar_time,
                open=round(float(c_open), 4),
                high=round(float(c_high), 4),
                low=round(float(c_low), 4),
                close=round(float(c_close), 4),
                tick_volume=vol,
                spread=2,
            )
        )
    return bars


# ---------------------------------------------------------------------------
# Scenario 1: Deterministic Mathematical Computation of Yang-Zhang Volatility
# ---------------------------------------------------------------------------
def test_scenario_1_yang_zhang_volatility_computation_and_flat_candles():
    """
    Given a series of at least 21 historical OHLCV daily bars sorted chronologically (time ASC)
    When compute_yang_zhang_volatility is called with window=20
    Then it accounts for overnight jumps and continuous drift
    And it multiplies by sqrt(252) to return annualized percentage volatility
    And when fed flat candles where open == high == low == close, it returns 0.0 without exception.
    """
    bars = _generate_synthetic_bars(count=21, base_price=100.0, seed=123)
    vol = compute_yang_zhang_volatility(bars, window=20)
    assert isinstance(vol, float)
    assert vol > 0.0
    assert not math.isnan(vol)
    assert not math.isinf(vol)

    # Flat candles guard
    flat_bars = _generate_synthetic_bars(count=21, base_price=50.0, constant=True)
    flat_vol = compute_yang_zhang_volatility(flat_bars, window=20)
    assert flat_vol == 0.0


# ---------------------------------------------------------------------------
# Scenario 2: Yang-Zhang Volatility Rejection on Insufficient Bars
# ---------------------------------------------------------------------------
def test_scenario_2_yang_zhang_insufficient_bars_rejection():
    """
    Given a series of fewer than 21 historical OHLCV bars
    When compute_yang_zhang_volatility is called with window=20
    Then it raises a ValueError with message "Yang-Zhang volatility requires at least window + 1 (21) chronological bars".
    """
    bars_10 = _generate_synthetic_bars(count=10)
    with pytest.raises(ValueError) as exc_info:
        compute_yang_zhang_volatility(bars_10, window=20)
    assert "Yang-Zhang volatility requires at least window + 1 (21) chronological bars" in str(exc_info.value)

    bars_20 = _generate_synthetic_bars(count=20)
    with pytest.raises(ValueError) as exc_info2:
        compute_yang_zhang_volatility(bars_20, window=20)
    assert "Yang-Zhang volatility requires at least window + 1 (21) chronological bars" in str(exc_info2.value)


# ---------------------------------------------------------------------------
# Scenario 3: Amihud Quote Revision Sensitivity Computation
# ---------------------------------------------------------------------------
def test_scenario_3_amihud_illiquidity_computation_and_zero_volume():
    """
    Given a series of at least 21 historical daily bars sorted chronologically
    When compute_amihud_illiquidity is called with window=20
    Then it calculates the mean of |ln(C_t / C_{t-1})| / tick_volume_t over all bars with tick_volume > 0
    And if all bars in the window have zero tick_volume, it returns None
    And does not raise DivisionByZeroError.
    """
    bars = _generate_synthetic_bars(count=21, base_price=100.0, seed=456)
    illiq = compute_amihud_illiquidity(bars, window=20)
    assert illiq is not None
    assert isinstance(illiq, float)
    assert illiq > 0.0

    # Hand calculation verification
    closes = [b.close for b in bars]
    vols = [b.tick_volume for b in bars]
    expected_ratios = [
        abs(math.log(closes[t] / closes[t - 1])) / vols[t]
        for t in range(1, 21)
        if vols[t] > 0
    ]
    expected_mean = float(np.mean(expected_ratios))
    assert pytest.approx(illiq, rel=1e-6) == expected_mean

    # Zero-volume degenerate guard
    zero_vol_bars = _generate_synthetic_bars(count=21, base_price=100.0, zero_volume=True)
    zero_illiq = compute_amihud_illiquidity(zero_vol_bars, window=20)
    assert zero_illiq is None


# ---------------------------------------------------------------------------
# Scenario 4: Roll Implicit Bid-Ask Spread Deterministic Computation
# ---------------------------------------------------------------------------
def test_scenario_4_roll_spread_negative_and_positive_autocovariance():
    """
    Given a sequence of close prices over a 20-bar window
    When compute_roll_spread calculates serial autocovariance Cov(ΔP_t, ΔP_{t-1})
    Then if covariance is negative, it returns (2 * sqrt(-Cov) / mean_close) * 100 as the effective spread percentage
    And if covariance is non-negative (trending market), it returns exactly 0.0
    And does not raise MathDomainError.
    """
    base_time = 1700000000

    # 1. Bouncing prices creating negative autocovariance: 100, 102, 100, 102, ...
    bouncing_closes = [100.0 if i % 2 == 0 else 102.0 for i in range(21)]
    bouncing_bars = [
        HistoricalBar(
            symbol="TEST",
            timeframe="D1",
            time=base_time + i * 86400,
            open=bouncing_closes[i],
            high=bouncing_closes[i] + 0.5,
            low=bouncing_closes[i] - 0.5,
            close=bouncing_closes[i],
            tick_volume=1000,
            spread=2,
        )
        for i in range(21)
    ]
    roll_spread = compute_roll_spread(bouncing_bars, window=20)
    assert isinstance(roll_spread, float)
    assert roll_spread > 0.0
    assert hasattr(roll_spread, "roll_spread_pct")
    assert hasattr(roll_spread, "roll_spread_absolute")
    assert roll_spread.roll_spread_pct == roll_spread
    assert roll_spread.roll_spread_absolute > 0.0

    # 2. Monotonically trending prices creating positive/zero autocovariance: 100, 101, 102, 103, ...
    trending_closes = [100.0 + i * 1.0 for i in range(21)]
    trending_bars = [
        HistoricalBar(
            symbol="TEST",
            timeframe="D1",
            time=base_time + i * 86400,
            open=trending_closes[i],
            high=trending_closes[i] + 0.5,
            low=trending_closes[i] - 0.5,
            close=trending_closes[i],
            tick_volume=1000,
            spread=2,
        )
        for i in range(21)
    ]
    roll_trending = compute_roll_spread(trending_bars, window=20)
    assert roll_trending == 0.0
    assert roll_trending.roll_spread_pct == 0.0
    assert roll_trending.roll_spread_absolute == 0.0


# ---------------------------------------------------------------------------
# Scenario 5: Rolling 20-Day VWAP, Dispersion Bands & Degenerate Guards
# ---------------------------------------------------------------------------
def test_scenario_5_vwap_and_bands_calculation_and_degenerate_guards():
    """
    Given a series of historical bars with high, low, close, and tick_volume
    When compute_vwap_and_bands is called with window=20 and num_std=2.0
    Then typical price is calculated as (high + low + close) / 3
    And VWAP is computed as sum(TP * tick_volume) / sum(tick_volume)
    And sigma is computed as sqrt(sum(tick_volume * (TP - VWAP)^2) / sum(tick_volume))
    And returns a dictionary with vwap, vwap_upper, vwap_lower, and vwap_deviation_sigmas
    And if sum(tick_volume) == 0, it returns all VWAP fields as None without raising ZeroDivisionError
    And if sigma == 0.0, vwap_upper and vwap_lower equal vwap, and vwap_deviation_sigmas returns 0.0 without raising ZeroDivisionError.
    """
    bars = _generate_synthetic_bars(count=21, base_price=100.0, seed=789)
    res = compute_vwap_and_bands(bars, window=20, num_std=2.0)
    assert res["vwap"] is not None
    assert res["vwap_upper"] is not None
    assert res["vwap_lower"] is not None
    assert res["vwap_deviation_sigmas"] is not None
    assert res["vwap_upper"] > res["vwap"]
    assert res["vwap_lower"] < res["vwap"]

    # Hand calculation verification
    selected_bars = bars[-20:]
    tps = [(b.high + b.low + b.close) / 3.0 for b in selected_bars]
    vols = [b.tick_volume for b in selected_bars]
    sum_vol = sum(vols)
    expected_vwap = sum(t * v for t, v in zip(tps, vols)) / sum_vol
    expected_var = sum(v * (t - expected_vwap) ** 2 for t, v in zip(tps, vols)) / sum_vol
    expected_sigma = math.sqrt(expected_var)
    assert pytest.approx(res["vwap"], rel=1e-6) == expected_vwap
    assert pytest.approx(res["vwap_upper"], rel=1e-6) == expected_vwap + 2.0 * expected_sigma
    assert pytest.approx(res["vwap_lower"], rel=1e-6) == expected_vwap - 2.0 * expected_sigma

    # Degenerate guard: zero volume
    zero_vol_bars = _generate_synthetic_bars(count=21, base_price=100.0, zero_volume=True)
    res_zero = compute_vwap_and_bands(zero_vol_bars, window=20)
    assert res_zero["vwap"] is None
    assert res_zero["vwap_upper"] is None
    assert res_zero["vwap_lower"] is None
    assert res_zero["vwap_deviation_sigmas"] is None

    # Degenerate guard: zero sigma (flat price action)
    flat_bars = _generate_synthetic_bars(count=21, base_price=100.0, constant=True)
    res_flat = compute_vwap_and_bands(flat_bars, window=20)
    assert res_flat["vwap"] == 100.0
    assert res_flat["vwap_upper"] == 100.0
    assert res_flat["vwap_lower"] == 100.0
    assert res_flat["vwap_deviation_sigmas"] == 0.0


# ---------------------------------------------------------------------------
# Scenario 6: Chronological Ordering Guard in Indicator Engine
# ---------------------------------------------------------------------------
def test_scenario_6_chronological_ordering_guard():
    """
    Given historical bars delivered in reverse-chronological order (time DESC)
    When passed to any compute_* function in strategy_engine.indicators
    Then the engine automatically normalizes bars to ascending chronological order (time ASC)
    And produces identical results regardless of input ordering.
    """
    bars_asc = _generate_synthetic_bars(count=25, seed=999)
    bars_desc = list(reversed(bars_asc))

    # Assert input is descending
    assert bars_desc[0].time > bars_desc[-1].time
    assert bars_asc[0].time < bars_asc[-1].time

    # 1. Yang-Zhang
    yz_asc = compute_yang_zhang_volatility(bars_asc, window=20)
    yz_desc = compute_yang_zhang_volatility(bars_desc, window=20)
    assert pytest.approx(yz_asc, rel=1e-9) == yz_desc

    # 2. Amihud
    am_asc = compute_amihud_illiquidity(bars_asc, window=20)
    am_desc = compute_amihud_illiquidity(bars_desc, window=20)
    assert pytest.approx(am_asc, rel=1e-9) == am_desc

    # 3. VWAP
    vwap_asc = compute_vwap_and_bands(bars_asc, window=20)
    vwap_desc = compute_vwap_and_bands(bars_desc, window=20)
    assert pytest.approx(vwap_asc["vwap"], rel=1e-9) == vwap_desc["vwap"]
    assert pytest.approx(vwap_asc["vwap_upper"], rel=1e-9) == vwap_desc["vwap_upper"]
    assert pytest.approx(vwap_asc["vwap_lower"], rel=1e-9) == vwap_desc["vwap_lower"]
    assert pytest.approx(vwap_asc["vwap_deviation_sigmas"], rel=1e-9) == vwap_desc["vwap_deviation_sigmas"]

    # 4. Roll Spread
    roll_asc = compute_roll_spread(bars_asc, window=20)
    roll_desc = compute_roll_spread(bars_desc, window=20)
    assert pytest.approx(roll_asc, rel=1e-9) == roll_desc


# ---------------------------------------------------------------------------
# Model Validation: InstitutionalMetrics Non-Finite Float Sanitization
# ---------------------------------------------------------------------------
def test_institutional_metrics_model_sanitizes_nan_and_inf():
    """
    Verifies that InstitutionalMetrics validator maps any non-finite floats (NaN, Inf) to None.
    """
    metrics = InstitutionalMetrics(
        symbol="EURUSD",
        insufficient_data=False,
        bars_found=21,
        bars_required=21,
        yang_zhang_vol_annualized=float("nan"),
        amihud_sensitivity=float("inf"),
        vwap=float("-inf"),
        vwap_upper=1.05,
        vwap_lower=0.95,
        vwap_deviation_sigmas=float("nan"),
        roll_spread_pct=0.038,
        roll_spread_absolute=float("nan"),
    )
    assert metrics.yang_zhang_vol_annualized is None
    assert metrics.amihud_sensitivity is None
    assert metrics.vwap is None
    assert metrics.vwap_upper == 1.05
    assert metrics.vwap_lower == 0.95
    assert metrics.vwap_deviation_sigmas is None
    assert metrics.roll_spread_pct == 0.038
    assert metrics.roll_spread_absolute is None


# ---------------------------------------------------------------------------
# Performance Benchmark: Isolated Indicator Execution < 50ms
# ---------------------------------------------------------------------------
@pytest.mark.perf
def test_indicators_performance_budget_under_50ms():
    """
    Verifies that running all 4 indicators on 21 bars finishes in < 50ms.
    """
    bars = _generate_synthetic_bars(count=21, seed=42)
    start_time = time.perf_counter()

    for _ in range(10):
        compute_yang_zhang_volatility(bars, window=20)
        compute_amihud_illiquidity(bars, window=20)
        compute_vwap_and_bands(bars, window=20)
        compute_roll_spread(bars, window=20)

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0 / 10.0
    assert elapsed_ms < 50.0, f"Average execution took {elapsed_ms:.2f} ms (budget: < 50 ms)"


# ---------------------------------------------------------------------------
# Helpers: compute_roll_spread_metrics, compute_asset_metrics & RollSpread
# ---------------------------------------------------------------------------
def test_roll_spread_metrics_and_asset_metrics_helper():
    """
    Verifies compute_roll_spread_metrics, compute_asset_metrics, and RollSpread class behavior.
    """
    bars = _generate_synthetic_bars(count=25, seed=777)

    # 1. compute_roll_spread_metrics
    pct, absolute = compute_roll_spread_metrics(bars, window=20)
    assert isinstance(pct, float)
    assert isinstance(absolute, float)

    # 2. RollSpread class
    rs = RollSpread(0.05, 0.12)
    assert rs == 0.05
    assert rs.roll_spread_pct == 0.05
    assert rs.roll_spread_absolute == 0.12

    # 3. compute_asset_metrics happy path (>= 21 bars)
    metrics = compute_asset_metrics(bars, symbol="TEST_SYM", window=20)
    assert isinstance(metrics, InstitutionalMetrics)
    assert metrics.symbol == "TEST_SYM"
    assert metrics.insufficient_data is False
    assert metrics.bars_found == 25
    assert metrics.bars_required == 21
    assert metrics.yang_zhang_vol_annualized is not None
    assert metrics.amihud_sensitivity is not None
    assert metrics.vwap is not None
    assert metrics.roll_spread_pct is not None

    # 4. compute_asset_metrics insufficient bars (< 21 bars)
    bars_short = bars[:10]
    metrics_short = compute_asset_metrics(bars_short, symbol="SHORT_SYM", window=20)
    assert metrics_short.symbol == "SHORT_SYM"
    assert metrics_short.insufficient_data is True
    assert metrics_short.bars_found == 10
    assert metrics_short.yang_zhang_vol_annualized is None

