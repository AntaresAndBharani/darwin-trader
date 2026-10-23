"""
Unit and BDD Scenario tests for Yahoo Finance Strategy Lifecycle & Backtesting Engine.
Covers strategy catalog, parameter validation, zero-lookahead Weekly Heikin-Ashi alignment,
single-asset MTM backtesting (`darwin_trend` and `darwinx_zero_trader`), warm-up window
handling, and multi-asset/sector portfolio aggregation.
"""
from datetime import date, timedelta
import math
import pandas as pd
import pytest

from strategy_engine.yahoo_backtester import (
    enrich_weekly_heikin_ashi,
    get_yahoo_strategies_catalog,
    run_single_asset_yahoo_backtest,
    run_yahoo_portfolio_backtest,
    validate_and_build_strategy_config,
)
from strategy_engine.yahoo_db import YahooFinanceDB


@pytest.fixture
def temp_yahoo_db(tmp_path):
    db_file = tmp_path / "test_yahoo_strategy.db"
    db = YahooFinanceDB(db_path=str(db_file))
    return db


def _seed_synthetic_stock_history(
    db: YahooFinanceDB,
    symbol: str = "AAPL",
    market: str = "NASDAQ",
    sector: str = "Technology",
    days: int = 260,
    start_date: date = date(2024, 1, 2),
) -> None:
    """Seeds deterministic oscillatory + trending daily bars into YahooFinanceDB."""
    db.upsert_tickers(
        [
            {
                "symbol": symbol,
                "name": f"{symbol} Corp",
                "market": market,
                "sector": sector,
                "industry": "Software",
                "active": True,
            }
        ]
    )
    rows = []
    cur = start_date
    price = 100.0
    for i in range(days):
        # Skip weekends
        while cur.weekday() >= 5:
            cur += timedelta(days=1)
        # Deterministic wave + upward drift so EMA crossovers and HA pullbacks occur
        wave = math.sin(i / 6.0) * 4.5 + (i * 0.18)
        c = round(max(10.0, price + wave), 2)
        o = round(c - math.cos(i / 5.0) * 1.2, 2)
        h = round(max(o, c) + 1.8, 2)
        l_val = round(min(o, c) - 1.8, 2)
        rows.append(
            {
                "symbol": symbol,
                "date": cur.strftime("%Y-%m-%d"),
                "open": o,
                "high": h,
                "low": l_val,
                "close": c,
                "volume": 1000000 + (i * 1000),
            }
        )
        cur += timedelta(days=1)
    db.upsert_stock_prices(rows)


def test_yahoo_strategies_catalog_schema():
    """Verifies FR-001 strategy catalog and parameter specifications."""
    catalog = get_yahoo_strategies_catalog()
    assert len(catalog) == 2
    ids = [s["id"] for s in catalog]
    assert ids == ["darwin_trend", "darwinx_zero_trader"]

    for s in catalog:
        assert s["supported_timeframes"] == ["D1", "W1", "MN1"]
        assert s["default_timeframe"] == "D1"
        assert len(s["parameters"]) >= 7
        for p in s["parameters"]:
            assert "key" in p
            assert "label" in p
            assert p["type"] in ("int", "float")
            assert p["min_value"] <= p["default"] <= p["max_value"]


def test_parameter_and_date_validation_guards():
    """Verifies edge-case validation guards for strategy_id, timeframe, dates, and bounds."""
    with pytest.raises(ValueError, match="Unknown strategy_id"):
        validate_and_build_strategy_config(strategy_id="non_existent")

    with pytest.raises(ValueError, match="Unsupported timeframe"):
        validate_and_build_strategy_config(strategy_id="darwin_trend", timeframe="M5")

    with pytest.raises(ValueError, match="initial_balance"):
        validate_and_build_strategy_config(strategy_id="darwin_trend", initial_balance=0)

    with pytest.raises(ValueError, match="risk_per_trade_pct"):
        validate_and_build_strategy_config(strategy_id="darwin_trend", risk_per_trade_pct=150.0)

    with pytest.raises(ValueError, match="from_date .* cannot be after to_date"):
        validate_and_build_strategy_config(
            strategy_id="darwin_trend",
            from_date="2025-06-01",
            to_date="2024-01-01",
        )

    with pytest.raises(ValueError, match="fast_ema_period must be strictly less"):
        validate_and_build_strategy_config(
            strategy_id="darwin_trend",
            strategy_params={"fast_ema_period": 30, "slow_ema_period": 26},
        )

    with pytest.raises(ValueError, match="out of bounds"):
        validate_and_build_strategy_config(
            strategy_id="darwin_trend",
            strategy_params={"rsi_oversold": 75.0, "rsi_overbought": 70.0},
        )

    with pytest.raises(ValueError, match="ema_period must be strictly less"):
        validate_and_build_strategy_config(
            strategy_id="darwinx_zero_trader",
            strategy_params={"ema_period": 120, "sma_slow_period": 100},
        )


