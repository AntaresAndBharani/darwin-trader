"""
Integration tests for FastAPI Asset Router, Gateway Mounting, and Client SDK.
Covers Gherkin Scenarios 1 through 6 for Issue #67 / #69.
"""
from unittest.mock import MagicMock, patch
import time
import httpx
import pytest
from fastapi.testclient import TestClient

from api_gateway.main import app
from api_gateway.routes_assets import _reset_sync_state, _set_sync_state_for_testing
from api_gateway.routes_strategy import connector, global_config
from strategy_engine.cli import main as cli_main
from strategy_engine.historical_db import HistoricalRatesDB
from strategy_engine.models import (
    AssetInfo,
    HistoricalBar,
    HistoricalRatesResponse,
    HistoricalSyncResponse,
    HistoricalSyncStatus,
    InstitutionalMetrics,
)
from strategy_engine.mt5_connector import MT5Connector
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


def test_scenario_3_background_sync_and_partial_failure():
    """
    Scenario 3: Asynchronous Background Sync Telemetry & Partial Failure Resilience Contract.
    Given FastAPI gateway is running and no sync job is currently active
    When a client requests POST /api/v1/assets/history/sync?category=stocks&fresh=true
    Then response status is 202 Accepted and returns status 'IN_PROGRESS'
    And subsequent requests to GET /api/v1/assets/history/sync/status report progress telemetry
    And if an invalid or delisted symbol is encountered, failed_assets is incremented without crashing
    And regular gateway endpoints continue responding without thread starvation.
    """
    _reset_sync_state()

    # 1. Trigger fresh batch sync
    response = client.post("/api/v1/assets/history/sync?category=stocks&fresh=true")
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "IN_PROGRESS"
    assert data["message"] == "Historical sync job started"

    # 2. Check telemetry immediately
    status_resp = client.get("/api/v1/assets/history/sync/status")
    assert status_resp.status_code == 200
    stat = status_resp.json()
    assert stat["total_assets"] == 5

    # 3. Regular endpoints continue responding cleanly
    assets_resp = client.get("/api/v1/assets")
    assert assets_resp.status_code == 200

    # 4. Wait for completion
    for _ in range(40):
        stat = client.get("/api/v1/assets/history/sync/status").json()
        if stat["status"] == "COMPLETED":
            break
        time.sleep(0.05)

    assert stat["status"] == "COMPLETED"
    assert stat["completed_assets"] == 5
    assert stat["failed_assets"] == 0

    # 5. Test partial failure resilience on delisted symbol
    _reset_sync_state()
    original_sync = connector.sync_historical_rates

    def mock_sync_with_failure(symbol, timeframe="D1", fresh=False, db=None):
        if symbol == "PM":
            return None, 0
        return original_sync(symbol, timeframe=timeframe, fresh=fresh, db=db)

    with patch.object(connector, "sync_historical_rates", side_effect=mock_sync_with_failure):
        fail_resp = client.post("/api/v1/assets/history/sync?category=stocks")
        assert fail_resp.status_code == 202

        for _ in range(40):
            stat = client.get("/api/v1/assets/history/sync/status").json()
            if stat["status"] == "COMPLETED":
                break
            time.sleep(0.05)

        assert stat["status"] == "COMPLETED"
        assert stat["completed_assets"] == 4
        assert stat["failed_assets"] == 1

    _reset_sync_state()


def test_scenario_7_concurrent_sync_rejection_with_http_409():
    """
    Scenario 7: Concurrent Sync Rejection with HTTP 409 Conflict.
    Given a bulk historical sync job is already currently 'IN_PROGRESS'
    When a client or TUI user submits a second POST /api/v1/assets/history/sync request
    Then the gateway immediately rejects the request with HTTP status 409 Conflict
    And returns JSON detail {"detail": "Sync job already in progress", "current_job_id": "...", "status": "IN_PROGRESS"}.
    """
    _reset_sync_state()
    _set_sync_state_for_testing(status="IN_PROGRESS", job_id="mock-active-job-xyz")

    resp_conflict = client.post("/api/v1/assets/history/sync")
    assert resp_conflict.status_code == 409
    body = resp_conflict.json()
    assert body["detail"] == "Sync job already in progress"
    assert body["current_job_id"] == "mock-active-job-xyz"
    assert body["status"] == "IN_PROGRESS"

    _reset_sync_state()


