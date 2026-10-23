from fastapi.testclient import TestClient
import pytest

from api_gateway.main import app
import api_gateway.routes_yahoo as routes_yahoo
from strategy_engine.yahoo_db import YahooFinanceDB

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_yahoo_db(tmp_path, monkeypatch):
    test_db = YahooFinanceDB(db_path=str(tmp_path / "test_routes_yahoo.db"))
    test_db.upsert_tickers(
        [
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "market": "NASDAQ",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "active": True,
            },
            {
                "symbol": "SAN",
                "name": "Banco Santander",
                "market": "BME",
                "sector": "Financial Services",
                "industry": "Banks - Diversified",
                "active": False,
            },
        ]
    )
    test_db.upsert_stock_prices(
        [
            {
                "symbol": "AAPL",
                "date": "2026-04-06",
                "open": 200.0,
                "high": 205.0,
                "low": 199.0,
                "close": 203.0,
                "volume": 40000000,
                "quarterly_eps": 2.15,
                "quarterly_revenue": 119575000000.0,
            },
            {
                "symbol": "AAPL",
                "date": "2026-04-07",
                "open": 203.0,
                "high": 208.0,
                "low": 201.0,
                "close": 206.5,
                "volume": 42000000,
                "quarterly_eps": 2.15,
                "quarterly_revenue": 119575000000.0,
            },
        ]
    )
    test_db.upsert_valuation_history(
        [
            {
                "symbol": "AAPL",
                "as_of_date": "2026-03-31",
                "period_type": "3M",
                "trailing_pe": 32.1,
                "forward_pe": 28.4,
                "pb": 45.0,
                "ps": 9.1,
                "peg": 2.0,
                "ev_ebitda": 24.2,
                "ev_revenue": 8.9,
                "market_cap": 3400000000000.0,
                "enterprise_value": 3450000000000.0,
                "dividend_yield": 0.005,
            }
        ]
    )
    monkeypatch.setattr(routes_yahoo, "yahoo_db", test_db)
    routes_yahoo._sync_state.update(
        {
            "status": "IDLE",
            "total_tickers": 0,
            "completed_tickers": 0,
            "failed_tickers": 0,
            "rows_upserted": 0,
            "valuations_upserted": 0,
            "message": "Idle",
        }
    )
    return test_db


def test_list_and_filter_yahoo_tickers():
    res = client.get("/api/v1/yahoo/tickers")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    assert "NASDAQ" in body["facets"]["markets"]
    assert "BME" in body["facets"]["markets"]

    res_active = client.get("/api/v1/yahoo/tickers?active_only=true")
    assert res_active.status_code == 200
    assert res_active.json()["total"] == 1
    assert res_active.json()["tickers"][0]["symbol"] == "AAPL"

    res_mkt = client.get("/api/v1/yahoo/tickers?market=BME")
    assert res_mkt.status_code == 200
    assert res_mkt.json()["total"] == 1
    assert res_mkt.json()["tickers"][0]["symbol"] == "SAN"


def test_crud_yahoo_ticker():
    # Create via MARKET:SYMBOL
    res_post = client.post(
        "/api/v1/yahoo/tickers",
        json={
            "symbol": "LSE:SHEL",
            "name": "Shell plc",
            "sector": "Energy",
            "industry": "Oil & Gas Integrated",
            "active": True,
        },
    )
    assert res_post.status_code == 200
    created = res_post.json()
    assert created["symbol"] == "SHEL"
    assert created["market"] == "LSE"

    # Patch active state
    res_patch = client.patch(
        "/api/v1/yahoo/tickers/SHEL",
        json={"active": False, "name": "Shell PLC Updated"},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["active"] is False
    assert res_patch.json()["name"] == "Shell PLC Updated"

    # Patch non-existent
    res_404 = client.patch("/api/v1/yahoo/tickers/NONEXISTENT", json={"active": True})
    assert res_404.status_code == 404

    # Delete
    res_del = client.delete("/api/v1/yahoo/tickers/SHEL")
    assert res_del.status_code == 200
    assert res_del.json()["deleted"] is True

    # Delete non-existent
    res_del_404 = client.delete("/api/v1/yahoo/tickers/SHEL")
    assert res_del_404.status_code == 404


def test_yahoo_history_and_fundamentals():
    res_d1 = client.get("/api/v1/yahoo/tickers/AAPL/history?timeframe=D1")
    assert res_d1.status_code == 200
    d1_body = res_d1.json()
    assert d1_body["symbol"] == "AAPL"
    assert d1_body["timeframe"] == "D1"
    assert d1_body["total_bars"] == 2
    assert d1_body["bars"][0]["date"] == "2026-04-06"
    assert d1_body["bars"][1]["close"] == pytest.approx(206.5)

    res_w1 = client.get("/api/v1/yahoo/tickers/AAPL/history?timeframe=W1")
    assert res_w1.status_code == 200
    w1_body = res_w1.json()
    assert w1_body["total_bars"] == 1
    assert w1_body["bars"][0]["high"] == pytest.approx(208.0)

    res_bad_tf = client.get("/api/v1/yahoo/tickers/AAPL/history?timeframe=M15")
    assert res_bad_tf.status_code == 400

    res_fund = client.get("/api/v1/yahoo/tickers/AAPL/fundamentals")
    assert res_fund.status_code == 200
    f_body = res_fund.json()
    assert f_body["symbol"] == "AAPL"
    assert f_body["latest_valuation"]["trailing_pe"] == pytest.approx(32.1)
    assert len(f_body["valuation_history"]) == 1
    assert len(f_body["quarterly_earnings"]) == 1
    assert f_body["quarterly_earnings"][0]["quarterly_eps"] == pytest.approx(2.15)


def test_yahoo_sync_and_conflict(monkeypatch):
    monkeypatch.setattr(
        routes_yahoo,
        "sync_yahoo_tickers",
        lambda **kwargs: {
            "total_symbols": 1,
            "completed_symbols": 1,
            "failed_symbols": [],
            "upserted_prices": 10,
            "upserted_valuations": 2,
            "updated_metadata": 1,
        },
    )

    res_sync = client.post("/api/v1/yahoo/sync", json={"symbol": "AAPL"})
    assert res_sync.status_code == 200
    body = res_sync.json()
    assert body["status"] == "COMPLETED"
    assert body["rows_upserted"] == 10
    assert body["valuations_upserted"] == 2

    res_status = client.get("/api/v1/yahoo/sync/status")
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "COMPLETED"

    # Simulate conflict when already IN_PROGRESS
    routes_yahoo._sync_state["status"] = "IN_PROGRESS"
    res_conflict = client.post("/api/v1/yahoo/sync", json={"symbol": "AAPL"})
    assert res_conflict.status_code == 409
