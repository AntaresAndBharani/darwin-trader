"""
Deterministic indicator calculation engine.
Pure mathematical operations (NumPy) for institutional microstructure and volatility metrics:
- Yang-Zhang Drift-Free Volatility (annualized %)
- Amihud Quote Revision Sensitivity (Tick Volume Proxy)
- 20-Day Rolling VWAP & Dispersion Bands
- Roll Implicit Effective Bid-Ask Spread
"""
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

from strategy_engine.models import InstitutionalMetrics, KalmanBetaResult


class RollSpread(float):
    """
    Subclass of float representing effective spread percentage (e.g. 0.038),
    while preserving .roll_spread_pct and .roll_spread_absolute attributes.
    """
    roll_spread_pct: float
    roll_spread_absolute: float

    def __new__(cls, pct: float, absolute: float):
        instance = super().__new__(cls, pct)
        instance.roll_spread_pct = pct
        instance.roll_spread_absolute = absolute
        return instance


def _get_bar_field(bar: Any, field: str, default: Any = 0) -> Any:
    if isinstance(bar, dict):
        return bar.get(field, default)
    return getattr(bar, field, default)


def _normalize_bars(bars: Sequence[Any]) -> List[Any]:
    """Sort bars chronologically ascending by time (time ASC)."""
    if not bars:
        return []
    def get_time(b):
        return int(_get_bar_field(b, "time", 0))
    return sorted(bars, key=get_time)


def compute_yang_zhang_volatility(bars: Sequence[Any], window: int = 20) -> float:
    """
    Computes Yang-Zhang historical volatility estimator over a rolling window.
    Accounts for overnight price jumps (open to prior close) and continuous intraday drift (Rogers-Satchell).
    Returns annualized percentage volatility (multiplied by sqrt(252)).
    Guarded against zero division and flat candle series (returns 0.0).
    """
    bars_asc = _normalize_bars(bars)
    if len(bars_asc) < window + 1:
        raise ValueError(
            f"Yang-Zhang volatility requires at least window + 1 ({window + 1}) chronological bars"
        )

    selected_bars = bars_asc[-(window + 1):]
    N = window

    opens = np.array([float(_get_bar_field(b, "open")) for b in selected_bars])
    highs = np.array([float(_get_bar_field(b, "high")) for b in selected_bars])
    lows = np.array([float(_get_bar_field(b, "low")) for b in selected_bars])
    closes = np.array([float(_get_bar_field(b, "close")) for b in selected_bars])

    # Flat candle guard: when open == high == low == close across all bars
    if np.all(opens == closes) and np.all(highs == lows) and np.all(opens == highs):
        return 0.0

    c_prev = closes[:-1]
    o_curr = opens[1:]
    h_curr = highs[1:]
    l_curr = lows[1:]
    c_curr = closes[1:]

    # Positivity guard for price inputs
    if (
        np.any(c_prev <= 0)
        or np.any(o_curr <= 0)
        or np.any(h_curr <= 0)
        or np.any(l_curr <= 0)
        or np.any(c_curr <= 0)
    ):
        return 0.0

    o_t = np.log(o_curr / c_prev)
    c_t = np.log(c_curr / o_curr)
    u_t = np.log(h_curr / o_curr)
    d_t = np.log(l_curr / o_curr)

    # Sample variance with ddof=1
    v_o = float(np.var(o_t, ddof=1)) if len(o_t) > 1 else 0.0
    v_c = float(np.var(c_t, ddof=1)) if len(c_t) > 1 else 0.0

    # Rogers-Satchell variance (uncentered, divided by N)
    rs_t = u_t * (u_t - c_t) + d_t * (d_t - c_t)
    v_rs = float(np.mean(rs_t))

    # Scale factor k = 0.34 / (1.34 + (N + 1) / (N - 1))
    k = 0.34 / (1.34 + (N + 1.0) / (N - 1.0))

    # Yang-Zhang total variance
    v_yz = v_o + k * v_c + (1.0 - k) * v_rs

    if v_yz <= 0.0 or not np.isfinite(v_yz):
        return 0.0

    return float(np.sqrt(v_yz) * np.sqrt(252.0))


