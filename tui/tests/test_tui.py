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
from textual.widgets import Button


from strategy_engine.models import (
    AccountConnectRequest,
    AccountConnectResponse,
    AccountInfo,
    ConnectionState,
    ConnectionStatus,
    OrderType,
    Position,
)
from tui.api_client import DarwinApiClient
from tui.app import DarwinTraderApp
from tui.screens.connect_modal import ConnectModal
from tui.screens.confirm_modal import ConfirmModal
from tui.widgets.header_bar import HeaderBar
from tui.widgets.summary_cards import SummaryCards, MetricCard
from tui.widgets.positions_table import PositionsTable
from tui.widgets.strategy_panel import StrategyPanel


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
    mock_client.get_positions.return_value = []
    mock_client.get_strategy_status.return_value = {
        "status": "IDLE",
        "strategy_name": "Darwin_Trend_ATR_V1",
        "symbol": "EURUSD",
        "account_balance": 100000.0,
        "account_equity": 100000.0,
    }

    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test() as pilot:
        await pilot.pause()
        badge = app.query_one("#status-badge")
        info = app.query_one("#telemetry-info")

        assert "[● CONNECTED (LIVE)]" in str(badge.content)
        assert "Server: Darwinex-Live" in str(info.content)
        assert "Login: 1234567" in str(info.content)


@pytest.mark.asyncio
async def test_summary_cards_dual_glyph_and_formatting():
    """Verify Scenario 1: SummaryCards dual glyphs (▲/▼) and USD currency formatting."""
    app = DarwinTraderApp()
    async with app.run_test():
        summary = app.query_one(SummaryCards)

        # 1. Test positive profit
        info_pos = AccountInfo(
            login=1001,
            balance=104000.0,
            equity=106500.0,
            margin=1500.0,
            profit=2500.0,
        )
        summary.update_metrics(account_info=info_pos)

        card_bal = summary.query_one("#card-balance-value")
        card_eq = summary.query_one("#card-equity-value")
        card_mar = summary.query_one("#card-margin-value")
        card_pnl = summary.query_one("#card-pnl-value")
        pnl_card = summary.query_one("#card-pnl", MetricCard)

        assert str(card_bal.content) == "$104,000.00"
        assert str(card_eq.content) == "$106,500.00"
        assert str(card_mar.content) == "$1,500.00"
        assert "▲ +$2,500.00" in str(card_pnl.content)
        assert "profit-positive" in pnl_card.classes

        # 2. Test negative profit
        info_neg = AccountInfo(
            login=1001,
            balance=100000.0,
            equity=98500.0,
            margin=2000.0,
            profit=-1500.0,
        )
        summary.update_metrics(account_info=info_neg)
        assert "▼ -$1,500.00" in str(card_pnl.content)
        assert "profit-negative" in pnl_card.classes

        # 3. Test zero profit
        summary.update_metrics(floating_pnl=0.0)
        assert "$0.00" in str(card_pnl.content)
        assert "profit-neutral" in pnl_card.classes


@pytest.mark.asyncio
async def test_positions_table_rendering_and_in_place_updates():
    """Verify Scenario 2: PositionsTable renders tickets and performs in-place cell updates."""
    app = DarwinTraderApp()
    async with app.run_test():
        table_container = app.query_one(PositionsTable)
        data_table = table_container.query_one("#positions-data-table")

        pos1 = Position(
            ticket=1001,
            symbol="EURUSD",
            order_type=OrderType.BUY,
            volume=1.00,
            open_price=1.08500,
            current_price=1.08600,
            sl=1.08000,
            tp=1.09500,
            pnl=100.0,
            swap=2.50,
        )
        pos2 = Position(
            ticket=1002,
            symbol="GBPUSD",
            order_type=OrderType.SELL,
            volume=0.50,
            open_price=1.27500,
            current_price=1.27600,
            sl=1.28000,
            tp=1.26500,
            pnl=-50.0,
            swap=-1.20,
        )

        table_container.update_positions([pos1, pos2])
        assert data_table.row_count == 2
        assert 1001 in table_container._row_keys
        assert 1002 in table_container._row_keys

        # Check values
        cell_curr = data_table.get_cell("1001", "current_price")
        assert cell_curr == "1.08600"
        cell_pnl = data_table.get_cell("1001", "pnl")
        assert "▲ +$100.00" in str(cell_pnl)

        cell_pnl2 = data_table.get_cell("1002", "pnl")
        assert "▼ -$50.00" in str(cell_pnl2)

        # Update in-place: ticket 1001 ticks from 1.08600 -> 1.08650, PnL 100 -> 150
        pos1_ticked = Position(
            ticket=1001,
            symbol="EURUSD",
            order_type=OrderType.BUY,
            volume=1.00,
            open_price=1.08500,
            current_price=1.08650,
            sl=1.08000,
            tp=1.09500,
            pnl=150.0,
            swap=2.50,
        )
        table_container.update_positions([pos1_ticked, pos2])
        assert data_table.row_count == 2
        assert data_table.get_cell("1001", "current_price") == "1.08650"
        assert "▲ +$150.00" in str(data_table.get_cell("1001", "pnl"))

        # Close ticket 1002
        table_container.update_positions([pos1_ticked])
        assert data_table.row_count == 1
        assert 1002 not in table_container._row_keys
        assert 1001 in table_container._row_keys


