"""Unit and BDD acceptance tests for Kalman Dynamic Beta state-space engine."""
import math
import numpy as np
import pytest

from strategy_engine.indicators import compute_kalman_dynamic_beta
from strategy_engine.models import KalmanBetaResult


def _make_bars(closes, times=None, start_time=1000, step=86400):
    times = times or [start_time + i * step for i in range(len(closes))]
    return [{"time": t, "close": float(c)} for t, c in zip(times, closes)]


def test_scenario_1_deterministic_convergence():
    rng = np.random.default_rng(42)
    r_m = rng.normal(0, 0.01, 150)
    e = rng.normal(0, 0.005, 150)
    p_b = 100.0 * np.exp(np.insert(np.cumsum(r_m), 0, 0.0))
    p_a = 100.0 * np.exp(np.insert(np.cumsum(0.0 + 1.5 * r_m + e), 0, 0.0))

    res = compute_kalman_dynamic_beta(_make_bars(p_a), _make_bars(p_b))
    assert isinstance(res, KalmanBetaResult) and 1.42 <= res.current_beta <= 1.58
    assert pytest.approx(res.current_beta, abs=1e-4) == 1.4850
    assert -0.02 <= res.current_alpha <= 0.02
    assert pytest.approx(res.current_alpha, abs=1e-4) == -0.0010
    assert len(res.beta_trajectory) == 150 and all(math.isfinite(x) for x in res.beta_trajectory)


def test_scenario_2_validated_regime_adaptation():
    rng = np.random.default_rng(101)
    r_m = rng.normal(0, 0.01, 120)
    e = rng.normal(0, 0.005, 120)
    p_b = 100.0 * np.exp(np.insert(np.cumsum(r_m), 0, 0.0))
    p_a = 100.0 * np.exp(np.insert(np.cumsum(np.array([0.8] * 60 + [1.8] * 60) * r_m + e), 0, 0.0))
    bars_a, bars_b = _make_bars(p_a), _make_bars(p_b)

    res_adapt = compute_kalman_dynamic_beta(bars_a, bars_b, q_beta=1e-2, r_noise=1e-3)
    assert res_adapt.current_beta > 1.50 and pytest.approx(res_adapt.current_beta, abs=1e-4) == 1.6694
    slope = float(np.polyfit(np.arange(20), res_adapt.beta_trajectory[-20:], 1)[0])
    assert slope > 0 and pytest.approx(slope, abs=1e-6) == 0.009128
    max_step = float(np.max(np.abs(np.diff(res_adapt.beta_trajectory))))
    assert max_step < 0.25 and pytest.approx(max_step, abs=1e-4) == 0.1543

    res_def = compute_kalman_dynamic_beta(bars_a, bars_b, q_beta=1e-4)
    assert res_def.current_beta > 1.25 and pytest.approx(res_def.current_beta, abs=1e-4) == 1.3073
    assert 0.70 <= res_def.beta_trajectory[59] <= 0.90
    assert pytest.approx(res_def.beta_trajectory[59], abs=1e-4) == 0.8386


def test_scenario_3_uncached_benchmark():
    res = compute_kalman_dynamic_beta(_make_bars([100.0 + i for i in range(25)]), [])
    assert res.current_beta is None
    assert "[BENCHMARK: UNCACHED (STANDALONE REGIME)]" in res.data_flags


def test_scenario_4_insufficient_overlap():
    times = [1000 + i * 86400 for i in range(15)]
    res = compute_kalman_dynamic_beta(_make_bars([100.0] * 15, times), _make_bars([200.0] * 15, times))
    assert res.current_beta is None
    assert "[BENCHMARK: INSUFFICIENT_OVERLAP]" in res.data_flags


def test_scenario_5_corrupt_or_non_positive_prices():
    times = [1000 + i * 86400 for i in range(30)]
    for close_a, close_b in [(0.0, 100.0), (100.0, float("nan")), (-5.0, 100.0)]:
        ca, cb = [100.0] * 30, [100.0] * 30
        ca[5], cb[5] = close_a, close_b
        res = compute_kalman_dynamic_beta(_make_bars(ca, times), _make_bars(cb, times))
        assert res.current_beta is None and "[DATA_CORRUPT: NON_POSITIVE_PRICES]" in res.data_flags


def test_scenario_6_degenerate_flat_benchmark():
    times = [1000 + i * 86400 for i in range(30)]
    res = compute_kalman_dynamic_beta(_make_bars([100.0 + (i % 3) for i in range(30)], times), _make_bars([200.0] * 30, times))
    assert res.current_beta is not None and abs(res.current_beta - 1.0) < 1e-9


def test_kalman_trend_states():
    times_short = [1000 + i * 86400 for i in range(20)]
    res = compute_kalman_dynamic_beta(_make_bars([100.0 + i for i in range(20)], times_short), _make_bars([100.0] * 20, times_short))
    assert res.kalman_trend == "STABLE"

    rng = np.random.default_rng(101)
    r_m, e = rng.normal(0, 0.01, 120), rng.normal(0, 0.005, 120)
    p_b = 100.0 * np.exp(np.insert(np.cumsum(r_m), 0, 0.0))
    p_up = 100.0 * np.exp(np.insert(np.cumsum(np.array([0.8] * 60 + [1.8] * 60) * r_m + e), 0, 0.0))
    p_down = 100.0 * np.exp(np.insert(np.cumsum(np.array([1.8] * 60 + [0.8] * 60) * r_m + e), 0, 0.0))
    assert compute_kalman_dynamic_beta(_make_bars(p_up), _make_bars(p_b), q_beta=1e-2).kalman_trend == "EXPANDING"
    assert compute_kalman_dynamic_beta(_make_bars(p_down), _make_bars(p_b), q_beta=1e-2).kalman_trend == "CONTRACTING"
