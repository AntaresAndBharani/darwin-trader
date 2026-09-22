"""
Pure deterministic technical calculation engine for Trading Committee.
Operates exclusively on local SQLite cached rates (zero network or MT5 imports).
Calculates EMAs, RSI, ATR, swing pivots (k=5), 60-bar Fibonacci grid,
50-bin Volume Profile (VPOC/HVN/LVN), and benchmark beta with overlap and staleness guards.
"""
import time
from typing import List, Optional, Tuple, Dict
import numpy as np
import pandas as pd

from .historical_db import HistoricalRatesDB
from .models import (
    HistoricalBar,
    HistoricalDataNotFoundError,
    CommitteeContext,
)


def compute_ema(series: pd.Series, period: int) -> Optional[float]:
    """Calculates exponential moving average for the given period."""
    if len(series) < period:
        return None
    ema = series.ewm(span=period, adjust=False).mean()
    return round(float(ema.iloc[-1]), 4)


def compute_rsi(series: pd.Series, period: int = 14) -> Optional[float]:
    """Calculates Relative Strength Index (RSI) using Wilder's smoothing."""
    if len(series) < period + 1:
        return None
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    last_gain = avg_gain.iloc[-1]
    last_loss = avg_loss.iloc[-1]
    if last_loss == 0.0:
        return 100.0 if last_gain > 0.0 else 50.0
    rs = last_gain / last_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return round(float(rsi), 2)