@pytest.mark.asyncio
async def test_positions_table_offline_cache_preservation():
    """Verify PositionsTable preserves rows when backend is offline and marks as STALE."""
    app = DarwinTraderApp()
    async with app.run_test():
        table_container = app.query_one(PositionsTable)
        data_table = table_container.query_one("#positions-data-table")

        pos = Position(
            ticket=2001,
            symbol="USDJPY",
            order_type=OrderType.BUY,
            volume=0.20,
            open_price=155.0,
            current_price=155.2,
            pnl=40.0,
        )
        table_container.update_positions([pos])
        assert data_table.row_count == 1

        # Now trigger offline update
        table_container.update_positions([], is_offline=True)
        assert data_table.row_count == 1
        title = table_container.query_one("#positions-table-title")
        assert "STALE / OFFLINE CACHE" in str(title.content)


@pytest.mark.asyncio
async def test_responsive_layout_collapse_below_80_columns():
    """Verify Scenario 7: Terminal resize below 80 columns or 24 rows triggers compact-grid layout."""
    app = DarwinTraderApp()
    async with app.run_test() as pilot:
        summary = app.query_one(SummaryCards)

        # Set size below 80 cols (e.g. 75x30)
        await pilot.resize_terminal(75, 30)
        await pilot.pause()
        assert "compact-grid" in summary.classes

        # Set size >= 80 cols (e.g. 100x30)
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        assert "compact-grid" not in summary.classes


@pytest.mark.asyncio
async def test_strategy_panel_rendering_and_telemetry():
    """Verify StrategyPanel renders state, drawdown, and exposure accurately."""
    mock_client = AsyncMock(spec=DarwinApiClient)
    mock_client.get_account_status.return_value = ConnectionStatus(
        status=ConnectionState.CONNECTED,
        server="Darwinex-Demo",
    )
    mock_client.get_positions.return_value = []
    mock_client.get_strategy_status.return_value = {"status": "IDLE"}

    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test():
        strat = app.query_one(StrategyPanel)
        state_widget = strat.query_one("#strategy-state-value")
        name_widget = strat.query_one("#strategy-name-value")
        drawdown_widget = strat.query_one("#strategy-drawdown-value")
        exposure_widget = strat.query_one("#strategy-exposure-value")

        # Initial state
        assert "[● IDLE]" in str(state_widget.content)
        assert "0.00 lots" in str(exposure_widget.content)

        # Update running with positions
        pos1 = Position(
            ticket=101,
            symbol="EURUSD",
            order_type=OrderType.BUY,
            volume=1.5,
            open_price=1.08,
            current_price=1.085,
        )
        pos2 = Position(
            ticket=102,
            symbol="EURUSD",
            order_type=OrderType.SELL,
            volume=0.5,
            open_price=1.08,
            current_price=1.085,
        )

        strat_data = {
            "status": "RUNNING",
            "strategy_name": "Darwin_Trend_ATR_V1",
            "symbol": "EURUSD",
            "account_balance": 100000.0,
            "account_equity": 98000.0, # 2% drawdown
        }
        strat.update_telemetry(strategy_data=strat_data, positions=[pos1, pos2])

        assert "[● RUNNING]" in str(state_widget.content)
        assert "state-running" in state_widget.classes
        assert "2.00%" in str(drawdown_widget.content)
        assert "drawdown-normal" in drawdown_widget.classes
        assert "2.00 lots" in str(exposure_widget.content)

        # Drawdown breach (>= 3.0%)
        strat_data_breach = {
            "status": "PAUSED",
            "strategy_name": "Darwin_Trend_ATR_V1",
            "symbol": "EURUSD",
            "account_balance": 100000.0,
            "account_equity": 96500.0, # 3.5% drawdown
        }
        strat.update_telemetry(strategy_data=strat_data_breach, positions=[pos1])
        assert "[⏸ PAUSED]" in str(state_widget.content)
        assert "state-paused" in state_widget.classes
        assert "3.50%" in str(drawdown_widget.content)
        assert "drawdown-warning" in drawdown_widget.classes
        assert "1.50 lots" in str(exposure_widget.content)

        # Offline state
        strat.update_telemetry(is_offline=True)
        title = strat.query_one("#strategy-panel-title")
        assert "OFFLINE" in str(title.content)
        assert "[○ UNKNOWN]" in str(state_widget.content)


