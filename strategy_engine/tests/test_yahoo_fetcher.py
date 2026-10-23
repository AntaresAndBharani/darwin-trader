import datetime
import pandas as pd
import pytest

from strategy_engine.cli import main as cli_main
from strategy_engine.yahoo_db import YahooFinanceDB
from strategy_engine.yahoo_fetcher import (
    fetch_ticker_metadata,
    fetch_ticker_ohlcv_and_earnings,
    fetch_ticker_valuation,
    format_yahoo_ticker,
    migrate_postgres_to_sqlite,
    parse_valuation_measures,
    sync_yahoo_tickers,
)


class FakeYahooTicker:
    def __init__(self, yahoo_symbol: str):
        self.yahoo_symbol = yahoo_symbol
        self.asset_profile = {
            yahoo_symbol: {
                "sector": "Technology",
                "industry": "Consumer Electronics",
            }
        }
        self.quote_type = {
            yahoo_symbol: {
                "longName": f"{yahoo_symbol} Corp",
                "exchange": "NMS",
            }
        }
        self.summary_detail = {
            yahoo_symbol: {
                "dividendYield": 0.0055,
            }
        }
        self.financial_data = {
            yahoo_symbol: {
                "totalRevenue": 391035000000.0,
            }
        }
        self.earning_history = pd.DataFrame(
            [
                {"quarter": "2026-01-01", "epsActual": 2.40},
                {"quarter": "2026-04-01", "epsActual": 1.65},
            ]
        )
        self.valuation_measures = pd.DataFrame(
            [
                {
                    "asOfDate": "2026-01-31",
                    "periodType": "3M",
                    "PeRatio": 31.2,
                    "ForwardPeRatio": 27.5,
                    "PbRatio": 44.1,
                    "PsRatio": 8.9,
                    "PegRatio": 2.1,
                    "EnterprisesValueEBITDARatio": 23.4,
                    "EnterprisesValueRevenueRatio": 8.7,
                    "MarketCap": 3400000000000.0,
                    "EnterpriseValue": 3450000000000.0,
                },
                {
                    "asOfDate": "2026-04-30",
                    "periodType": "3M",
                    "PeRatio": 33.0,
                    "ForwardPeRatio": 28.1,
                    "PbRatio": 46.0,
                    "PsRatio": 9.3,
                    "PegRatio": 2.2,
                    "EnterpriseValueEBITDARatio": 24.5,
                    "EnterpriseValueRevenueRatio": 9.1,
                    "MarketCap": 3550000000000.0,
                    "EnterpriseValue": 3600000000000.0,
                },
            ]
        )

    def history(self, start=None, end=None, interval="1d"):
        return pd.DataFrame(
            [
                {
                    "symbol": self.yahoo_symbol,
                    "date": "2026-04-10",
                    "open": 210.0,
                    "high": 215.0,
                    "low": 208.0,
                    "close": 213.5,
                    "volume": 45000000,
                },
                {
                    "symbol": self.yahoo_symbol,
                    "date": "2026-04-13",
                    "open": 214.0,
                    "high": 218.0,
                    "low": 212.0,
                    "close": 217.0,
                    "volume": 51000000,
                },
            ]
        )


def test_format_yahoo_ticker():
    assert format_yahoo_ticker("AAPL", "NASDAQ") == "AAPL"
    assert format_yahoo_ticker("SHEL", "LSE") == "SHEL.L"
    assert format_yahoo_ticker("LSE:SHEL") == "SHEL.L"
    assert format_yahoo_ticker("BME:SAN") == "SAN.MC"
    assert format_yahoo_ticker("XETR:SAP") == "SAP.DE"
    assert format_yahoo_ticker("TSX:SHOP") == "SHOP.TO"
    assert format_yahoo_ticker("HKEX:0700") == "0700.HK"


def test_fetch_ohlcv_metadata_and_valuation():
    factory = lambda sym: FakeYahooTicker(sym)

    meta = fetch_ticker_metadata("LSE:SHEL", ticker_factory=factory)
    assert meta["symbol"] == "SHEL"
    assert meta["market"] == "LSE"
    assert meta["sector"] == "Technology"
    assert meta["industry"] == "Consumer Electronics"
    assert meta["name"] == "SHEL.L Corp"

    vals = fetch_ticker_valuation("AAPL", market="NASDAQ", ticker_factory=factory)
    assert len(vals) == 2
    assert vals[0]["as_of_date"] == "2026-01-31"
    assert vals[0]["dividend_yield"] is None
    assert vals[1]["as_of_date"] == "2026-04-30"
    assert vals[1]["trailing_pe"] == pytest.approx(33.0)
    assert vals[1]["dividend_yield"] == pytest.approx(0.0055)

    prices = fetch_ticker_ohlcv_and_earnings(
        "AAPL",
        start_date="2026-04-01",
        end_date="2026-04-15",
        market="NASDAQ",
        include_fundamentals=True,
        ticker_factory=factory,
    )
    assert len(prices) == 2
    assert prices[0]["date"] == "2026-04-10"
    assert prices[0]["close"] == pytest.approx(213.5)
    assert prices[0]["quarterly_eps"] == pytest.approx(1.65)
    assert prices[0]["quarterly_revenue"] == pytest.approx(391035000000.0)

    assert parse_valuation_measures("AAPL", "No data available") == []