def test_scenario_4_and_5_historical_rates_pagination_and_scoped_resync():
    """
    Scenario 4 & 5: Historical Rates Paginated Reads and Scoped Re-sync.
    Given database contains bars for 'MSFT'
    When querying GET /api/v1/assets/MSFT/history?timeframe=D1&limit=500&offset=0
    Then returns total_bars, limit, offset, page, total_pages, and bars list.
    And when triggering POST /api/v1/assets/history/sync?symbol=MSFT&fresh=true
    Then initiates scoped sync for only MSFT (total_assets=1).
    """
    _reset_sync_state()
    db = HistoricalRatesDB()
    db.clear_rates(symbol="MSFT")

    # Insert 1200 test bars
    test_bars = [
        HistoricalBar(
            symbol="MSFT",
            timeframe="D1",
            time=1700000000 + i * 86400,
            open=300.0 + i * 0.1,
            high=305.0 + i * 0.1,
            low=299.0 + i * 0.1,
            close=304.0 + i * 0.1,
            tick_volume=1500,
            spread=2,
        )
        for i in range(1200)
    ]
    db.insert_rates(test_bars)

    # Page 1: 500 bars
    resp_p1 = client.get("/api/v1/assets/MSFT/history?timeframe=D1&limit=500&offset=0")
    assert resp_p1.status_code == 200
    data_p1 = resp_p1.json()
    assert data_p1["symbol"] == "MSFT"
    assert data_p1["timeframe"] == "D1"
    assert data_p1["total_bars"] == 1200
    assert data_p1["limit"] == 500
    assert data_p1["offset"] == 0
    assert data_p1["page"] == 1
    assert data_p1["total_pages"] == 3
    assert len(data_p1["bars"]) == 500

    # Page 2: 500 bars
    resp_p2 = client.get("/api/v1/assets/MSFT/history?timeframe=D1&limit=500&offset=500")
    assert resp_p2.status_code == 200
    data_p2 = resp_p2.json()
    assert data_p2["page"] == 2
    assert data_p2["offset"] == 500
    assert len(data_p2["bars"]) == 500

    # Page 3: 200 bars
    resp_p3 = client.get("/api/v1/assets/MSFT/history?timeframe=D1&limit=500&offset=1000")
    assert resp_p3.status_code == 200
    data_p3 = resp_p3.json()
    assert data_p3["page"] == 3
    assert data_p3["offset"] == 1000
    assert len(data_p3["bars"]) == 200

    # Scoped re-sync for MSFT
    resp_scoped = client.post("/api/v1/assets/history/sync?symbol=MSFT&fresh=true")
    assert resp_scoped.status_code == 202
    stat = client.get("/api/v1/assets/history/sync/status").json()
    assert stat["total_assets"] == 1

    # Cleanup
    db.clear_rates(symbol="MSFT")
    _reset_sync_state()


def test_strict_route_ordering_preceding_symbol():
    """
    Route Ordering Verification:
    Static history endpoints must precede /{symbol} to prevent capturing 'history' as symbol parameter.
    """
    # 1. /history/sync/status must return sync telemetry, NOT 404 "Asset 'history' not found"
    resp_status = client.get("/api/v1/assets/history/sync/status")
    assert resp_status.status_code == 200
    assert "status" in resp_status.json()

    # 2. /{symbol}/history must return HistoricalRatesResponse
    resp_hist = client.get("/api/v1/assets/NVDA/history")
    assert resp_hist.status_code == 200
    assert resp_hist.json()["symbol"] == "NVDA"

    # 3. /{symbol} must return AssetInfo
    resp_asset = client.get("/api/v1/assets/NVDA")
    assert resp_asset.status_code == 200
    assert resp_asset.json()["symbol"] == "NVDA"
    assert "lot_min" in resp_asset.json()

    # 4. Unknown asset history returns empty rates rather than 404
    resp_unknown_hist = client.get("/api/v1/assets/UNKNOWN_XYZ/history")
    assert resp_unknown_hist.status_code == 200
    assert resp_unknown_hist.json()["total_bars"] == 0
    assert resp_unknown_hist.json()["bars"] == []


