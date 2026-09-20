"""
Unit tests for MT5Connector assets discovery, thread-safe caching, and contract models.
Covers Gherkin Scenarios 1 through 7 for Issue #67 / #68.
"""
import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from strategy_engine.config import StrategyConfig
from strategy_engine.models import AssetCategory, AssetInfo
from strategy_engine.mt5_connector import MT5Connector


@pytest.fixture
def mock_connector():
    """Returns an initialized MT5Connector in mock mode."""
    config = StrategyConfig(mock_mode=True)
    connector = MT5Connector(config)
    connector.initialize()
    return connector


def test_asset_info_and_category_models():
    """Verifies that AssetCategory enum and AssetInfo data models instantiate correctly."""
    assert AssetCategory.ALL == "all"
    assert AssetCategory.STOCKS == "stocks"
    assert AssetCategory.ETFS == "etfs"
    assert AssetCategory.FOREX == "forex"

    info = AssetInfo(
        symbol="AMZN",
        description="Amazon.com Inc",
        category="Stocks/US/Nasdaq",
        currency="USD",
        visible=True,
        lot_min=0.01,
        lot_max=100.0,
        lot_step=0.01,
        digits=2,
        point=0.01,
        filling_mode=1,
        trade_mode=4,
        bid=185.50,
        ask=185.60,
    )
    assert info.symbol == "AMZN"
    assert info.lot_min == 0.01
    assert info.digits == 2
    assert info.trade_mode == 4
    assert info.filling_mode == 1
    assert info.bid == 185.50
    assert info.ask == 185.60


def test_scenario_2_deterministic_mock_assets_retrieval(mock_connector):
    """
    Scenario 2: Deterministic Mock Assets Retrieval in Headless CI.
    Given MT5Connector is in Mock Mode
    When requesting assets with category 'stocks'
    Then returns exactly 5 mock stocks: AMZN, NVDA, MSFT, PM, AAPL
    And all have category starting with 'Stocks/US/' and currency 'USD'.
    """
    stocks = mock_connector.get_available_assets(category="stocks")
    assert len(stocks) == 5

    symbols = [s.symbol for s in stocks]
    expected_symbols = ["AMZN", "NVDA", "MSFT", "PM", "AAPL"]
    assert sorted(symbols) == sorted(expected_symbols)

    for stock in stocks:
        assert stock.category.startswith("Stocks/US/")
        assert stock.currency == "USD"
        assert stock.visible is True
        assert stock.lot_min > 0
        # In bulk catalog, quotes are decoupled/None
        assert stock.bid is None
        assert stock.ask is None

    # Test category enum parameter
    stocks_enum = mock_connector.get_available_assets(category=AssetCategory.STOCKS)
    assert len(stocks_enum) == 5

    # Test category 'all' and no category returns full catalog (8 instruments)
    all_assets = mock_connector.get_available_assets(category="all")
    assert len(all_assets) == 8

    default_assets = mock_connector.get_available_assets()
    assert len(default_assets) == 8

    # Test category 'etfs'
    etfs = mock_connector.get_available_assets(category="etfs")
    assert len(etfs) == 2
    assert {e.symbol for e in etfs} == {"SPY", "QQQ"}

    # Test category 'forex'
    forex = mock_connector.get_available_assets(category="forex")
    assert len(forex) == 1
    assert forex[0].symbol == "EURUSD"


def test_scenario_3_search_assets_by_substring(mock_connector):
    """
    Scenario 3: Search Assets by Substring Ticker or Company Name.
    Given assets catalog is loaded
    When searching 'nvidia'
    Then returns NVDA ('NVIDIA Corp')
    And when searching 'nonexistent_xyz'
    Then returns empty list [].
    """
    results_nvidia = mock_connector.get_available_assets(search="nvidia")
    assert len(results_nvidia) == 1
    assert results_nvidia[0].symbol == "NVDA"
    assert "NVIDIA Corp" in results_nvidia[0].description

    results_none = mock_connector.get_available_assets(search="nonexistent_xyz")
    assert results_none == []

    # Ticker case-insensitivity
    results_amzn = mock_connector.get_available_assets(search="amzn")
    assert len(results_amzn) == 1
    assert results_amzn[0].symbol == "AMZN"

    # Search with category constraint
    results_corp = mock_connector.get_available_assets(category="stocks", search="Corp")
    assert len(results_corp) >= 2
    matched_tickers = {s.symbol for s in results_corp}
    assert "NVDA" in matched_tickers
    assert "MSFT" in matched_tickers


