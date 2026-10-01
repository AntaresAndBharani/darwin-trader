"""
Unit test suite for Heikin-Ashi indicators and zero-lookahead MTF alignment.
Verifies HA calculation formulas, SMA, EMA, and Gherkin Scenario 6 MT5 boundary assertions.
"""
import numpy as np
import pandas as pd
import pytest

from strategy_engine.indicators import align_weekly_to_h4, compute_ema, compute_heikin_ashi, compute_sma


class TestHeikinAshiFormulas:
    """Verifies Heikin-Ashi calculation formulas and edge conditions."""

    def test_single_bar_initialization(self):
        """First bar: ha_open = (open + close)/2, ha_close = (open + high + low + close)/4."""
        df = pd.DataFrame([{"timestamp": "2025-01-06 00:00:00", "open": 100.0, "high": 110.0, "low": 90.0, "close": 104.0}])
        res = compute_heikin_ashi(df)
        assert res.loc[0, "ha_open"] == pytest.approx(102.0)
        assert res.loc[0, "ha_close"] == pytest.approx(101.0)
        assert res.loc[0, "ha_high"] == pytest.approx(110.0)
        assert res.loc[0, "ha_low"] == pytest.approx(90.0)
        assert res.loc[0, "ha_color"] == "RED"

    def test_recursive_ha_and_scenario_1_bars(self):
        """Verifies multi-bar recursive formulation using Scenario 1 weekly rates."""
        df = pd.DataFrame([
            {"timestamp": "2025-02-24 00:00:00", "open": 102.0, "high": 103.0, "low": 98.0, "close": 99.0},
            {"timestamp": "2025-03-03 00:00:00", "open": 99.0, "high": 106.0, "low": 98.5, "close": 105.0},
        ])
        res = compute_heikin_ashi(df)
        assert res.loc[0, "ha_open"] == pytest.approx(100.5)
        assert res.loc[0, "ha_close"] == pytest.approx(100.5)
        assert res.loc[0, "ha_color"] == "RED"
        assert res.loc[1, "ha_open"] == pytest.approx(100.5)
        assert res.loc[1, "ha_close"] == pytest.approx(102.125)
        assert res.loc[1, "ha_color"] == "GREEN"

    def test_empty_dataframe(self):
        """Empty input returns empty DataFrame with HA columns."""
        res = compute_heikin_ashi(pd.DataFrame(columns=["open", "high", "low", "close"]))
        assert res.empty
        for col in ["ha_open", "ha_high", "ha_low", "ha_close", "ha_color"]:
            assert col in res.columns

    def test_case_insensitivity_and_missing_columns(self):
        """Accepts TitleCase columns and raises ValueError on missing columns."""
        res = compute_heikin_ashi(pd.DataFrame([{"Open": 10.0, "High": 15.0, "Low": 10.0, "Close": 13.0}]))
        assert res.loc[0, "ha_color"] == "GREEN"
        with pytest.raises(ValueError, match="missing required OHLC"):
            compute_heikin_ashi(pd.DataFrame([{"open": 10.0, "close": 11.0}]))


class TestMovingAverages:
    """Verifies SMA and EMA mathematical implementations."""

    def test_compute_sma(self):
        series = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        sma3 = compute_sma(series, 3)
        assert pd.isna(sma3.iloc[0]) and pd.isna(sma3.iloc[1])
        assert sma3.iloc[2] == pytest.approx(20.0)
        assert sma3.iloc[4] == pytest.approx(40.0)
        with pytest.raises(ValueError, match="positive integer"):
            compute_sma(series, 0)

    def test_compute_ema(self):
        series = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        pd.testing.assert_series_equal(compute_ema(series, 3), series.ewm(span=3, adjust=False).mean())
        with pytest.raises(ValueError, match="positive integer"):
            compute_ema(series, -1)