def compute_atr(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14) -> Optional[float]:
    """Calculates Average True Range (ATR) using Wilder's smoothing."""
    if len(closes) < period:
        return None
    prev_close = closes.shift(1)
    tr1 = highs - lows
    tr2 = (highs - prev_close).abs()
    tr3 = (lows - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(com=period - 1, adjust=False).mean()
    return round(float(atr.iloc[-1]), 4)


def identify_swing_pivots(highs: np.ndarray, lows: np.ndarray, k: int = 5) -> Tuple[List[float], List[float]]:
    """
    Identifies swing highs and lows using rolling local extrema with parameter k bars left/right.
    """
    swing_highs: List[float] = []
    swing_lows: List[float] = []
    n = len(highs)
    if n < 2 * k + 1:
        return swing_highs, swing_lows

    for i in range(k, n - k):
        val_h = highs[i]
        if val_h == np.max(highs[i - k : i + k + 1]) and val_h > highs[i - 1] and val_h > highs[i + 1]:
            swing_highs.append(round(float(val_h), 4))

        val_l = lows[i]
        if val_l == np.min(lows[i - k : i + k + 1]) and val_l < lows[i - 1] and val_l < lows[i + 1]:
            swing_lows.append(round(float(val_l), 4))

    return swing_highs, swing_lows


def compute_fibonacci_grid(bars: List[HistoricalBar], lookback: int = 60) -> Dict[str, float]:
    """
    Establishes dominant Fibonacci grid using absolute swing high and low over fixed lookback window.
    """
    window = bars[-lookback:] if len(bars) >= lookback else bars
    anchor_high = max(b.high for b in window)
    anchor_low = min(b.low for b in window)
    diff = anchor_high - anchor_low

    return {
        "anchor_high": round(float(anchor_high), 4),
        "anchor_low": round(float(anchor_low), 4),
        "0.0": round(float(anchor_low), 4),
        "0.236": round(float(anchor_low + 0.236 * diff), 4),
        "0.382": round(float(anchor_low + 0.382 * diff), 4),
        "0.5": round(float(anchor_low + 0.5 * diff), 4),
        "0.500": round(float(anchor_low + 0.5 * diff), 4),
        "0.618": round(float(anchor_low + 0.618 * diff), 4),
        "0.786": round(float(anchor_low + 0.786 * diff), 4),
        "1.0": round(float(anchor_high), 4),
        "1.272": round(float(anchor_low + 1.272 * diff), 4),
        "1.618": round(float(anchor_low + 1.618 * diff), 4),
    }


def compute_volume_profile(bars: List[HistoricalBar], bins: int = 50) -> Tuple[Optional[float], List[float], List[float]]:
    """
    Computes 50-bin Volume Profile using Typical Price (H+L+C)/3 weighted by tick_volume.
    Returns (vpoc, hvn_list, lvn_list).
    """
    if not bars:
        return None, [], []

    typical = np.array([(b.high + b.low + b.close) / 3.0 for b in bars], dtype=float)
    volumes = np.array([float(b.tick_volume) for b in bars], dtype=float)
    if np.sum(volumes) <= 0:
        volumes = np.ones_like(typical)

    counts, bin_edges = np.histogram(typical, bins=bins, weights=volumes)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
    vpoc_idx = int(np.argmax(counts))
    vpoc = round(float(bin_centers[vpoc_idx]), 4)

    hvn: List[float] = [vpoc]
    lvn: List[float] = []
    for i in range(1, len(counts) - 1):
        center_val = round(float(bin_centers[i]), 4)
        if counts[i] > counts[i - 1] and counts[i] > counts[i + 1] and counts[i] > 0:
            if center_val not in hvn:
                hvn.append(center_val)
        elif counts[i] < counts[i - 1] and counts[i] < counts[i + 1]:
            lvn.append(center_val)

    return vpoc, hvn, lvn


def compute_benchmark_beta(
    db: HistoricalRatesDB,
    symbol: str,
    asset_bars: List[HistoricalBar],
    benchmark_symbol: str = "SPY",
) -> Tuple[Optional[float], Optional[float], List[str]]:
    """
    Calculates asset beta vs benchmark using inner-join on daily timestamps.
    Enforces <20 overlap guard and missing benchmark detection.
    """
    flags: List[str] = []
    spy_raw, spy_total = db.get_rates(benchmark_symbol, timeframe="D1", limit=250, descending=True)
    if spy_total == 0 or not spy_raw:
        flags.append("[BENCHMARK: UNCACHED (STANDALONE REGIME)]")
        return None, None, flags

    spy_bars = list(reversed(spy_raw))
    asset_map = {b.time: b.close for b in asset_bars}
    spy_map = {b.time: b.close for b in spy_bars}
    common_times = sorted(set(asset_map.keys()) & set(spy_map.keys()))

    if len(common_times) < 20:
        flags.append("[BENCHMARK: INSUFFICIENT_OVERLAP]")
        return None, None, flags

    asset_closes = np.array([asset_map[t] for t in common_times], dtype=float)
    spy_closes = np.array([spy_map[t] for t in common_times], dtype=float)

    r_asset = np.diff(asset_closes) / asset_closes[:-1]
    r_spy = np.diff(spy_closes) / spy_closes[:-1]

    cov = np.cov(r_asset, r_spy)
    var_spy = cov[1, 1]
    if var_spy > 1e-12:
        beta = round(float(cov[0, 1] / var_spy), 2)
    else:
        beta = 1.0

    rs = round(float((asset_closes[-1] - asset_closes[0]) / asset_closes[0] - (spy_closes[-1] - spy_closes[0]) / spy_closes[0]), 4)
    return beta, rs, flags


class CommitteeCalculator:
    """Deterministic Technical Calculation Engine for Committee Deliberation."""

    def __init__(self, db: Optional[HistoricalRatesDB] = None):
        self.db = db or HistoricalRatesDB()

    def calculate(
        self,
        symbol: str,
        benchmark_symbol: str = "SPY",
        now: Optional[int] = None,
    ) -> CommitteeContext:
        """
        Executes pure mathematical calculations for committee technical briefing.
        Fails closed with HistoricalDataNotFoundError on cold start assets.
        """
        raw_d1, total_d1 = self.db.get_rates(symbol, timeframe="D1", limit=250, descending=True)
        if total_d1 == 0 or not raw_d1:
            raise HistoricalDataNotFoundError(f"No historical rates found for symbol '{symbol}' in database.")

        # Recency fetch: reverse descending results to obtain chronologically ascending order (time ASC)
        bars_d1 = list(reversed(raw_d1))

        # Recency verification: ensure the last bar matches the maximum timestamp in SQLite
        latest_ts = self.db.get_latest_timestamp(symbol, "D1")
        if latest_ts is not None and bars_d1[-1].time != latest_ts:
            raise ValueError(f"Recency verification failed: last bar {bars_d1[-1].time} != db latest {latest_ts}")

        # Hourly bars fetch
        raw_h1, _ = self.db.get_rates(symbol, timeframe="H1", limit=250, descending=True)
        bars_h1 = list(reversed(raw_h1)) if raw_h1 else []

        data_flags: List[str] = []

        # Staleness detection: latest bar timestamp older than 5 trading days (5 * 86400s)
        eval_time = now if now is not None else int(time.time())
        latest_bar_time = bars_d1[-1].time
        if eval_time - latest_bar_time > 5 * 86400:
            data_flags.append("[DATA_STALE]")

        # Moving Averages & Short History Degraded State
        closes = pd.Series([b.close for b in bars_d1])
        highs = pd.Series([b.high for b in bars_d1])
        lows = pd.Series([b.low for b in bars_d1])

        ema_20 = compute_ema(closes, 20)
        ema_50 = compute_ema(closes, 50)
        if len(bars_d1) < 200:
            ema_200 = None
            data_flags.append("[REGIME: SHORT_HISTORY_DEGRADED]")
        else:
            ema_200 = compute_ema(closes, 200)

        # Momentum & Volatility
        rsi_14 = compute_rsi(closes, 14)
        atr_14 = compute_atr(highs, lows, closes, 14)

        # Swing Pivots (k=5)
        swing_highs, swing_lows = identify_swing_pivots(highs.to_numpy(), lows.to_numpy(), k=5)
        swing_ceiling = max(swing_highs) if swing_highs else round(float(highs.max()), 4)
        swing_floor = min(swing_lows) if swing_lows else round(float(lows.min()), 4)

        # Dominant Fibonacci Grid (60-bar lookback)
        fib_grid = compute_fibonacci_grid(bars_d1, lookback=60)

        # Volume Profile (Typical Price on H1 bars, fallback to D1 if H1 empty)
        vp_bars = bars_h1 if bars_h1 else bars_d1
        vpoc, hvn, lvn = compute_volume_profile(vp_bars, bins=50)

        # Benchmark Beta & RS
        beta, rs, bench_flags = compute_benchmark_beta(self.db, symbol, bars_d1, benchmark_symbol=benchmark_symbol)
        data_flags.extend(bench_flags)

        return CommitteeContext(
            symbol=symbol,
            current_price=round(float(bars_d1[-1].close), 4),
            as_of_time=int(bars_d1[-1].time),
            d1_bars_count=len(bars_d1),
            h1_bars_count=len(bars_h1),
            ema_20=ema_20,
            ema_50=ema_50,
            ema_200=ema_200,
            rsi_14=rsi_14,
            atr_14=atr_14,
            swing_highs=swing_highs,
            swing_lows=swing_lows,
            swing_ceiling=swing_ceiling,
            swing_floor=swing_floor,
            fibonacci_grid=fib_grid,
            vpoc=vpoc,
            hvn=hvn,
            lvn=lvn,
            benchmark_symbol=benchmark_symbol,
            benchmark_beta=beta,
            relative_strength=rs,
            data_flags=data_flags,
        )


def calculate_committee_context(
    symbol: str,
    db: Optional[HistoricalRatesDB] = None,
    benchmark_symbol: str = "SPY",
    now: Optional[int] = None,
) -> CommitteeContext:
    """Convenience helper to compute CommitteeContext."""
    calculator = CommitteeCalculator(db=db)
    return calculator.calculate(symbol, benchmark_symbol=benchmark_symbol, now=now)
