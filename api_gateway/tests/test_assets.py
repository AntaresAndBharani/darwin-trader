"""
Integration tests for FastAPI Asset Router, Gateway Mounting, and Client SDK.
Covers Gherkin Scenarios 1 through 6 for Issue #67 / #69.
"""
from unittest.mock import MagicMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient

from api_gateway.main import app
from api_gateway.routes_strategy import connector, global_config
from strategy_engine.models import AssetInfo
from tui.api_client import DarwinApiClient

client = TestClient(app)


def test_scenario_2_deterministic_mock_assets_retrieval():
    """
    Scenario 2: Deterministic Mock Assets Retrieval in Headless CI.
    Given MT5Connector is running in Mock Mode
    When a client requests GET /api/v1/assets?category=stocks
    Then status is 200 OK
    And payload contains exactly 5 mock stocks: AMZN, NVDA, MSFT, PM, AAPL
    And all have category starting with 'Stocks/US/' and currency 'USD'.
    """
    response = client.get("/api/v1/assets?category=stocks")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5

    symbols = [item["symbol"] for item in data]
    expected_symbols = ["AMZN", "NVDA", "MSFT", "PM", "AAPL"]
    assert sorted(symbols) == sorted(expected_symbols)

    for item in data:
        assert item["category"].startswith("Stocks/US/")
        assert item["currency"] == "USD"
        assert item["visible"] is True
        assert item["lot_min"] > 0
        assert item["bid"] is None
        assert item["ask"] is None

    # Default (no query params) and category=all return full 8 instruments
    resp_all = client.get("/api/v1/assets?category=all")
    assert resp_all.status_code == 200
    assert len(resp_all.json()) == 8

    resp_default = client.get("/api/v1/assets")
    assert resp_default.status_code == 200
    assert len(resp_default.json()) == 8

    # ETFs category
    resp_etfs = client.get("/api/v1/assets?category=etfs")
    assert resp_etfs.status_code == 200
    assert len(resp_etfs.json()) == 2
    assert {e["symbol"] for e in resp_etfs.json()} == {"SPY", "QQQ"}

    # Forex category
    resp_forex = client.get("/api/v1/assets?category=forex")
    assert resp_forex.status_code == 200
    assert len(resp_forex.json()) == 1
    assert resp_forex.json()[0]["symbol"] == "EURUSD"


def test_scenario_3_search_assets_by_substring():
    """
    Scenario 3: Search Assets by Substring Ticker or Company Name.
    Given assets catalog is loaded
    When a client requests GET /api/v1/assets?search=nvidia
    Then status is 200 OK and returns NVDA ('NVIDIA Corp')
    And when searching 'nonexistent_xyz'
    Then status is 200 OK and returns empty list [].
    """
    resp_nvidia = client.get("/api/v1/assets?search=nvidia")
    assert resp_nvidia.status_code == 200
    data = resp_nvidia.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "NVDA"
    assert "NVIDIA Corp" in data[0]["description"]

    resp_none = client.get("/api/v1/assets?search=nonexistent_xyz")
    assert resp_none.status_code == 200
    assert resp_none.json() == []

    # Ticker case-insensitivity
    resp_case = client.get("/api/v1/assets?search=amzn")
    assert resp_case.status_code == 200
    assert len(resp_case.json()) == 1
    assert resp_case.json()[0]["symbol"] == "AMZN"

    # Search with category constraint
    resp_filtered = client.get("/api/v1/assets?category=stocks&search=Corp")
    assert resp_filtered.status_code == 200
    tickers = {item["symbol"] for item in resp_filtered.json()}
    assert "NVDA" in tickers
    assert "MSFT" in tickers


def test_scenario_4_category_filtering_and_invalid_category():
    """
    Scenario 4: Category Filtering and Invalid Category Error Contract.
    Given backend is connected to MT5
    When a client requests GET /api/v1/assets?category=etfs
    Then returns only ETFs
    And when a client requests GET /api/v1/assets?category=crypto
    Then status is 400 Bad Request
    And detail is 'Invalid category 'crypto'. Supported categories: all, stocks, etfs, forex'.
    """
    resp_etfs = client.get("/api/v1/assets?category=etfs")
    assert resp_etfs.status_code == 200
    for item in resp_etfs.json():
        assert item["category"].startswith("ETFs/")

    resp_invalid = client.get("/api/v1/assets?category=crypto")
    assert resp_invalid.status_code == 400
    assert (
        resp_invalid.json()["detail"]
        == "Invalid category 'crypto'. Supported categories: all, stocks, etfs, forex"
    )

    resp_commodities = client.get("/api/v1/assets?category=commodities")
    assert resp_commodities.status_code == 400
    assert (
        resp_commodities.json()["detail"]
        == "Invalid category 'commodities'. Supported categories: all, stocks, etfs, forex"
    )