class TestMTFAlignmentScenario6:
    """Verifies Scenario 6: MT5 Lagged Weekly Alignment Boundary & Zero Lookahead."""

    @pytest.fixture
    def weekly_rates_scenario_6(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"timestamp": "2025-02-24 00:00:00", "open": 102.0, "high": 103.0, "low": 98.0, "close": 99.0},   # W-2: RED
            {"timestamp": "2025-03-03 00:00:00", "open": 99.0, "high": 106.0, "low": 98.5, "close": 105.0},   # W-1: GREEN
            {"timestamp": "2025-03-10 00:00:00", "open": 105.0, "high": 106.0, "low": 95.0, "close": 97.0},   # W: RED
        ])

    def test_scenario_6_mt5_lagged_weekly_alignment(self, weekly_rates_scenario_6):
        """
        Scenario 6 Gherkin Assertions:
        Wednesday 2025-03-12 12:00:00 -> prev1 is GREEN (W-1), prev2 is RED (W-2)
        Friday 2025-03-14 20:00:00 -> prev1 is still GREEN (W-1), prev2 is RED (W-2)
        Monday 2025-03-17 00:00:00 -> prev1 transitions to RED (Week W), prev2 to GREEN (Week W-1)
        """
        h4_df = pd.DataFrame([
            {"timestamp": "2025-03-12 12:00:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
            {"timestamp": "2025-03-14 20:00:00", "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5},
            {"timestamp": "2025-03-17 00:00:00", "open": 98.0, "high": 99.0, "low": 97.0, "close": 97.5},
        ])
        merged = align_weekly_to_h4(h4_df, weekly_rates_scenario_6)

        assert merged.iloc[0]["w1_ha_color_prev1"] == "GREEN" and merged.iloc[0]["w1_ha_color_prev2"] == "RED"
        assert merged.iloc[1]["w1_ha_color_prev1"] == "GREEN" and merged.iloc[1]["w1_ha_color_prev2"] == "RED"
        assert merged.iloc[2]["w1_ha_color_prev1"] == "RED" and merged.iloc[2]["w1_ha_color_prev2"] == "GREEN"

    def test_zero_lookahead_warmup_and_empty_guards(self, weekly_rates_scenario_6):
        h4_early = pd.DataFrame([
            {"timestamp": "2025-02-28 12:00:00", "close": 100.0},
            {"timestamp": "2025-03-05 08:00:00", "close": 100.0},
        ])
        merged = align_weekly_to_h4(h4_early, weekly_rates_scenario_6)
        assert pd.isna(merged.iloc[0]["w1_ha_color_prev1"]) and pd.isna(merged.iloc[0]["w1_ha_color_prev2"])
        assert merged.iloc[1]["w1_ha_color_prev1"] == "RED" and pd.isna(merged.iloc[1]["w1_ha_color_prev2"])

        assert align_weekly_to_h4(pd.DataFrame(), weekly_rates_scenario_6).empty
        assert pd.isna(align_weekly_to_h4(h4_early, pd.DataFrame()).iloc[0]["w1_ha_color_prev1"])

    def test_aliases_unix_timestamps_and_unsorted(self):
        w1_df = pd.DataFrame([
            {"time": 1709510400, "open": 100.0, "high": 110.0, "low": 99.0, "close": 108.0},  # 2024-03-04 (close: 03-11)
            {"time": 1710115200, "open": 108.0, "high": 109.0, "low": 95.0, "close": 96.0},   # 2024-03-11 (close: 03-18)
        ])
        h4_df = pd.DataFrame([
            {"time": 1710244800, "close": 106.5},  # 2024-03-12 (after first close)
            {"time": 1709812800, "close": 105.5},  # 2024-03-07 (before first close)
        ])
        merged = align_weekly_to_h4(h4_df, w1_df)
        assert pd.isna(merged.iloc[0]["w1_ha_color_prev1"])
        assert merged.iloc[1]["w1_ha_color_prev1"] == "GREEN"
        assert merged.iloc[1]["w1_ha_color_prev1"] == merged.iloc[1]["ha_color_prev1"]
        with pytest.raises(KeyError, match="must contain 'timestamp' or 'time'"):
            align_weekly_to_h4(pd.DataFrame([{"close": 1.0}]), w1_df)
