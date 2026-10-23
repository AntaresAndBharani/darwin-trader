"""
Unit tests for YahooFinanceDB SQLite WAL storage engine, ticker filtering,
D1/W1/MN1 resampling, NaN/Inf sanitization, and valuation/earnings queries.
"""
import math
import pytest

from strategy_engine.yahoo_db import (
    YahooFinanceDB,
    parse_market_symbol,
    sanitize_float,
)


def test_parse_market_symbol_and_sanitize_float():
    assert parse_market_symbol("NASDAQ:AAPL") == ("AAPL", "NASDAQ")
    assert parse_market_symbol("  bme:san  ") == ("SAN", "BME")
    assert parse_market_symbol("msft", default_market="nasdaq") == ("MSFT", "NASDAQ")

    assert sanitize_float(12.5) == 12.5
    assert sanitize_float(float("nan")) is None
    assert sanitize_float(float("inf")) is None
    assert sanitize_float(float("-inf")) is None
    assert sanitize_float("invalid") is None


def test_yahoo_db_tickers_crud_and_facets(tmp_path):
    db_file = str(tmp_path / "test_yahoo.db")
    db = YahooFinanceDB(db_path=db_file)

    count = db.upsert_tickers(
        [
            {
                "symbol": "NASDAQ:AAPL",
                "name": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "active": True,
            },
            {
                "symbol": "BME:SAN",
                "name": "Banco Santander",
                "sector": "Financial Services",
                "industry": "Banks - Diversified",
                "active": True,
            },
            {
                "symbol": "NYSE:PM",
                "name": "Philip Morris",
                "sector": "Consumer Defensive",
                "industry": "Tobacco",
                "active": False,
            },
        ]
    )
    assert count == 3

    facets = db.get_filter_facets()
    assert facets["markets"] == ["BME", "NASDAQ", "NYSE"]
    assert "Technology" in facets["sectors"]
    assert "Banks - Diversified" in facets["industries"]

    # Filter by market
    bme_list = db.get_tickers(market="BME")
    assert len(bme_list) == 1
    assert bme_list[0]["symbol"] == "SAN"

    # Filter by active_only
    active_list = db.get_tickers(active_only=True)
    assert [t["symbol"] for t in active_list] == ["AAPL", "SAN"]

    # Search by substring
    search_list = db.get_tickers(search="apple")
    assert len(search_list) == 1
    assert search_list[0]["symbol"] == "AAPL"

    # Update ticker
    updated = db.update_ticker("AAPL", active=False, sector="Tech Hardware")
    assert updated is not None
    assert updated["active"] is False
    assert updated["sector"] == "Tech Hardware"

    # Delete ticker
    del_res = db.delete_ticker("PM")
    assert del_res["deleted"] is True
    assert db.get_ticker("PM") is None


