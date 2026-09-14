"""
Unit and integration tests for Darwin Trader TUI.
Covers:
- DarwinApiClient with mock responses and offline fallback behavior
- HeaderBar visual badge formatting (Live, Demo, Simulation, Unreachable)
- DarwinTraderApp base layout, mounting, and dual keybindings (F2 and C)
"""
import pytest
import httpx
from unittest.mock import AsyncMock


from strategy_engine.models import (
    AccountConnectRequest,
    AccountInfo,
    ConnectionState,
    ConnectionStatus,
)
from tui.api_client import DarwinApiClient
from tui.app import DarwinTraderApp
from tui.screens.connect_modal import ConnectModal
from tui.widgets.header_bar import HeaderBar


@pytest.mark.asyncio
async def test_api_client_offline_fallback_status():
    """Verify that when backend is unreachable, get_account_status returns DISCONNECTED with error."""
    # Using a non-routable port to guarantee connection failure
    client = DarwinApiClient(base_url="http://127.0.0.1:59999", timeout=0.1)
    status = await client.get_account_status()

    assert status.status == ConnectionState.DISCONNECTED
    assert status.last_error is not None
    assert len(status.last_error) > 0
    await client.close()


@pytest.mark.asyncio
async def test_api_client_offline_fallback_positions_and_info():
    """Verify that info returns None and positions returns empty list when offline."""
    client = DarwinApiClient(base_url="http://127.0.0.1:59999", timeout=0.1)
    info = await client.get_account_info()
    assert info is None

    positions = await client.get_positions()
    assert positions == []

    strategy = await client.get_strategy_status()
    assert strategy is None

    kill_res = await client.kill_switch()
    assert kill_res["status"] == "ERROR"
    await client.close()


@pytest.mark.asyncio
async def test_api_client_offline_fallback_connect():
    """Verify that connect_account returns an ERROR response rather than raising when offline."""
    client = DarwinApiClient(base_url="http://127.0.0.1:59999", timeout=0.1)
    req = AccountConnectRequest(login=12345, server="Darwinex-Live")
    resp = await client.connect_account(req)

    assert resp.status == ConnectionState.ERROR
    assert resp.login == 12345
    assert resp.server == "Darwinex-Live"
    assert resp.error is not None
    await client.close()