def compute_amihud_illiquidity(bars: Sequence[Any], window: int = 20) -> Optional[float]:
    """
    Computes Amihud Quote Revision Sensitivity (Tick Volume Proxy).
    mean(|ln(C_t / C_{t-1})| / tick_volume_t) for bars with tick_volume > 0.
    Returns None if all bars in window have zero tick_volume.
    """
    bars_asc = _normalize_bars(bars)
    if len(bars_asc) < window + 1:
        raise ValueError(
            f"Amihud illiquidity requires at least window + 1 ({window + 1}) chronological bars"
        )

    selected_bars = bars_asc[-(window + 1):]
    closes = np.array([float(_get_bar_field(b, "close")) for b in selected_bars])
    vols = np.array([int(_get_bar_field(b, "tick_volume", 0)) for b in selected_bars])

    c_prev = closes[:-1]
    c_curr = closes[1:]
    vol_curr = vols[1:]

    # Mask where tick_volume > 0
    pos_mask = vol_curr > 0
    if not np.any(pos_mask):
        return None

    valid_c_prev = c_prev[pos_mask]
    valid_c_curr = c_curr[pos_mask]
    valid_vol = vol_curr[pos_mask]

    # Non-positive price guard
    valid_price_mask = (valid_c_prev > 0) & (valid_c_curr > 0)
    if not np.any(valid_price_mask):
        return None

    valid_c_prev = valid_c_prev[valid_price_mask]
    valid_c_curr = valid_c_curr[valid_price_mask]
    valid_vol = valid_vol[valid_price_mask]

    log_returns = np.abs(np.log(valid_c_curr / valid_c_prev))
    ratios = log_returns / valid_vol

    mean_val = float(np.mean(ratios))
    if not np.isfinite(mean_val):
        return None
    return mean_val


def compute_vwap_and_bands(
    bars: Sequence[Any], window: int = 20, num_std: float = 2.0
) -> Dict[str, Optional[float]]:
    """
    Computes rolling 20-day Volume Weighted Average Price (VWAP) and dispersion bands.
    Typical price TP = (high + low + close) / 3.
    VWAP = sum(TP * tick_volume) / sum(tick_volume).
    sigma = sqrt(sum(tick_volume * (TP - VWAP)^2) / sum(tick_volume)).
    Guards:
      - If sum(tick_volume) == 0: returns all fields as None without ZeroDivisionError.
      - If sigma <= 1e-12 * |vwap|: vwap_upper = vwap, vwap_lower = vwap, vwap_deviation_sigmas = 0.0.
    """
    bars_asc = _normalize_bars(bars)
    if len(bars_asc) < window:
        raise ValueError(f"VWAP requires at least window ({window}) chronological bars")

    selected_bars = bars_asc[-window:]
    highs = np.array([float(_get_bar_field(b, "high")) for b in selected_bars])
    lows = np.array([float(_get_bar_field(b, "low")) for b in selected_bars])
    closes = np.array([float(_get_bar_field(b, "close")) for b in selected_bars])
    vols = np.array([float(_get_bar_field(b, "tick_volume", 0)) for b in selected_bars])

    sum_vol = float(np.sum(vols))
    if sum_vol <= 0.0 or not np.isfinite(sum_vol):
        return {
            "vwap": None,
            "vwap_upper": None,
            "vwap_lower": None,
            "vwap_deviation_sigmas": None,
        }

    tp = (highs + lows + closes) / 3.0
    vwap = float(np.sum(tp * vols) / sum_vol)

    variance = float(np.sum(vols * (tp - vwap) ** 2) / sum_vol)
    sigma = float(np.sqrt(max(0.0, variance)))

    last_close = float(closes[-1])

    # Guard for zero or near-zero sigma (flat / halted market)
    tolerance = 1e-12 * max(1.0, abs(vwap))
    if sigma <= tolerance:
        return {
            "vwap": vwap,
            "vwap_upper": vwap,
            "vwap_lower": vwap,
            "vwap_deviation_sigmas": 0.0,
        }

    vwap_upper = float(vwap + num_std * sigma)
    vwap_lower = float(vwap - num_std * sigma)
    vwap_deviation_sigmas = float((last_close - vwap) / sigma)

    return {
        "vwap": vwap,
        "vwap_upper": vwap_upper,
        "vwap_lower": vwap_lower,
        "vwap_deviation_sigmas": vwap_deviation_sigmas,
    }