@pytest.mark.asyncio
async def test_client_sdk_historical_methods_and_15s_timeout():
    """
    Client SDK Integration Test for Historical Operations:
    Verifies DarwinApiClient methods for sync, status, and paginated rates with 15.0s timeout.
    """
    _reset_sync_state()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_httpx:
        sdk = DarwinApiClient(base_url="http://test", client=test_httpx)
        assert sdk.historical_timeout == 15.0

        # 1. sync_historical_rates
        sync_res = await sdk.sync_historical_rates(symbol="MSFT", fresh=True)
        assert isinstance(sync_res, HistoricalSyncResponse)
        assert sync_res.status == "IN_PROGRESS"
        assert sync_res.job_id != ""

        # 2. get_sync_status
        status_res = await sdk.get_sync_status()
        assert isinstance(status_res, HistoricalSyncStatus)
        assert status_res.total_assets == 1

        # 3. get_historical_rates
        rates_res = await sdk.get_historical_rates("MSFT", limit=500, offset=0)
        assert isinstance(rates_res, HistoricalRatesResponse)
        assert rates_res.symbol == "MSFT"

        # 4. 409 Conflict handling in SDK
        _set_sync_state_for_testing(status="IN_PROGRESS", job_id="sdk-conflict-job-id")

        conflict_res = await sdk.sync_historical_rates(symbol="AAPL")
        assert conflict_res.status == "IN_PROGRESS"
        assert conflict_res.job_id == "sdk-conflict-job-id"
        assert "already in progress" in conflict_res.message

    _reset_sync_state()

    # 5. Offline SDK resilience
    offline_sdk = DarwinApiClient(base_url="http://127.0.0.1:9999", timeout=0.1, historical_timeout=0.1)
    rates_off = await offline_sdk.get_historical_rates("MSFT")
    assert rates_off.bars == []
    assert rates_off.total_bars == 0

    stat_off = await offline_sdk.get_sync_status()
    assert stat_off.status == "IDLE"

    sync_off = await offline_sdk.sync_historical_rates("MSFT")
    assert sync_off.status == "ERROR"
    await offline_sdk.close()


def test_cli_sync_history_command(tmp_path):
    """
    CLI Ingestion Tool Test:
    Verifies 'python -m strategy_engine.cli sync-history' with symbol, category, and fresh options.
    """
    db_file = str(tmp_path / "cli_test.db")

    # 1. Sync single symbol
    rc = cli_main(["sync-history", "--symbol", "AMZN", "--db-path", db_file])
    assert rc == 0
    db = HistoricalRatesDB(db_path=db_file)
    assert db.get_total_bars("AMZN") > 0

    # 2. Sync single symbol with --fresh
    rc_fresh = cli_main(["sync-history", "--symbol", "AMZN", "--fresh", "--db-path", db_file])
    assert rc_fresh == 0

    # 3. Sync category
    rc_cat = cli_main(["sync-history", "--category", "stocks", "--db-path", db_file])
    assert rc_cat == 0

    # 4. Invalid category returns 1
    rc_inv = cli_main(["sync-history", "--category", "crypto_invalid", "--db-path", db_file])
    assert rc_inv == 1

    # 5. No command / invalid command returns 1
    assert cli_main([]) == 1
    assert cli_main(["unknown-cmd"]) == 1