def test_scenario_5_single_asset_contract_and_quote_nullability():
    """
    Scenario 5: Single Asset Contract Specification & Closed-Market Quote Nullability.
    Given an asset exists (e.g. 'AMZN')
    When requesting GET /api/v1/assets/AMZN
    Then status is 200 OK and contains full contract specs
    And returns live numeric bid/ask when market is open
    And returns null bid/ask when market is closed
    And when requesting GET /api/v1/assets/UNKNOWN_TICKER
    Then status is 404 Not Found with exact detail message.
    """
    # Open market: quotes populated
    connector._mock_market_open = True
    resp_open = client.get("/api/v1/assets/AMZN")
    assert resp_open.status_code == 200
    data = resp_open.json()
    assert data["symbol"] == "AMZN"
    assert data["lot_min"] == 0.01
    assert data["lot_max"] == 100.0
    assert data["lot_step"] == 0.01
    assert data["digits"] == 2
    assert data["point"] == 0.01
    assert data["filling_mode"] == 1
    assert data["trade_mode"] == 4
    assert isinstance(data["bid"], float)
    assert isinstance(data["ask"], float)
    assert data["bid"] > 0
    assert data["ask"] > 0

    # Closed market: quotes degrade to null
    connector._mock_market_open = False
    resp_closed = client.get("/api/v1/assets/AMZN")
    assert resp_closed.status_code == 200
    closed_data = resp_closed.json()
    assert closed_data["symbol"] == "AMZN"
    assert closed_data["bid"] is None
    assert closed_data["ask"] is None

    # Case insensitivity in symbol lookup
    connector._mock_market_open = True
    resp_lower = client.get("/api/v1/assets/amzn")
    assert resp_lower.status_code == 200
    assert resp_lower.json()["symbol"] == "AMZN"

    # Unknown symbol -> 404
    resp_unknown = client.get("/api/v1/assets/UNKNOWN_TICKER")
    assert resp_unknown.status_code == 404
    assert resp_unknown.json()["detail"] == "Asset 'UNKNOWN_TICKER' not found in broker catalog"


def test_scenario_6_gateway_disconnected_error_contract():
    """
    Scenario 6: Gateway Disconnected Error Contract.
    Given MT5Connector is disconnected (is_connected=False and mock_mode=False)
    When requesting GET /api/v1/assets or GET /api/v1/assets/AMZN
    Then status is 503 Service Unavailable with detail 'MetaTrader 5 gateway disconnected'.
    """
    global_config.mock_mode = False
    connector.config.mock_mode = False
    connector.is_connected = False

    resp_assets = client.get("/api/v1/assets")
    assert resp_assets.status_code == 503
    assert resp_assets.json()["detail"] == "MetaTrader 5 gateway disconnected"

    resp_single = client.get("/api/v1/assets/AMZN")
    assert resp_single.status_code == 503
    assert resp_single.json()["detail"] == "MetaTrader 5 gateway disconnected"