def compute_roll_spread(bars: Sequence[Any], window: int = 20) -> float:
    """
    Computes Roll implicit effective bid-ask spread percentage.
    Calculates serial autocovariance Cov(ΔP_t, ΔP_{t-1}) over price revisions.
    If Cov < 0: returns (2 * sqrt(-Cov) / mean_close) * 100.
    If Cov >= 0: returns exactly 0.0.
    Does not raise MathDomainError.
    """
    bars_asc = _normalize_bars(bars)
    if len(bars_asc) < window + 1:
        raise ValueError(
            f"Roll spread requires at least window + 1 ({window + 1}) chronological bars"
        )

    selected_bars = bars_asc[-(window + 1):]
    closes = np.array([float(_get_bar_field(b, "close")) for b in selected_bars])

    delta_p = np.diff(closes)
    if len(delta_p) < 2:
        return RollSpread(0.0, 0.0)

    # 19 lagged pairs from 20 price changes (21 closes)
    x = delta_p[1:]
    y = delta_p[:-1]

    cov_matrix = np.cov(x, y, ddof=1)
    cov = float(cov_matrix[0, 1])

    if cov < 0.0:
        spread_abs = float(2.0 * np.sqrt(-cov))
        mean_close = float(np.mean(closes))
        spread_pct = float((spread_abs / mean_close) * 100.0) if mean_close > 0 else 0.0
        return RollSpread(spread_pct, spread_abs)
    else:
        return RollSpread(0.0, 0.0)


def compute_roll_spread_metrics(bars: Sequence[Any], window: int = 20) -> Tuple[float, float]:
    """
    Convenience helper returning (roll_spread_pct, roll_spread_absolute).
    """
    res = compute_roll_spread(bars, window=window)
    return float(getattr(res, "roll_spread_pct", res)), float(getattr(res, "roll_spread_absolute", 0.0))


def compute_asset_metrics(
    bars: Sequence[Any], symbol: str = "", window: int = 20
) -> InstitutionalMetrics:
    """
    Consolidated calculation engine producing an InstitutionalMetrics bundle.
    Automatically handles ASC normalization, insufficient bar counts, and degenerate boundaries.
    """
    bars_asc = _normalize_bars(bars)
    total_bars = len(bars_asc)
    req_bars = window + 1

    if total_bars < req_bars:
        last_time = int(_get_bar_field(bars_asc[-1], "time")) if total_bars > 0 else None
        return InstitutionalMetrics(
            symbol=symbol,
            insufficient_data=True,
            bars_found=total_bars,
            bars_required=req_bars,
            last_bar_time=last_time,
        )

    last_time = int(_get_bar_field(bars_asc[-1], "time"))
    yz_vol = compute_yang_zhang_volatility(bars_asc, window=window)
    amihud = compute_amihud_illiquidity(bars_asc, window=window)
    vwap_data = compute_vwap_and_bands(bars_asc, window=window, num_std=2.0)
    roll_pct, roll_abs = compute_roll_spread_metrics(bars_asc, window=window)

    return InstitutionalMetrics(
        symbol=symbol,
        insufficient_data=False,
        bars_found=total_bars,
        bars_required=req_bars,
        yang_zhang_vol_annualized=yz_vol,
        amihud_sensitivity=amihud,
        vwap=vwap_data.get("vwap"),
        vwap_upper=vwap_data.get("vwap_upper"),
        vwap_lower=vwap_data.get("vwap_lower"),
        vwap_deviation_sigmas=vwap_data.get("vwap_deviation_sigmas"),
        roll_spread_pct=roll_pct,
        roll_spread_absolute=roll_abs,
        last_bar_time=last_time,
    )