@pytest.mark.asyncio
async def test_kill_switch_with_open_positions_scenario_4():
    """Verify Scenario 4: Safeguarded Emergency Kill Switch with Open Positions (Hotkey K)."""
    mock_client = AsyncMock(spec=DarwinApiClient)
    mock_client.get_account_status.return_value = ConnectionStatus(
        status=ConnectionState.CONNECTED,
        server="Darwinex-Live",
        account_info=AccountInfo(login=55555, server="Darwinex-Live", balance=10000.0, equity=10000.0),
    )
    mock_positions = [
        Position(
            ticket=501,
            symbol="EURUSD",
            order_type=OrderType.BUY,
            volume=1.0,
            open_price=1.08,
            current_price=1.082,
        ),
        Position(
            ticket=502,
            symbol="GBPUSD",
            order_type=OrderType.SELL,
            volume=0.5,
            open_price=1.28,
            current_price=1.278,
        ),
    ]
    mock_client.get_positions.return_value = mock_positions
    mock_client.get_strategy_status.return_value = {
        "status": "RUNNING",
        "strategy_name": "Darwin_Trend_ATR_V1",
        "symbol": "EURUSD",
    }
    mock_client.kill_switch.return_value = {
        "message": "Emergency Kill Switch Activated",
        "positions_closed": 2,
        "detail": "Closed 2 positions",
        "status": "PAUSED",
    }

    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test() as pilot:
        await pilot.pause()

        # Press hotkey K
        await pilot.press("k")
        await pilot.pause()

        # Danger dialog must be displayed
        assert isinstance(app.screen, ConfirmModal)
        assert app.screen.is_danger is True
        prompt = app.screen.query_one("#confirm-prompt")
        assert "Are you sure you want to close ALL positions and pause strategy?" in str(prompt.content)

        # After confirming, simulate backend positions returning empty and status PAUSED
        mock_client.get_positions.return_value = []
        mock_client.get_strategy_status.return_value = {
            "status": "PAUSED",
            "strategy_name": "Darwin_Trend_ATR_V1",
            "symbol": "EURUSD",
        }

        # Click Yes (Confirm)
        await pilot.click("#btn-confirm")
        await pilot.pause(0.1)
        await app.workers.wait_for_complete()
        await pilot.pause()

        # Verify kill_switch API was called
        mock_client.kill_switch.assert_awaited_once()

        # Verify positions table is empty and strategy is paused
        table = app.query_one(PositionsTable)
        assert table.query_one("#positions-data-table").row_count == 0
        strat_panel = app.query_one(StrategyPanel)
        state_badge = strat_panel.query_one("#strategy-state-value")
        assert "[⏸ PAUSED]" in str(state_badge.content)


@pytest.mark.asyncio
async def test_kill_switch_with_zero_positions_scenario_8():
    """Verify Scenario 8: Kill-Switch Invocation with Zero Open Positions (Hotkey K)."""
    mock_client = AsyncMock(spec=DarwinApiClient)
    mock_client.get_account_status.return_value = ConnectionStatus(
        status=ConnectionState.CONNECTED,
        server="Darwinex-Live",
        account_info=AccountInfo(login=55555, server="Darwinex-Live", balance=10000.0, equity=10000.0),
    )
    mock_client.get_positions.return_value = []
    mock_client.get_strategy_status.return_value = {
        "status": "RUNNING",
        "strategy_name": "Darwin_Trend_ATR_V1",
        "symbol": "EURUSD",
    }
    mock_client.pause_strategy.return_value = {
        "message": "Strategy paused",
        "status": "PAUSED",
    }

    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test() as pilot:
        await pilot.pause()

        # Press hotkey K
        await pilot.press("k")
        await pilot.pause()

        # Informational prompt must be displayed (not danger)
        assert isinstance(app.screen, ConfirmModal)
        assert app.screen.is_danger is False
        prompt = app.screen.query_one("#confirm-prompt")
        assert "No active positions to liquidate; strategy paused" in str(prompt.content)

        mock_client.get_strategy_status.return_value = {
            "status": "PAUSED",
            "strategy_name": "Darwin_Trend_ATR_V1",
            "symbol": "EURUSD",
        }

        # Confirm
        await pilot.click("#btn-confirm")
        await pilot.pause(0.1)
        await app.workers.wait_for_complete()
        await pilot.pause()

        # Verify pause_strategy was called, and kill_switch was NOT called
        mock_client.pause_strategy.assert_awaited_once()
        mock_client.kill_switch.assert_not_awaited()

        strat_panel = app.query_one(StrategyPanel)
        state_badge = strat_panel.query_one("#strategy-state-value")
        assert "[⏸ PAUSED]" in str(state_badge.content)