def test_scenario_4_category_filtering_and_invalid_category(mock_connector):
    """
    Scenario 4: Category Filtering and Invalid Category Error Contract.
    Given MT5Connector is running
    When requesting category 'crypto'
    Then raises ValueError with exact error message contract.
    """
    with pytest.raises(ValueError) as exc_info:
        mock_connector.get_available_assets(category="crypto")
    assert (
        str(exc_info.value)
        == "Invalid category 'crypto'. Supported categories: all, stocks, etfs, forex"
    )

    with pytest.raises(ValueError) as exc_info2:
        mock_connector.get_available_assets(category="commodities")
    assert (
        str(exc_info2.value)
        == "Invalid category 'commodities'. Supported categories: all, stocks, etfs, forex"
    )


def test_scenario_5_single_asset_contract_and_quote_nullability(mock_connector):
    """
    Scenario 5: Single Asset Contract Specification & Closed-Market Quote Nullability.
    Given an asset exists (e.g. 'AMZN')
    When requesting single asset specs
    Then contains full contract specs: lot_min, lot_max, lot_step, digits, point, filling_mode, trade_mode
    And returns live quotes when market is open
    And returns null quotes when market is closed without raising unhandled errors
    And returns None for unknown ticker.
    """
    # Market open: quotes present
    mock_connector._mock_market_open = True
    asset = mock_connector.get_asset_info("AMZN")
    assert asset is not None
    assert asset.symbol == "AMZN"
    assert asset.lot_min == 0.01
    assert asset.lot_max == 100.0
    assert asset.lot_step == 0.01
    assert asset.digits == 2
    assert asset.point == 0.01
    assert asset.filling_mode == 1
    assert asset.trade_mode == 4
    assert isinstance(asset.bid, float)
    assert isinstance(asset.ask, float)
    assert asset.bid > 0
    assert asset.ask > 0

    # Market closed: quotes degrade to None (null in JSON)
    mock_connector._mock_market_open = False
    closed_asset = mock_connector.get_asset_info("AMZN")
    assert closed_asset is not None
    assert closed_asset.symbol == "AMZN"
    assert closed_asset.lot_min == 0.01
    assert closed_asset.bid is None
    assert closed_asset.ask is None

    # Case insensitive lookup
    mock_connector._mock_market_open = True
    lower_asset = mock_connector.get_asset_info("amzn")
    assert lower_asset is not None
    assert lower_asset.symbol == "AMZN"

    # Unknown symbol
    unknown = mock_connector.get_asset_info("UNKNOWN_TICKER")
    assert unknown is None


def test_scenario_6_gateway_disconnected_error_contract():
    """
    Scenario 6: Gateway Disconnected Error Contract.
    Given MT5Connector is disconnected (is_connected=False and not mock mode)
    When calling get_available_assets() or get_asset_info()
    Then raises ConnectionError with 'MetaTrader 5 gateway disconnected'.
    """
    config = StrategyConfig(mock_mode=False)
    connector = MT5Connector(config)
    connector.is_connected = False

    with pytest.raises(ConnectionError) as exc_info1:
        connector.get_available_assets()
    assert str(exc_info1.value) == "MetaTrader 5 gateway disconnected"

    with pytest.raises(ConnectionError) as exc_info2:
        connector.get_asset_info("AMZN")
    assert str(exc_info2.value) == "MetaTrader 5 gateway disconnected"


def test_scenario_7_cache_invalidation_on_account_switch(mock_connector):
    """
    Scenario 7: Cache Invalidation on Account Switching & Concurrent Read Safety.
    Given asset cache is populated
    When initialize() is called (operator switches accounts)
    Then in-memory cache is immediately cleared under self._lock.
    """
    # Populate cache
    initial_assets = mock_connector.get_available_assets()
    assert len(initial_assets) == 8
    assert len(mock_connector._symbols_cache) == 8

    # Switch accounts / re-initialize
    mock_connector.initialize()
    # Cache cleared during initialize
    assert len(mock_connector._symbols_cache) == 0

    # Subsequent request repopulates cache
    repopulated = mock_connector.get_available_assets()
    assert len(repopulated) == 8
    assert len(mock_connector._symbols_cache) == 8


def test_scenario_7_concurrent_read_safety_during_cache_invalidation(mock_connector):
    """
    Scenario 7 Concurrency: Multi-threaded test verifying that taking shallow snapshots
    under self._lock prevents 'RuntimeError: dictionary changed size during iteration'
    while concurrent threads invalidate/repopulate the cache.
    """
    errors = []
    stop_event = threading.Event()

    def reader_task():
        while not stop_event.is_set():
            try:
                assets = mock_connector.get_available_assets(category="stocks", search="a")
                assert isinstance(assets, list)
                info = mock_connector.get_asset_info("AMZN")
                if info is not None:
                    assert info.symbol == "AMZN"
            except Exception as e:
                errors.append(e)

    def invalidator_task():
        while not stop_event.is_set():
            try:
                mock_connector.clear_cache()
                time.sleep(0.001)
            except Exception as e:
                errors.append(e)

    readers = [threading.Thread(target=reader_task) for _ in range(6)]
    invalidators = [threading.Thread(target=invalidator_task) for _ in range(2)]

    for t in readers + invalidators:
        t.start()

    time.sleep(0.3)
    stop_event.set()

    for t in readers + invalidators:
        t.join(timeout=2.0)

    assert errors == [], f"Concurrent read errors detected: {errors}"