def compute_kalman_dynamic_beta(
    asset_bars: Sequence[Any],
    benchmark_bars: Sequence[Any],
    q_alpha: float = 1e-5,
    q_beta: float = 1e-4,
    r_noise: float = 1e-3,
    p0: float = 1.0,
) -> KalmanBetaResult:
    """
    Computes Kalman Filter Dynamic Beta (beta_t) and Alpha (alpha_t) against a benchmark.
    Uses pure scalar float Joseph-stabilized covariance recursion for zero-lag adaptation.
    """
    flags: List[str] = []
    if benchmark_bars is None or len(benchmark_bars) == 0:
        flags.append("[BENCHMARK: UNCACHED (STANDALONE REGIME)]")
        return KalmanBetaResult(data_flags=flags)
    if asset_bars is None or len(asset_bars) == 0:
        flags.append("[BENCHMARK: INSUFFICIENT_OVERLAP]")
        return KalmanBetaResult(data_flags=flags)

    def _to_map(bars: Sequence[Any]) -> Dict[int, float]:
        m: Dict[int, float] = {}
        for idx, b in enumerate(_normalize_bars(bars)):
            try:
                m[int(_get_bar_field(b, "time", idx))] = float(_get_bar_field(b, "close", b))
            except (ValueError, TypeError):
                m[idx] = float("nan")
        return m

    asset_map, bench_map = _to_map(asset_bars), _to_map(benchmark_bars)
    common_times = sorted(set(asset_map.keys()) & set(bench_map.keys()))
    if len(common_times) < 20:
        flags.append("[BENCHMARK: INSUFFICIENT_OVERLAP]")
        return KalmanBetaResult(data_flags=flags)

    asset_closes = [asset_map[t] for t in common_times]
    bench_closes = [bench_map[t] for t in common_times]
    if any(not (math.isfinite(p) and p > 0.0) for p in asset_closes + bench_closes):
        flags.append("[DATA_CORRUPT: NON_POSITIVE_PRICES]")
        return KalmanBetaResult(data_flags=flags)

    r_asset = [math.log(asset_closes[i] / asset_closes[i - 1]) for i in range(1, len(asset_closes))]
    r_bench = [math.log(bench_closes[i] / bench_closes[i - 1]) for i in range(1, len(bench_closes))]

    a, b = 0.0, 1.0
    p00, p01, p11 = float(p0), 0.0, float(p0)
    beta_trajectory: List[float] = []
    f_val = p00 + r_noise

    for y, x in zip(r_asset, r_bench):
        p00 += q_alpha
        p11 += q_beta
        v = y - (a + b * x)
        f_val = p00 + 2.0 * x * p01 + (x * x) * p11 + r_noise
        k0, k1 = (p00 + x * p01) / f_val, (p01 + x * p11) / f_val
        a += k0 * v
        b += k1 * v
        beta_trajectory.append(b)

        a00, a01, a10, a11 = 1.0 - k0, -k0 * x, -k1, 1.0 - k1 * x
        m00, m01 = a00 * p00 + a01 * p01, a00 * p01 + a01 * p11
        m10, m11 = a10 * p00 + a11 * p01, a10 * p01 + a11 * p11
        p00 = m00 * a00 + m01 * a01 + (k0 * k0) * r_noise
        p01 = 0.5 * (m00 * a10 + m01 * a11 + m10 * a00 + m11 * a01) + (k0 * k1) * r_noise
        p11 = m10 * a10 + m11 * a11 + (k1 * k1) * r_noise

    kalman_trend = "STABLE"
    if len(beta_trajectory) >= 21:
        delta_beta = beta_trajectory[-1] - beta_trajectory[-21]
        if delta_beta > 0.05:
            kalman_trend = "EXPANDING"
        elif delta_beta < -0.05:
            kalman_trend = "CONTRACTING"

    return KalmanBetaResult(
        current_beta=b,
        current_alpha=a,
        kalman_trend=kalman_trend,
        prediction_error_variance=f_val,
        beta_trajectory=beta_trajectory,
        data_flags=flags,
    )