def test_historical_routes_invalid_timeframe():
    """
    Verifies that passing an unsupported timeframe to historical sync or rates endpoints
    returns HTTP 400 Bad Request with descriptive error details.
    """
    # 1. POST /history/sync with invalid timeframe
    resp_sync = client.post("/api/v1/assets/history/sync?timeframe=INVALID_TF")
    assert resp_sync.status_code == 400
    assert "Unsupported timeframe" in resp_sync.json()["detail"]

    # 2. GET /{symbol}/history with invalid timeframe
    resp_rates = client.get("/api/v1/assets/MSFT/history?timeframe=INVALID_TF")
    assert resp_rates.status_code == 400
    assert "Unsupported timeframe" in resp_rates.json()["detail"]


def test_historical_routes_pagination_validation():
    """
    Verifies FastAPI query parameter validation for limit and offset bounds.
    """
    # limit < 1
    resp_low_limit = client.get("/api/v1/assets/MSFT/history?limit=0")
    assert resp_low_limit.status_code == 422

    # limit > 5000
    resp_high_limit = client.get("/api/v1/assets/MSFT/history?limit=5001")
    assert resp_high_limit.status_code == 422

    # offset < 0
    resp_neg_offset = client.get("/api/v1/assets/MSFT/history?offset=-1")
    assert resp_neg_offset.status_code == 422


def test_historical_sync_worker_exception_handling():
    """
    Verifies that an unhandled exception inside the background sync worker
    safely transitions sync status to FAILED and reports error telemetry.
    """
    _reset_sync_state()

    with patch.object(connector, "sync_historical_rates", side_effect=RuntimeError("Simulated DB crash")):
        resp = client.post("/api/v1/assets/history/sync?symbol=AMZN")
        assert resp.status_code == 202

        for _ in range(30):
            stat = client.get("/api/v1/assets/history/sync/status").json()
            if stat["status"] == "FAILED":
                break
            time.sleep(0.05)

        assert stat["status"] == "FAILED"
        assert "Simulated DB crash" in stat["message"]

    _reset_sync_state()


def test_cli_timeframe_validation_and_failures(tmp_path):
    """
    Verifies CLI returns exit code 1 on unsupported timeframe, connector failure,
    or delisted single symbol.
    """
    db_file = str(tmp_path / "cli_failures.db")

    # 1. Unsupported timeframe
    rc_tf = cli_main(["sync-history", "--symbol", "AMZN", "--timeframe", "INVALID_TF", "--db-path", db_file])
    assert rc_tf == 1

    # 2. Delisted single symbol
    with patch.object(MT5Connector, "sync_historical_rates", return_value=(None, 0)):
        rc_delisted = cli_main(["sync-history", "--symbol", "DELISTED_TEST", "--db-path", db_file])
        assert rc_delisted == 1

    # 3. Connector initialization failure
    with patch.object(MT5Connector, "initialize", return_value=(False, "Failed to connect to MT5 IPC")):
        rc_init_fail = cli_main(["sync-history", "--symbol", "AMZN", "--db-path", db_file])
        assert rc_init_fail == 1