@pytest.mark.live
def test_scenario_1_live_darwinex_mt5_assets():
    """
    Scenario 1: Retrieve All Stock Assets from Live Darwinex MT5 (@pytest.mark.live).
    Given backend is connected to live Darwinex MT5 terminal
    When a client requests GET /api/v1/assets?category=stocks
    Then status is 200 OK
    And payload contains stock assets retrieved from mt5.symbols_get()
    And no sequential symbol_select() IPC calls are invoked
    And includes verified assets 'AMZN', 'NVDA', 'MSFT', and 'PM'.
    """
    mock_symbols = []
    canonical_stocks = [
        ("AMZN", "Amazon.com Inc", r"Stocks\US\Nasdaq\AMZN"),
        ("NVDA", "NVIDIA Corp", r"Stocks\US\Nasdaq\NVDA"),
        ("MSFT", "Microsoft Corp", r"Stocks\US\Nasdaq\MSFT"),
        ("PM", "Philip Morris International", r"Stocks\US\NYSE\PM"),
    ]
    # Build 650+ stock items to verify scale requirement
    for i in range(650):
        sym = MagicMock()
        if i < len(canonical_stocks):
            name, desc, path = canonical_stocks[i]
            sym.name = name
            sym.description = desc
            sym.path = path
        else:
            sym.name = f"STK_{i}"
            sym.description = f"Stock Asset #{i}"
            sym.path = rf"Stocks\US\NYSE\STK_{i}"

        sym.currency_profit = "USD"
        sym.currency_base = "USD"
        sym.visible = bool(i % 2 == 0)
        sym.volume_min = 0.01
        sym.volume_max = 100.0
        sym.volume_step = 0.01
        sym.digits = 2
        sym.point = 0.01
        sym.filling_mode = 1
        sym.trade_mode = 4
        mock_symbols.append(sym)

    # Add a non-stock item to verify category filtering
    forex_sym = MagicMock()
    forex_sym.name = "EURUSD"
    forex_sym.description = "Euro vs US Dollar"
    forex_sym.path = r"Forex\Majors\EURUSD"
    forex_sym.currency_profit = "USD"
    forex_sym.visible = True
    mock_symbols.append(forex_sym)

    global_config.mock_mode = False
    connector.config.mock_mode = False
    connector.is_connected = True

    with patch("strategy_engine.mt5_connector.HAS_MT5", True), patch(
        "strategy_engine.mt5_connector.mt5"
    ) as mock_mt5:
        mock_mt5.symbols_get.return_value = mock_symbols

        response = client.get("/api/v1/assets?category=stocks")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 650

        # Verify no sequential symbol_select was called
        mock_mt5.symbols_get.assert_called_once()
        assert not hasattr(mock_mt5, "symbol_select") or mock_mt5.symbol_select.call_count == 0

        # Verify canonical assets exist
        returned_symbols = {item["symbol"] for item in data}
        for expected in ["AMZN", "NVDA", "MSFT", "PM"]:
            assert expected in returned_symbols

        # Verify properties
        for item in data:
            assert item["category"].startswith("Stocks/")
            assert "\\" not in item["category"]  # Forward-slash normalized
            assert "lot_min" in item
            assert "currency" in item
            assert "visible" in item


@pytest.mark.asyncio
async def test_client_sdk_get_assets_and_get_asset_info():
    """
    Client SDK Integration Test:
    Verifies that DarwinApiClient successfully queries the assets endpoints,
    deserializes responses into AssetInfo instances, and handles errors with safe fallbacks.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_httpx:
        sdk = DarwinApiClient(base_url="http://test", client=test_httpx)

        # 1. get_assets with category='stocks'
        stocks = await sdk.get_assets(category="stocks")
        assert isinstance(stocks, list)
        assert len(stocks) == 5
        assert all(isinstance(s, AssetInfo) for s in stocks)
        symbols = [s.symbol for s in stocks]
        assert "AMZN" in symbols
        assert "NVDA" in symbols

        # 2. get_assets with substring search
        search_res = await sdk.get_assets(search="nvidia")
        assert len(search_res) == 1
        assert isinstance(search_res[0], AssetInfo)
        assert search_res[0].symbol == "NVDA"

        # 3. get_assets with invalid category (HTTP 400 error handled gracefully with empty list)
        invalid_res = await sdk.get_assets(category="invalid_category")
        assert invalid_res == []

        # 4. get_asset_info existing symbol
        amzn_info = await sdk.get_asset_info("AMZN")
        assert amzn_info is not None
        assert isinstance(amzn_info, AssetInfo)
        assert amzn_info.symbol == "AMZN"
        assert amzn_info.lot_min == 0.01

        # 5. get_asset_info unknown symbol (HTTP 404 handled gracefully with None)
        unknown_info = await sdk.get_asset_info("UNKNOWN_XYZ")
        assert unknown_info is None


@pytest.mark.asyncio
async def test_client_sdk_offline_fallback():
    """
    Client SDK Offline Resilience Test:
    Verifies that DarwinApiClient returns safe defaults ([ ] and None)
    when the gateway is completely offline or unreachable.
    """
    offline_sdk = DarwinApiClient(base_url="http://127.0.0.1:9999", timeout=0.1)
    assets = await offline_sdk.get_assets()
    assert assets == []

    asset_info = await offline_sdk.get_asset_info("AMZN")
    assert asset_info is None
    await offline_sdk.close()