def test_sync_yahoo_tickers(tmp_path):
    db = YahooFinanceDB(db_path=str(tmp_path / "yahoo_sync_test.db"))
    factory = lambda sym: FakeYahooTicker(sym)

    summary = sync_yahoo_tickers(
        db=db,
        symbols=["NASDAQ:AAPL", "LSE:SHEL"],
        workers=2,
        ticker_factory=factory,
    )
    assert summary["total_symbols"] == 2
    assert summary["completed_symbols"] == 2
    assert summary["failed_symbols"] == []
    assert summary["upserted_prices"] == 4
    assert summary["upserted_valuations"] == 4

    aapl = db.get_ticker("AAPL")
    assert aapl is not None
    assert aapl["sector"] == "Technology"
    assert aapl["price_bars_count"] == 2


def test_migrate_postgres_to_sqlite_and_cli(tmp_path, monkeypatch):
    db_path = str(tmp_path / "yahoo_migrated.db")
    db = YahooFinanceDB(db_path=db_path)

    class FakeCursor:
        def __init__(self):
            self._query = ""
            self._fetched = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def execute(self, sql):
            self._query = sql
            self._fetched = False

        def fetchall(self):
            if "FROM tickers" in self._query:
                return [
                    (
                        "AAPL",
                        "Apple Inc.",
                        "NASDAQ",
                        "Technology",
                        "Consumer Electronics",
                        True,
                        datetime.datetime(2025, 1, 1, 12, 0, 0),
                    ),
                    (
                        "MSFT",
                        "Microsoft Corp.",
                        "NASDAQ",
                        "Technology",
                        "Software - Infrastructure",
                        True,
                        datetime.datetime(2025, 1, 1, 12, 0, 0),
                    ),
                ]
            return []

        def fetchmany(self, size):
            if self._fetched:
                return []
            self._fetched = True
            if "FROM stock_prices" in self._query:
                return [
                    (
                        "AAPL",
                        datetime.date(2026, 4, 10),
                        210.0,
                        215.0,
                        208.0,
                        213.5,
                        45000000,
                        1.65,
                        391035000000.0,
                        datetime.datetime(2026, 4, 10, 18, 0, 0),
                    )
                ]
            if "FROM valuation_history" in self._query:
                return [
                    (
                        "AAPL",
                        datetime.date(2026, 3, 31),
                        "3M",
                        32.5,
                        28.0,
                        45.1,
                        9.2,
                        2.1,
                        24.0,
                        8.9,
                        3500000000000.0,
                        3550000000000.0,
                        0.005,
                        datetime.datetime(2026, 4, 1, 12, 0, 0),
                    )
                ]
            return []

    class FakePGConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            pass

    counts = migrate_postgres_to_sqlite(
        db=db,
        conn_factory=lambda **_kwargs: FakePGConn(),
    )
    assert counts == {"tickers": 2, "stock_prices": 1, "valuation_history": 1}

    # Verify CLI subcommands yahoo-migrate and yahoo-sync
    monkeypatch.setattr(
        "strategy_engine.cli.migrate_postgres_to_sqlite",
        lambda **kwargs: {"tickers": 2, "stock_prices": 1, "valuation_history": 1},
    )
    exit_code = cli_main(["yahoo-migrate", "--db-path", db_path, "-q"])
    assert exit_code == 0

    monkeypatch.setattr(
        "strategy_engine.cli.sync_yahoo_tickers",
        lambda **kwargs: {
            "total_symbols": 1,
            "completed_symbols": 1,
            "failed_symbols": [],
            "upserted_prices": 2,
            "upserted_valuations": 2,
            "updated_metadata": 1,
        },
    )
    exit_code_sync = cli_main(
        ["yahoo-sync", "--symbol", "AAPL", "--db-path", db_path, "-q"]
    )
    assert exit_code_sync == 0