def test_yahoo_db_stock_prices_and_resampling(tmp_path):
    db_file = str(tmp_path / "test_prices.db")
    db = YahooFinanceDB(db_path=db_file)

    rows = [
        # Week 1 of Jan 2024
        {"symbol": "AAPL", "date": "2024-01-02", "open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0, "volume": 1000, "quarterly_eps": 1.5, "quarterly_revenue": 90000.0},
        {"symbol": "AAPL", "date": "2024-01-03", "open": 102.0, "high": 108.0, "low": 101.0, "close": 107.0, "volume": 1500, "quarterly_eps": float("nan"), "quarterly_revenue": None},
        # Week 2 of Jan 2024
        {"symbol": "AAPL", "date": "2024-01-08", "open": 107.0, "high": 110.0, "low": 104.0, "close": 109.0, "volume": 2000},
        # Feb 2024
        {"symbol": "AAPL", "date": "2024-02-01", "open": 110.0, "high": 115.0, "low": 108.0, "close": 114.0, "volume": 2500, "quarterly_eps": 1.65, "quarterly_revenue": 95000.0},
    ]
    written = db.upsert_stock_prices(rows)
    assert written == 4

    assert db.get_global_max_date() == "2024-02-01"
    ranges = db.get_data_ranges(["AAPL"])
    assert ranges["AAPL"] == ("2024-01-02", "2024-02-01")

    # D1 history
    d1_bars, d1_total = db.get_price_history("AAPL", timeframe="D1")
    assert d1_total == 4
    assert len(d1_bars) == 4
    assert d1_bars[0]["date"] == "2024-01-02"
    assert d1_bars[-1]["date"] == "2024-02-01"
    assert d1_bars[0]["time"] < d1_bars[-1]["time"]

    # W1 history (3 distinct ISO weeks)
    w1_bars, w1_total = db.get_price_history("AAPL", timeframe="W1")
    assert w1_total == 3
    assert w1_bars[0]["open"] == 100.0
    assert w1_bars[0]["high"] == 108.0
    assert w1_bars[0]["low"] == 99.0
    assert w1_bars[0]["close"] == 107.0
    assert w1_bars[0]["volume"] == 2500
    # Resampled bars are anchored to the first trading day of the bucket
    assert w1_bars[0]["date"] == "2024-01-02"
    assert w1_bars[0]["time"] == d1_bars[0]["time"]

    # MN1 history (2 distinct months: Jan & Feb 2024)
    mn1_bars, mn1_total = db.get_price_history("AAPL", timeframe="MN1")
    assert mn1_total == 2
    assert mn1_bars[0]["open"] == 100.0
    assert mn1_bars[0]["high"] == 110.0
    assert mn1_bars[0]["low"] == 99.0
    assert mn1_bars[0]["close"] == 109.0
    assert mn1_bars[0]["volume"] == 4500
    assert mn1_bars[0]["date"] == "2024-01-02"
    assert mn1_bars[1]["date"] == "2024-02-01"
    assert mn1_bars[1]["close"] == 114.0

    with pytest.raises(ValueError, match="Unsupported timeframe"):
        db.get_price_history("AAPL", timeframe="M15")


def test_yahoo_db_valuation_and_fundamentals_summary(tmp_path):
    db_file = str(tmp_path / "test_val.db")
    db = YahooFinanceDB(db_path=db_file)
    db.upsert_tickers([{"symbol": "NASDAQ:NVDA", "name": "NVIDIA Corp", "sector": "Technology", "industry": "Semiconductors"}])
    db.upsert_stock_prices(
        [
            {"symbol": "NVDA", "date": "2024-05-01", "open": 80.0, "high": 85.0, "low": 79.0, "close": 83.0, "volume": 10000, "quarterly_eps": 0.60, "quarterly_revenue": 26000000000.0},
            {"symbol": "NVDA", "date": "2024-08-01", "open": 110.0, "high": 120.0, "low": 108.0, "close": 118.0, "volume": 12000, "quarterly_eps": 0.68, "quarterly_revenue": 30000000000.0},
        ]
    )
    val_written = db.upsert_valuation_history(
        [
            {
                "symbol": "NVDA",
                "as_of_date": "2024-04-30",
                "period_type": "3M",
                "trailing_pe": 45.2,
                "forward_pe": 32.1,
                "pb": 38.0,
                "ps": 24.5,
                "peg": 1.2,
                "ev_ebitda": 39.0,
                "ev_revenue": 24.0,
                "market_cap": 2100000000000.0,
                "enterprise_value": 2080000000000.0,
                "dividend_yield": None,
            },
            {
                "symbol": "NVDA",
                "as_of_date": "2024-07-31",
                "period_type": "3M",
                "trailing_pe": 52.4,
                "forward_pe": 35.0,
                "pb": float("nan"),
                "ps": 28.1,
                "peg": 1.35,
                "ev_ebitda": 44.2,
                "ev_revenue": 27.8,
                "market_cap": 2900000000000.0,
                "enterprise_value": 2880000000000.0,
                "dividend_yield": 0.0003,
            },
        ]
    )
    assert val_written == 2

    summary = db.get_fundamentals_summary("NVDA")
    assert summary["symbol"] == "NVDA"
    assert summary["ticker"]["name"] == "NVIDIA Corp"
    assert summary["latest_valuation"]["trailing_pe"] == 52.4
    # Merged non-null fallback from previous quarter when latest had NaN->None
    assert summary["latest_valuation"]["pb"] == 38.0
    assert summary["latest_valuation"]["dividend_yield"] == 0.0003
    assert len(summary["valuation_history"]) == 2
    assert len(summary["quarterly_earnings"]) == 2
    assert summary["quarterly_earnings"][0]["quarterly_eps"] == 0.68