@pytest.mark.asyncio
async def test_client_sdk_error_handling_and_status_codes():
    """
    Verifies DarwinApiClient graceful error handling on 400 Bad Request and unexpected errors.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_httpx:
        sdk = DarwinApiClient(base_url="http://test", client=test_httpx)

        # 1. sync_historical_rates with invalid timeframe (HTTP 400 -> ERROR response)
        sync_resp = await sdk.sync_historical_rates(symbol="MSFT", timeframe="INVALID_TF")
        assert sync_resp.status == "ERROR"
        assert "400" in sync_resp.message or "Unsupported timeframe" in sync_resp.message

        # 2. get_historical_rates with invalid timeframe (HTTP 400 -> empty rates response)
        rates_resp = await sdk.get_historical_rates("MSFT", timeframe="INVALID_TF")
        assert rates_resp.bars == []
        assert rates_resp.total_bars == 0


def test_scenario_7_fast_gateway_endpoint_for_synced_asset():
    """
    Scenario 7: Fast Gateway Endpoint for Synced Asset Using Most Recent Bars.
    Given an asset symbol "EURUSD" with 100 historical D1 bars in the local SQLite rates database
    When an API client queries "GET /api/v1/assets/EURUSD/metrics"
    Then the gateway queries HistoricalRatesDB with descending=True and limit=21
    And reverses the bars to chronological time ASC order ending at the latest available timestamp
    And responds with HTTP 200 OK and payload with insufficient_data=False.
    """
    db = HistoricalRatesDB()
    db.clear_rates(symbol="EURUSD")

    base_time = 1700000000
    # First 79 bars: flat at 1.0500
    # Last 21 bars: oscillating with known price variance
    test_bars = []
    for i in range(79):
        test_bars.append(
            HistoricalBar(
                symbol="EURUSD",
                timeframe="D1",
                time=base_time + i * 86400,
                open=1.0500,
                high=1.0500,
                low=1.0500,
                close=1.0500,
                tick_volume=1000,
                spread=1,
            )
        )
    for i in range(79, 100):
        price = 1.0500 + ((i % 2) * 0.0050)
        test_bars.append(
            HistoricalBar(
                symbol="EURUSD",
                timeframe="D1",
                time=base_time + i * 86400,
                open=price,
                high=price + 0.0020,
                low=price - 0.0020,
                close=price,
                tick_volume=1500,
                spread=1,
            )
        )
    db.insert_rates(test_bars)

    resp = client.get("/api/v1/assets/EURUSD/metrics")
    assert resp.status_code == 200
    data = resp.json()
    metrics_obj = InstitutionalMetrics(**data)
    assert metrics_obj.symbol == "EURUSD"

    assert data["symbol"] == "EURUSD"
    assert data["insufficient_data"] is False
    assert data["bars_found"] == 100
    assert data["bars_required"] == 21
    assert data["last_bar_time"] == db.get_latest_timestamp("EURUSD", "D1")

    # Metrics computed on newest 21 bars with price variance must be non-zero
    assert data["yang_zhang_vol_annualized"] is not None
    assert data["yang_zhang_vol_annualized"] > 0.0
    assert data["amihud_sensitivity"] is not None
    assert data["amihud_sensitivity"] > 0.0
    assert data["vwap"] is not None
    assert data["vwap_upper"] is not None
    assert data["vwap_lower"] is not None
    assert data["vwap_deviation_sigmas"] is not None
    assert data["roll_spread_pct"] is not None
    assert data["roll_spread_absolute"] is not None


def test_scenario_8_gateway_endpoint_returns_404_for_unsynced_asset():
    """
    Scenario 8: Gateway Endpoint Returns 404 for Unsynced Asset.
    Given an asset symbol "UNKNOWN_SYM" with zero bars in the local SQLite rates database
    When an API client queries "GET /api/v1/assets/UNKNOWN_SYM/metrics"
    Then the gateway responds with HTTP 404 Not Found
    And the detail message indicates "No local historical rates found; synchronize history first"
    And no MT5 network calls are triggered.
    """
    db = HistoricalRatesDB()
    db.clear_rates(symbol="UNKNOWN_SYM")

    with patch.object(connector, "get_asset_info") as mock_asset_info, patch.object(
        connector, "sync_historical_rates"
    ) as mock_sync:
        resp = client.get("/api/v1/assets/UNKNOWN_SYM/metrics")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "No local historical rates found; synchronize history first"
        assert mock_asset_info.call_count == 0
        assert mock_sync.call_count == 0


def test_scenario_9_gateway_endpoint_handles_insufficient_historical_bars():
    """
    Scenario 9: Gateway Endpoint Handles Insufficient Historical Bars.
    Given an asset symbol "NEW_STOCK" with only 10 historical bars in the local database
    When an API client queries "GET /api/v1/assets/NEW_STOCK/metrics"
    Then the gateway responds with HTTP 200 OK
    And the payload has insufficient_data set to true
    And bars_found is 10 and bars_required is 21
    And all computed metric fields are null.
    """
    db = HistoricalRatesDB()
    db.clear_rates(symbol="NEW_STOCK")

    base_time = 1700000000
    bars = [
        HistoricalBar(
            symbol="NEW_STOCK",
            timeframe="D1",
            time=base_time + i * 86400,
            open=50.0 + i,
            high=51.0 + i,
            low=49.0 + i,
            close=50.5 + i,
            tick_volume=1000,
            spread=2,
        )
        for i in range(10)
    ]
    db.insert_rates(bars)

    resp = client.get("/api/v1/assets/NEW_STOCK/metrics")
    assert resp.status_code == 200
    data = resp.json()

    assert data["symbol"] == "NEW_STOCK"
    assert data["insufficient_data"] is True
    assert data["bars_found"] == 10
    assert data["bars_required"] == 21
    assert data["last_bar_time"] == bars[-1].time
    assert data["yang_zhang_vol_annualized"] is None
    assert data["amihud_sensitivity"] is None
    assert data["vwap"] is None
    assert data["vwap_upper"] is None
    assert data["vwap_lower"] is None
    assert data["vwap_deviation_sigmas"] is None
    assert data["roll_spread_pct"] is None
    assert data["roll_spread_absolute"] is None


def test_gateway_endpoint_degenerate_zero_volume_and_flat_market():
    """
    Verifies that zero-volume bars and flat market conditions return HTTP 200 with nulls/zeros
    rather than crashing with HTTP 500 (RC6).
    """
    db = HistoricalRatesDB()
    base_time = 1700000000

    # 1. Zero volume 21 bars
    db.clear_rates(symbol="ZERO_VOL_SYM")
    zero_vol_bars = [
        HistoricalBar(
            symbol="ZERO_VOL_SYM",
            timeframe="D1",
            time=base_time + i * 86400,
            open=100.0 + i * 0.1,
            high=101.0 + i * 0.1,
            low=99.0 + i * 0.1,
            close=100.5 + i * 0.1,
            tick_volume=0,
            spread=2,
        )
        for i in range(21)
    ]
    db.insert_rates(zero_vol_bars)

    resp_zero = client.get("/api/v1/assets/ZERO_VOL_SYM/metrics")
    assert resp_zero.status_code == 200
    data_zero = resp_zero.json()
    assert data_zero["insufficient_data"] is False
    assert data_zero["amihud_sensitivity"] is None
    assert data_zero["vwap"] is None
    assert data_zero["vwap_upper"] is None
    assert data_zero["vwap_lower"] is None
    assert data_zero["vwap_deviation_sigmas"] is None

    # 2. Completely flat price action 21 bars (sigma == 0)
    db.clear_rates(symbol="FLAT_SYM")
    flat_bars = [
        HistoricalBar(
            symbol="FLAT_SYM",
            timeframe="D1",
            time=base_time + i * 86400,
            open=200.0,
            high=200.0,
            low=200.0,
            close=200.0,
            tick_volume=1000,
            spread=2,
        )
        for i in range(21)
    ]
    db.insert_rates(flat_bars)

    resp_flat = client.get("/api/v1/assets/FLAT_SYM/metrics")
    assert resp_flat.status_code == 200
    data_flat = resp_flat.json()
    assert data_flat["insufficient_data"] is False
    assert data_flat["yang_zhang_vol_annualized"] == 0.0
    assert data_flat["vwap"] == 200.0
    assert data_flat["vwap_upper"] == 200.0
    assert data_flat["vwap_lower"] == 200.0
    assert data_flat["vwap_deviation_sigmas"] == 0.0
    assert data_flat["roll_spread_pct"] == 0.0
    assert data_flat["roll_spread_absolute"] == 0.0


def test_gateway_endpoint_invalid_timeframe():
    """
    Verifies that requesting an invalid timeframe returns HTTP 400 Bad Request.
    """
    resp = client.get("/api/v1/assets/EURUSD/metrics?timeframe=INVALID_TF")
    assert resp.status_code == 400
    assert "Unsupported timeframe" in resp.json()["detail"]


