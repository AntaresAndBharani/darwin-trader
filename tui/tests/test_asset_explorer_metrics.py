"""
Widget test suite for TUI Asset Explorer Metrics Drawer.
Covers Scenario 7: State synchronization, 150ms debounced interaction,
Dynamic Kalman Beta and OLS Beta rendering, amber degradation badges,
and stale response discard during rapid cursor navigation.
"""
import asyncio
from unittest.mock import AsyncMock
import pytest
from textual.widgets import DataTable, Static

from strategy_engine.models import AssetInfo, ConnectionState, ConnectionStatus
from tui.api_client import AssetMetricsResponse, DarwinApiClient
from tui.app import DarwinTraderApp
from tui.screens.asset_explorer_modal import AssetExplorerModal


@pytest.fixture
def mock_client() -> AsyncMock:
    client = AsyncMock(spec=DarwinApiClient)
    client.get_account_status.return_value = ConnectionStatus(status=ConnectionState.CONNECTED, server="Live")
    client.get_positions.return_value = []
    client.get_strategy_status.return_value = {"status": "IDLE"}
    client.get_assets.return_value = [
        AssetInfo(symbol="NVDA", description="NVIDIA", category="Stocks/US/Nasdaq"),
        AssetInfo(symbol="AAPL", description="Apple", category="Stocks/US/Nasdaq"),
    ]
    return client


@pytest.mark.asyncio
async def test_scenario_7_metrics_drawer_state_sync_and_stale_discard(mock_client: AsyncMock):
    """Scenario 7: TUI Asset Explorer Metrics Drawer State Synchronization."""
    nvda_metrics = AssetMetricsResponse(symbol="NVDA", kalman_beta=1.4850, ols_beta=1.4500, yang_zhang_vol_annualized=0.45)
    aapl_metrics = AssetMetricsResponse(symbol="AAPL", kalman_beta=1.2500, ols_beta=1.2000, yang_zhang_vol_annualized=0.225)
    aapl_event = asyncio.Event()

    async def fake_get_metrics(symbol: str):
        if symbol == "NVDA":
            return nvda_metrics
        elif symbol == "AAPL":
            await aapl_event.wait()
            return aapl_metrics
        return None

    mock_client.get_asset_metrics.side_effect = fake_get_metrics
    modal = AssetExplorerModal(api_client=mock_client, debounce_delay=0.3)
    app = DarwinTraderApp(api_client=mock_client)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(modal)
        await pilot.pause(0.1)

        drawer = modal.query_one("#institutional-metrics-drawer")
        header = modal.query_one("#metrics-drawer-header", Static)
        content = modal.query_one("#metrics-drawer-content", Static)

        # Given: Asset Explorer modal open with metrics drawer expanded for NVDA
        await pilot.press("i")
        await pilot.pause(0.1)
        assert "visible" in drawer.classes
        assert "NVDA" in str(header.content)
        assert "Dynamic Kalman Beta" in str(content.content) and "1.4850" in str(content.content)
        assert "OLS Beta" in str(content.content) and "1.4500" in str(content.content)

        # When: user navigates down to select AAPL
        modal.query_one("#assets-data-table", DataTable).focus()
        await pilot.press("down")

        # Then: drawer immediately updates its status label to "Loading metrics for AAPL..." synchronously
        assert "AAPL" in str(header.content)
        assert "Loading metrics for AAPL..." in str(content.content)
        assert modal._metrics_request_symbol == "AAPL"

        # And: HTTP API call to get_asset_metrics is debounced by 300ms
        await pilot.pause(0.05)
        assert not any(c.args and c.args[0] == "AAPL" for c in mock_client.get_asset_metrics.call_args_list)

        # Debounce timer fires after 300ms
        await pilot.pause(0.35)
        assert any(c.args and c.args[0] == "AAPL" for c in mock_client.get_asset_metrics.call_args_list)

        # And: when metrics API response for AAPL resolves
        aapl_event.set()
        await pilot.pause(0.1)
        assert modal._current_metrics.symbol == "AAPL"
        assert "AAPL" in str(header.content)
        assert "Dynamic Kalman Beta" in str(content.content) and "1.2500" in str(content.content)
        assert "OLS Beta" in str(content.content) and "1.2000" in str(content.content)

        # And: if delayed response for NVDA arrives afterward, it is discarded without overwriting AAPL
        await modal._fetch_metrics("NVDA")
        await pilot.pause(0.1)
        assert modal._current_metrics.symbol == "AAPL"
        assert "AAPL" in str(header.content)
        assert "1.2500" in str(content.content)


@pytest.mark.asyncio
async def test_metrics_drawer_amber_degradation_badges(mock_client: AsyncMock):
    """Verify drawer renders amber degradation badges for uncached benchmark."""
    degraded = AssetMetricsResponse(
        symbol="NVDA", kalman_beta=None, ols_beta=None,
        data_flags=["[BENCHMARK: UNCACHED (STANDALONE REGIME)]"], yang_zhang_vol_annualized=0.45,
    )
    mock_client.get_asset_metrics.return_value = degraded
    modal = AssetExplorerModal(api_client=mock_client, debounce_delay=0.0)
    app = DarwinTraderApp(api_client=mock_client)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(modal)
        await pilot.pause(0.1)

        await pilot.press("I")
        await pilot.pause(0.05)
        header = modal.query_one("#metrics-drawer-header", Static)
        content = modal.query_one("#metrics-drawer-content", Static)
        assert "[BENCHMARK: UNCACHED (STANDALONE REGIME)]" in str(header.content)
        assert "[BENCHMARK: UNCACHED (STANDALONE REGIME)]" in str(content.content)
        assert "Dynamic Kalman Beta" in str(content.content) and "--" in str(content.content)


@pytest.mark.asyncio
async def test_metrics_drawer_keybinding_toggles(mock_client: AsyncMock):
    """Verify both 'i' and 'I' toggle the drawer open and closed."""
    modal = AssetExplorerModal(api_client=mock_client, debounce_delay=0.0)
    app = DarwinTraderApp(api_client=mock_client)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(modal)
        await pilot.pause(0.1)
        drawer = modal.query_one("#institutional-metrics-drawer")
        assert "visible" not in drawer.classes
        await pilot.press("i")
        await pilot.pause(0.05)
        assert "visible" in drawer.classes
        await pilot.press("I")
        await pilot.pause(0.05)
        assert "visible" not in drawer.classes