def test_live_path_normalization_and_visibility_without_symbol_select():
    """
    Scenario 1 Live MT5 mock verification:
    Verifies that symbols with Windows backslash paths ('Stocks\\US\\Nasdaq\\AMZN')
    are normalized to forward slashes, visible=False is preserved, and no symbol_select is called.
    """
    config = StrategyConfig(mock_mode=False)
    connector = MT5Connector(config)
    connector.is_connected = True

    mock_symbol_1 = MagicMock()
    mock_symbol_1.name = "AMZN"
    mock_symbol_1.description = "Amazon.com Inc"
    mock_symbol_1.path = r"Stocks\US\Nasdaq\AMZN"
    mock_symbol_1.currency_profit = "USD"
    mock_symbol_1.currency_base = "USD"
    mock_symbol_1.visible = False
    mock_symbol_1.volume_min = 0.01
    mock_symbol_1.volume_max = 100.0
    mock_symbol_1.volume_step = 0.01
    mock_symbol_1.digits = 2
    mock_symbol_1.point = 0.01
    mock_symbol_1.filling_mode = 1
    mock_symbol_1.trade_mode = 4

    mock_symbol_2 = MagicMock()
    mock_symbol_2.name = "EURUSD"
    mock_symbol_2.description = "Euro vs US Dollar"
    mock_symbol_2.path = r"Forex\Majors\EURUSD"
    mock_symbol_2.currency_profit = "USD"
    mock_symbol_2.currency_base = "EUR"
    mock_symbol_2.visible = True
    mock_symbol_2.volume_min = 0.01
    mock_symbol_2.volume_max = 100.0
    mock_symbol_2.volume_step = 0.01
    mock_symbol_2.digits = 5
    mock_symbol_2.point = 0.00001
    mock_symbol_2.filling_mode = 1
    mock_symbol_2.trade_mode = 4

    with patch("strategy_engine.mt5_connector.HAS_MT5", True), patch(
        "strategy_engine.mt5_connector.mt5"
    ) as mock_mt5:
        mock_mt5.symbols_get.return_value = [mock_symbol_1, mock_symbol_2]

        assets = connector.get_available_assets(category="stocks")
        assert len(assets) == 1
        asset = assets[0]
        assert asset.symbol == "AMZN"
        assert asset.category == "Stocks/US/Nasdaq/AMZN"
        assert asset.visible is False
        assert asset.bid is None
        assert asset.ask is None

        # Verify symbols_get was called once and symbol_select was never called
        mock_mt5.symbols_get.assert_called_once()
        assert not hasattr(mock_mt5, "symbol_select") or mock_mt5.symbol_select.call_count == 0


def test_live_single_symbol_closed_market_tick_degradation():
    """
    Scenario 5 Live MT5 mock verification:
    When mt5.symbol_info_tick returns None (market closed / weekend),
    bid and ask degrade gracefully to None.
    """
    config = StrategyConfig(mock_mode=False)
    connector = MT5Connector(config)
    connector.is_connected = True

    mock_s = MagicMock()
    mock_s.name = "AMZN"
    mock_s.description = "Amazon.com Inc"
    mock_s.path = r"Stocks\US\Nasdaq\AMZN"
    mock_s.currency_profit = "USD"
    mock_s.visible = True
    mock_s.volume_min = 0.01
    mock_s.volume_max = 100.0
    mock_s.volume_step = 0.01
    mock_s.digits = 2
    mock_s.point = 0.01
    mock_s.filling_mode = 1
    mock_s.trade_mode = 4
    mock_s.bid = 0.0
    mock_s.ask = 0.0

    with patch("strategy_engine.mt5_connector.HAS_MT5", True), patch(
        "strategy_engine.mt5_connector.mt5"
    ) as mock_mt5:
        mock_mt5.symbol_info.return_value = mock_s
        mock_mt5.symbol_info_tick.return_value = None

        info = connector.get_asset_info("AMZN")
        assert info is not None
        assert info.symbol == "AMZN"
        assert info.category == "Stocks/US/Nasdaq/AMZN"
        assert info.bid is None
        assert info.ask is None