def test_zero_lookahead_weekly_heikin_ashi_alignment():
    """
    Verifies FR-004: Weekly Heikin-Ashi alignment onto daily bars strictly uses
    completed prior ISO weeks (zero lookahead bias).
    """
    weekly_bars = [
        {"date": "2025-01-06", "time": 1736121600, "open": 105.0, "high": 106.0, "low": 98.0, "close": 99.0, "volume": 100},
        {"date": "2025-01-13", "time": 1736726400, "open": 99.0, "high": 108.0, "low": 98.5, "close": 107.0, "volume": 100},
        {"date": "2025-01-20", "time": 1737331200, "open": 107.0, "high": 108.0, "low": 95.0, "close": 96.0, "volume": 100},
    ]
    # Daily bar on Wednesday 2025-01-22 (ISO week 4) must only see ISO weeks 2 and 3 (2025-01-06 and 2025-01-13),
    # NEVER the unfinished ISO week 4 (2025-01-20)!
    daily_df = pd.DataFrame(
        [
            {"date": "2025-01-08", "time": 1736294400, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
            {"date": "2025-01-22", "time": 1737504000, "open": 105.0, "high": 106.0, "low": 104.0, "close": 105.5},
        ]
    )
    enriched = enrich_weekly_heikin_ashi(daily_df, weekly_bars)

    # First daily bar has 0 completed prior weeks -> None
    assert enriched.loc[0, "w1_ha_color_prev1"] is None
    assert enriched.loc[0, "w1_ha_color_prev2"] is None

    # Second daily bar (2025-01-22) sees W-2 (2025-01-06 = RED) and W-1 (2025-01-13 = GREEN)
    assert enriched.loc[1, "w1_ha_color_prev2"] == "RED"
    assert enriched.loc[1, "w1_ha_color_prev1"] == "GREEN"


def test_single_asset_darwin_trend_backtest_and_mtm_invariants(temp_yahoo_db):
    """
    Verifies US1 Scenario 1 & SC-003: Single-asset Darwin Trend ATR backtest with custom
    parameters satisfies MTM accounting invariants (`final_equity == initial_balance + realized + unrealized`).
    """
    _seed_synthetic_stock_history(temp_yahoo_db, symbol="AAPL", days=220)

    res = run_single_asset_yahoo_backtest(
        db=temp_yahoo_db,
        symbol="NASDAQ:AAPL",
        strategy_id="darwin_trend",
        timeframe="D1",
        from_date="2024-03-01",
        to_date="2024-12-31",
        initial_balance=100000.0,
        risk_per_trade_pct=15.0,
        strategy_params={
            "fast_ema_period": 8,
            "slow_ema_period": 21,
            "rsi_period": 10,
            "rsi_overbought": 75.0,
            "rsi_oversold": 25.0,
            "atr_period": 10,
            "atr_multiplier": 1.5,
        },
    )

    assert res["symbol"] == "AAPL"
    assert res["status"] == "READY"
    assert res["bars_count"] > 0
    assert res["effective_from_date"] >= "2024-03-01"
    assert res["latest_signal"] in ("ENTER_LONG", "ENTER_SHORT", "HOLD")

    m = res["metrics"]
    assert m["initial_balance"] == 100000.0
    assert m["net_profit"] == pytest.approx(m["realized_pnl"] + m["unrealized_pnl"], abs=0.02)
    assert m["final_equity"] == pytest.approx(
        m["initial_balance"] + m["realized_pnl"] + m["unrealized_pnl"], abs=0.02
    )
    assert len(res["equity_curve"]) == res["bars_count"]
    for t in res["trades"]:
        assert t["entry_date"] >= "2024-03-01"


def test_single_asset_darwinx_zero_trader_custom_params(temp_yahoo_db):
    """
    Verifies US1 Scenario 2: DarwinX Zero Trader executes on Yahoo Finance data with
    customizable Quad-MA periods and 3-stage parameters.
    """
    _seed_synthetic_stock_history(temp_yahoo_db, symbol="NVDA", days=260)

    res = run_single_asset_yahoo_backtest(
        db=temp_yahoo_db,
        symbol="NVDA",
        strategy_id="darwinx_zero_trader",
        timeframe="D1",
        initial_balance=50000.0,
        risk_per_trade_pct=20.0,
        strategy_params={
            "ema_period": 10,
            "sma_fast_period": 20,
            "sma_mid_period": 30,
            "sma_slow_period": 50,
            "stop_loss_pct": 8.0,
            "partial_tp_pct": 4.0,
            "partial_fraction": 0.5,
        },
    )

    assert res["symbol"] == "NVDA"
    assert res["status"] == "READY"
    m = res["metrics"]
    assert m["initial_balance"] == 50000.0
    assert m["final_equity"] == pytest.approx(
        m["initial_balance"] + m["realized_pnl"] + m["unrealized_pnl"], abs=0.02
    )


def test_multi_asset_and_sector_portfolio_backtest(temp_yahoo_db):
    """
    Verifies US2 Scenarios 1-3 & FR-006: Multi-asset and sector batch backtesting
    allocates `initial_balance / N` across valid symbols, handles `NO_DATA` symbols
    gracefully, and aligns portfolio equity curves with `ffill().fillna(capital_k)`.
    """
    _seed_synthetic_stock_history(temp_yahoo_db, symbol="AAPL", sector="Technology", days=180)
    _seed_synthetic_stock_history(temp_yahoo_db, symbol="MSFT", sector="Technology", days=180)
    # Add a ticker with 0 price rows
    temp_yahoo_db.upsert_tickers(
        [{"symbol": "GHOST", "name": "Ghost Inc", "market": "NYSE", "sector": "Technology", "active": True}]
    )

    port_res = run_yahoo_portfolio_backtest(
        db=temp_yahoo_db,
        strategy_id="darwin_trend",
        symbols=["AAPL", "MSFT", "GHOST"],
        timeframe="D1",
        initial_balance=100000.0,
        risk_per_trade_pct=10.0,
    )

    assert port_res["total_symbols_requested"] == 3
    assert port_res["valid_symbols_count"] == 2
    assert len(port_res["asset_results"]) == 3

    by_sym = {r["symbol"]: r for r in port_res["asset_results"]}
    assert by_sym["AAPL"]["status"] == "READY"
    assert by_sym["MSFT"]["status"] == "READY"
    assert by_sym["GHOST"]["status"] == "NO_DATA"

    # Capital allocated equally across the 2 valid symbols ($50k each)
    assert by_sym["AAPL"]["metrics"]["initial_balance"] == pytest.approx(50000.0)
    assert by_sym["MSFT"]["metrics"]["initial_balance"] == pytest.approx(50000.0)

    pm = port_res["portfolio_metrics"]
    assert pm["initial_balance"] == pytest.approx(100000.0)
    assert pm["realized_pnl"] == pytest.approx(
        by_sym["AAPL"]["metrics"]["realized_pnl"] + by_sym["MSFT"]["metrics"]["realized_pnl"],
        abs=0.05,
    )
    assert pm["unrealized_pnl"] == pytest.approx(
        by_sym["AAPL"]["metrics"]["unrealized_pnl"] + by_sym["MSFT"]["metrics"]["unrealized_pnl"],
        abs=0.05,
    )
    assert len(port_res["portfolio_equity_curve"]) > 0

    # Also test sector filter batch selection
    sector_res = run_yahoo_portfolio_backtest(
        db=temp_yahoo_db,
        strategy_id="darwin_trend",
        sector="Technology",
        timeframe="W1",
        initial_balance=90000.0,
    )
    assert sector_res["total_symbols_requested"] == 3
    assert sector_res["valid_symbols_count"] == 2