@pytest.mark.asyncio
async def test_api_client_mock_responses():
    """Verify DarwinApiClient parsing against a custom mocked httpx Transport/Client."""
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/account/status":
            return httpx.Response(
                200,
                json={
                    "status": "CONNECTED",
                    "server": "Darwinex-Live",
                    "mock_mode": False,
                    "latency_ms": 12.5,
                    "account_info": {
                        "login": 998877,
                        "trade_mode": "REAL",
                        "server": "Darwinex-Live",
                        "balance": 50000.0,
                        "equity": 52000.0,
                    },
                },
            )
        elif request.url.path == "/api/v1/account/positions":
            return httpx.Response(
                200,
                json=[
                    {
                        "ticket": 101,
                        "symbol": "EURUSD",
                        "order_type": "BUY",
                        "volume": 1.0,
                        "open_price": 1.0850,
                        "current_price": 1.0860,
                        "pnl": 100.0,
                    }
                ],
            )
        elif request.url.path == "/api/v1/account/connect":
            return httpx.Response(
                200,
                json={
                    "status": "CONNECTED",
                    "message": "Connected successfully",
                    "login": 998877,
                    "server": "Darwinex-Live",
                    "trade_mode": "REAL",
                    "balance": 50000.0,
                    "currency": "USD",
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    mock_http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    api_client = DarwinApiClient(client=mock_http_client)

    status = await api_client.get_account_status()
    assert status.status == ConnectionState.CONNECTED
    assert status.server == "Darwinex-Live"
    assert status.latency_ms == 12.5
    assert status.account_info.login == 998877

    positions = await api_client.get_positions()
    assert len(positions) == 1
    assert positions[0].ticket == 101
    assert positions[0].symbol == "EURUSD"

    req = AccountConnectRequest(login=998877, server="Darwinex-Live")
    conn_resp = await api_client.connect_account(req)
    assert conn_resp.status == ConnectionState.CONNECTED
    assert conn_resp.login == 998877

    await api_client.close()
    await mock_http_client.aclose()


@pytest.mark.asyncio
async def test_header_bar_badge_modes():
    """Verify HeaderBar updates badges according to live, demo, simulation, and offline states."""
    app = DarwinTraderApp()
    async with app.run_test():
        header = app.query_one(HeaderBar)
        badge = header.query_one("#status-badge")

        # 1. Live status
        live_status = ConnectionStatus(
            status=ConnectionState.CONNECTED,
            server="Darwinex-Live",
            mock_mode=False,
            latency_ms=15.0,
            account_info=AccountInfo(login=112233, server="Darwinex-Live"),
        )
        header.update_telemetry(live_status)
        assert "[● CONNECTED (LIVE)]" in str(badge.content)
        assert "status-connected-live" in badge.classes

        # 2. Demo status
        demo_status = ConnectionStatus(
            status=ConnectionState.CONNECTED,
            server="Darwinex-Demo",
            mock_mode=False,
            latency_ms=10.0,
            account_info=AccountInfo(login=445566, server="Darwinex-Demo"),
        )
        header.update_telemetry(demo_status)
        assert "[● CONNECTED (DEMO)]" in str(badge.content)
        assert "status-connected-demo" in badge.classes

        # 3. Simulation status
        sim_status = ConnectionStatus(
            status=ConnectionState.CONNECTED,
            server="Darwinex-Live",
            mock_mode=True,
            latency_ms=5.0,
            account_info=AccountInfo(login=778899, server="Darwinex-Live"),
        )
        header.update_telemetry(sim_status)
        assert "[● SIMULATION]" in str(badge.content)
        assert "status-simulation" in badge.classes

        # 4. Offline status
        offline_status = ConnectionStatus(
            status=ConnectionState.DISCONNECTED,
            server="Unknown",
            mock_mode=True,
            last_error="Connection refused",
        )
        header.update_telemetry(offline_status, reconnect_seconds=2)
        assert "[○ GATEWAY UNREACHABLE (2s)]" in str(badge.content)
        assert "status-offline" in badge.classes


@pytest.mark.asyncio
async def test_app_keybindings_f2_and_c():
    """Verify that pressing F2, C, or clicking Connect button opens the ConnectModal dialog."""
    app = DarwinTraderApp()
    async with app.run_test() as pilot:
        # Initial state: only default screen active
        assert len(app.screen_stack) == 1

        # Press F2 -> ConnectModal opens
        await pilot.press("f2")
        await pilot.pause()
        assert isinstance(app.screen, ConnectModal)
        assert len(app.screen_stack) == 2

        # Dismiss modal
        app.screen.dismiss()
        await pilot.pause()
        assert len(app.screen_stack) == 1

        # Press C -> ConnectModal opens
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, ConnectModal)
        assert len(app.screen_stack) == 2

        # Dismiss modal
        app.screen.dismiss()
        await pilot.pause()
        assert len(app.screen_stack) == 1

        # Click Connect button -> ConnectModal opens
        await pilot.click("#btn-connect")
        await pilot.pause()
        assert isinstance(app.screen, ConnectModal)
        assert len(app.screen_stack) == 2


@pytest.mark.asyncio
async def test_app_background_polling_with_mock_client():
    """Verify that DarwinTraderApp poll_telemetry updates the HeaderBar seamlessly."""
    mock_client = AsyncMock(spec=DarwinApiClient)
    mock_client.get_account_status.return_value = ConnectionStatus(
        status=ConnectionState.CONNECTED,
        server="Darwinex-Live",
        mock_mode=False,
        latency_ms=18.4,
        account_info=AccountInfo(login=1234567, server="Darwinex-Live"),
    )

    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test() as pilot:
        await pilot.pause()
        badge = app.query_one("#status-badge")
        info = app.query_one("#telemetry-info")

        assert "[● CONNECTED (LIVE)]" in str(badge.content)
        assert "Server: Darwinex-Live" in str(info.content)
        assert "Login: 1234567" in str(info.content)