@pytest.mark.asyncio
async def test_connect_modal_success_and_account_switching_scenario_3():
    """Verify Scenario 3: Account Switching via Connection Modal (F2/C)."""
    mock_client = AsyncMock(spec=DarwinApiClient)
    mock_client.get_account_status.return_value = ConnectionStatus(
        status=ConnectionState.CONNECTED,
        server="Darwinex-Demo",
        account_info=AccountInfo(login=111111, server="Darwinex-Demo"),
    )
    mock_client.get_positions.return_value = []
    mock_client.get_strategy_status.return_value = {
        "status": "CONNECTED",
        "strategy_name": "Darwin_Trend_ATR_V1",
        "symbol": "EURUSD",
    }
    mock_client.connect_account.return_value = AccountConnectResponse(
        status=ConnectionState.CONNECTED,
        message="Connected to live account",
        login=999888,
        server="Darwinex-Live",
        trade_mode="REAL",
        balance=75000.0,
        account_info=AccountInfo(login=999888, server="Darwinex-Live", balance=75000.0, equity=76000.0),
    )

    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()

        # Press F2 to open ConnectModal
        await pilot.press("f2")
        await pilot.pause()
        assert isinstance(app.screen, ConnectModal)

        # Fill in credentials
        login_input = app.screen.query_one("#input-login")
        login_input.value = "999888"
        password_input = app.screen.query_one("#input-password")
        password_input.value = "secret_pass"

        # Update client return for next poll
        mock_client.get_account_status.return_value = ConnectionStatus(
            status=ConnectionState.CONNECTED,
            server="Darwinex-Live",
            mock_mode=False,
            account_info=AccountInfo(login=999888, server="Darwinex-Live", balance=75000.0, equity=76000.0),
        )

        # Click Connect button
        modal = app.screen
        modal.query_one("#btn-submit", Button).press()
        await pilot.pause(0.1)

        # Modal must be dismissed on success
        assert not isinstance(app.screen, ConnectModal)

        # Verify telemetry updated to new account
        header = app.query_one(HeaderBar)
        info_widget = header.query_one("#telemetry-info")
        assert "Login: 999888" in str(info_widget.content)
        assert "Server: Darwinex-Live" in str(info_widget.content)


@pytest.mark.asyncio
async def test_connect_modal_error_banner_scenario_6():
    """Verify Scenario 6: Invalid Credentials Handling in Connect Modal displays error banner."""
    mock_client = AsyncMock(spec=DarwinApiClient)
    mock_client.connect_account.return_value = AccountConnectResponse(
        status=ConnectionState.ERROR,
        message="MT5 initialize failed: Invalid account login or password",
        error="Invalid account login or password",
        login=123,
        server="Darwinex-Live",
    )
    mock_client.get_account_status.return_value = ConnectionStatus(
        status=ConnectionState.CONNECTED,
        server="Darwinex-Live",
    )
    mock_client.get_positions.return_value = []
    mock_client.get_strategy_status.return_value = {"status": "IDLE"}

    modal = ConnectModal(api_client=mock_client)
    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test(size=(80, 40)) as pilot:
        app.push_screen(modal)
        await pilot.pause()

        modal.query_one("#input-login").value = "123"
        modal.query_one("#input-password").value = "wrong_password"

        # Submit
        modal.query_one("#btn-submit", Button).press()
        await pilot.pause()

        # Modal remains open
        assert app.screen is modal
        banner = modal.query_one("#error-banner")
        assert "visible" in banner.classes
        assert "Invalid account login or password" in str(banner.content)
        # Input fields preserved
        assert modal.query_one("#input-login").value == "123"

