"""
Unit and integration tests for Darwin Trader TUI.
Comprehensive BDD coverage across:
- Issue #60 DarwinX Zero BDD Scenarios (1 to 6):
  * Scenario 1: Automatic Detection of Darwinex MT5 Installation (test_connect_modal_autodetection_and_account_pinning_terminal_exists)
  * Scenario 2: Live MT5 IPC Connection for Account 4000073238 on Darwinex-Live (test_live_mt5_ipc_connection_account_4000073238_scenario_2)
  * Scenario 3: Attach to Already-Running MT5 Terminal Instance Without Password (test_mt5_attach_to_running_terminal_without_password_scenario_3)
  * Scenario 4: Terminal Error Diagnostic Mapping (test_terminal_error_diagnostic_mapping_scenario_4)
  * Scenario 5: Darwinex Zero Risk Limits Visibility & Buffer Warning (test_darwinex_zero_risk_limits_and_buffer_warning_scenario_5)
  * Scenario 6: Graceful Mock Fallback on Non-Windows or Missing Dependency (test_graceful_mock_fallback_non_windows_or_missing_dep_scenario_6)
- Core TUI Functional Scenarios:
  * Live Telemetry & Financial Metric Synchronization (test_live_telemetry_synchronization_scenario_1, test_summary_cards_dual_glyph_and_formatting)
  * Active Positions Display and Dynamic Cell Updates (test_positions_table_rendering_and_in_place_updates)
  * Account Switching via Connection Modal with Dual Keybindings (test_connect_modal_success_and_account_switching_scenario_3, test_app_keybindings_f2_and_c)
  * Safeguarded Emergency Kill Switch with Open Positions (test_kill_switch_with_open_positions_scenario_4)
  * Backend Offline at Launch & Resilient Reconnect Loop (test_backend_offline_at_launch_and_reconnect_loop_scenario_5, test_api_client_offline_fallback_status)
  * Invalid Credentials Handling in Connect Modal (test_connect_modal_error_banner_scenario_6)
  * Responsive Terminal Layout Below 80 Columns (test_responsive_layout_collapse_below_80_columns)
  * Kill-Switch Invocation with Zero Open Positions (test_kill_switch_with_zero_positions_scenario_8)
  * Simulation Mode Telemetry & Badge (test_simulation_mode_telemetry_and_badge_scenario_9, test_header_bar_badge_modes)
"""
import pytest
import httpx
from unittest.mock import AsyncMock
from textual.widgets import Button, Checkbox, Input, Select, Static


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


@pytest.mark.asyncio
async def test_live_telemetry_synchronization_scenario_1():
    """Verify Scenario 1: Live Telemetry & Financial Metric Synchronization.

    Given the FastAPI backend is running and connected to a Darwinex-Live account
    When the user launches the Darwin Trader TUI via `python -m tui`
    Then the HeaderBar displays a green "[● CONNECTED (LIVE)]" status badge with active server and account login ID
    And the SummaryCards display current Balance, Equity, Margin, and Floating P&L formatted in USD currency
    And positive Floating P&L values are dual-signaled with a green "▲" glyph, while negative values are styled with a red "▼" glyph.
    """
    mock_client = AsyncMock(spec=DarwinApiClient)
    mock_client.get_account_status.return_value = ConnectionStatus(
        status=ConnectionState.CONNECTED,
        server="Darwinex-Live",
        mock_mode=False,
        latency_ms=12.0,
        account_info=AccountInfo(
            login=987654,
            server="Darwinex-Live",
            balance=50000.0,
            equity=52500.0,
            margin=1200.0,
            profit=2500.0,
        ),
    )
    mock_client.get_positions.return_value = []
    mock_client.get_strategy_status.return_value = {
        "status": "IDLE",
        "strategy_name": "Darwin_Trend_ATR_V1",
        "symbol": "EURUSD",
    }

    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test() as pilot:
        await pilot.pause()

        # Check HeaderBar
        badge = app.query_one("#status-badge")
        info = app.query_one("#telemetry-info")
        assert "[● CONNECTED (LIVE)]" in str(badge.content)
        assert "status-connected-live" in badge.classes
        assert "Server: Darwinex-Live" in str(info.content)
        assert "Login: 987654" in str(info.content)

        # Check SummaryCards
        summary = app.query_one(SummaryCards)
        bal_val = summary.query_one("#card-balance-value")
        eq_val = summary.query_one("#card-equity-value")
        mar_val = summary.query_one("#card-margin-value")
        pnl_val = summary.query_one("#card-pnl-value")
        pnl_card = summary.query_one("#card-pnl", MetricCard)

        assert str(bal_val.content) == "$50,000.00"
        assert str(eq_val.content) == "$52,500.00"
        assert str(mar_val.content) == "$1,200.00"
        assert "▲ +$2,500.00" in str(pnl_val.content)
        assert "profit-positive" in pnl_card.classes

        # Negative Floating P&L transition
        mock_client.get_account_status.return_value = ConnectionStatus(
            status=ConnectionState.CONNECTED,
            server="Darwinex-Live",
            mock_mode=False,
            latency_ms=14.0,
            account_info=AccountInfo(
                login=987654,
                server="Darwinex-Live",
                balance=50000.0,
                equity=48500.0,
                margin=1200.0,
                profit=-1500.0,
            ),
        )
        await app.poll_telemetry()
        await pilot.pause()

        assert "▼ -$1,500.00" in str(pnl_val.content)
        assert "profit-negative" in pnl_card.classes


@pytest.mark.asyncio
async def test_backend_offline_at_launch_and_reconnect_loop_scenario_5():
    """Verify Scenario 5: Backend Offline at Launch & Resilient Reconnect Loop.

    Given the FastAPI backend is unreachable or down at startup
    When the user launches the TUI
    Then the HeaderBar displays an amber "[○ GATEWAY UNREACHABLE]" warning badge with a reconnect countdown timer
    And background polling continues every 3 seconds without raising unhandled connection exceptions
    And when the FastAPI server comes online, the TUI automatically synchronizes telemetry and transitions to normal operation.
    """
    mock_client = AsyncMock(spec=DarwinApiClient)
    # 1. Startup: Gateway unreachable
    mock_client.get_account_status.return_value = ConnectionStatus(
        status=ConnectionState.DISCONNECTED,
        server="Unknown",
        mock_mode=False,
        last_error="Connection refused: http://127.0.0.1:8000",
    )
    mock_client.get_positions.return_value = []
    mock_client.get_strategy_status.return_value = None

    app = DarwinTraderApp(api_client=mock_client, poll_interval=3.0)
    async with app.run_test() as pilot:
        await pilot.pause()

        badge = app.query_one("#status-badge")
        assert "[○ GATEWAY UNREACHABLE" in str(badge.content)
        assert "status-offline" in badge.classes

        # Verify timer countdown tick
        await app._tick_timer()
        await pilot.pause()
        assert "[○ GATEWAY UNREACHABLE (2s)]" in str(badge.content)

        # 2. FastAPI backend comes online
        mock_client.get_account_status.return_value = ConnectionStatus(
            status=ConnectionState.CONNECTED,
            server="Darwinex-Live",
            mock_mode=False,
            latency_ms=10.0,
            account_info=AccountInfo(
                login=334455,
                server="Darwinex-Live",
                balance=25000.0,
                equity=25000.0,
                margin=0.0,
                profit=0.0,
            ),
        )
        mock_client.get_strategy_status.return_value = {
            "status": "RUNNING",
            "strategy_name": "Darwin_Trend_ATR_V1",
            "symbol": "EURUSD",
        }

        # Poll runs when countdown expires or on poll_telemetry
        await app.poll_telemetry()
        await pilot.pause()

        # Telemetry automatically transitions to normal operation
        assert "[● CONNECTED (LIVE)]" in str(badge.content)
        assert "status-connected-live" in badge.classes
        info = app.query_one("#telemetry-info")
        assert "Server: Darwinex-Live" in str(info.content)
        assert "Login: 334455" in str(info.content)


@pytest.mark.asyncio
async def test_simulation_mode_telemetry_and_badge_scenario_9():
    """Verify Scenario 9: Simulation Mode Telemetry & Badge.

    Given the user connects with Mock Mode enabled or server is set to a demo sandbox
    When connection succeeds
    Then the HeaderBar displays a cyan/amber "[● SIMULATION] badge"
    And the SummaryCards and PositionsTable display simulated execution telemetry without sending live broker orders.
    """
    mock_client = AsyncMock(spec=DarwinApiClient)
    mock_client.get_account_status.return_value = ConnectionStatus(
        status=ConnectionState.CONNECTED,
        server="Darwinex-Live",
        mock_mode=True,
        latency_ms=5.0,
        account_info=AccountInfo(
            login=777888,
            server="Darwinex-Live",
            balance=100000.0,
            equity=100250.0,
            margin=500.0,
            profit=250.0,
        ),
    )
    sim_position = Position(
        ticket=9001,
        symbol="EURUSD",
        order_type=OrderType.BUY,
        volume=0.10,
        open_price=1.0850,
        current_price=1.0875,
        sl=1.0800,
        tp=1.0950,
        pnl=25.0,
        swap=0.0,
    )
    mock_client.get_positions.return_value = [sim_position]
    mock_client.get_strategy_status.return_value = {
        "status": "RUNNING",
        "strategy_name": "Darwin_Trend_ATR_V1",
        "symbol": "EURUSD",
    }

    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test() as pilot:
        await pilot.pause()

        header = app.query_one(HeaderBar)
        badge = header.query_one("#status-badge")
        assert "[● SIMULATION]" in str(badge.content)
        assert "status-simulation" in badge.classes

        summary = app.query_one(SummaryCards)
        bal_val = summary.query_one("#card-balance-value")
        assert str(bal_val.content) == "$100,000.00"

        table = app.query_one(PositionsTable)
        data_table = table.query_one("#positions-data-table")
        assert data_table.row_count == 1
        assert data_table.get_cell("9001", "symbol") == "EURUSD"
        assert "▲ +$25.00" in str(data_table.get_cell("9001", "pnl"))


@pytest.mark.asyncio
async def test_connect_modal_autodetection_and_account_pinning_terminal_exists(monkeypatch):
    """
    Scenario 1: Automatic Detection of Darwinex MT5 Installation when terminal binary exists.
    Given the Darwinex MetaTrader 5 terminal is installed at "C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe"
    When the user opens the TUI MT5 Account Connection modal via F2 or C
    Then the Terminal Path input field is pre-populated with "C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe"
    And the Server dropdown defaults to "Darwinex-Live"
    And the Login ID field defaults to "4000073238"
    And the Mock Mode checkbox is unchecked by default when the terminal binary exists.
    """
    import os
    monkeypatch.setattr(os.path, "exists", lambda path: True if "terminal64.exe" in path else False)

    mock_client = AsyncMock(spec=DarwinApiClient)
    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.press("f2")
        await pilot.pause()

        assert isinstance(app.screen, ConnectModal)
        modal = app.screen

        # Verify auto-detection and account pinning defaults
        input_login = modal.query_one("#input-login", Input)
        assert input_login.value == "4000073238"

        select_server = modal.query_one("#select-server", Select)
        assert select_server.value == "Darwinex-Live"

        input_path = modal.query_one("#input-path", Input)
        assert input_path.value == r"C:\Program Files\Darwinex MetaTrader 5\terminal64.exe"

        checkbox_mock = modal.query_one("#checkbox-mock", Checkbox)
        assert checkbox_mock.value is False


@pytest.mark.asyncio
async def test_connect_modal_autodetection_terminal_missing(monkeypatch):
    """
    Verify ConnectModal defaults when terminal binary does not exist.
    Given terminal64.exe does not exist at the default path
    When ConnectModal is composed
    Then the Mock Mode checkbox is checked by default (True)
    And default login is still 4000073238 and server is Darwinex-Live.
    """
    import os
    monkeypatch.setattr(os.path, "exists", lambda path: False)

    modal = ConnectModal()
    app = DarwinTraderApp()
    async with app.run_test(size=(80, 40)) as pilot:
        app.push_screen(modal)
        await pilot.pause()

        input_login = modal.query_one("#input-login", Input)
        assert input_login.value == "4000073238"

        select_server = modal.query_one("#select-server", Select)
        assert select_server.value == "Darwinex-Live"

        input_path = modal.query_one("#input-path", Input)
        assert input_path.value == r"C:\Program Files\Darwinex MetaTrader 5\terminal64.exe"

        checkbox_mock = modal.query_one("#checkbox-mock", Checkbox)
        assert checkbox_mock.value is True


@pytest.mark.asyncio
async def test_connect_modal_submit_submits_pinned_account_request(monkeypatch):
    """
    Verify submitting ConnectModal with pinned defaults submits the expected AccountConnectRequest.
    """
    import os
    monkeypatch.setattr(os.path, "exists", lambda path: True)

    mock_client = AsyncMock(spec=DarwinApiClient)
    mock_client.connect_account.return_value = AccountConnectResponse(
        status=ConnectionState.CONNECTED,
        message="Connected to MetaTrader 5 live terminal",
        login=4000073238,
        server="Darwinex-Live",
        trade_mode="REAL",
        balance=100000.0,
        currency="USD",
        account_info=AccountInfo(
            login=4000073238,
            server="Darwinex-Live",
            trade_mode="REAL",
            balance=100000.0,
            equity=100000.0,
        ),
    )

    modal = ConnectModal(api_client=mock_client)
    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test(size=(80, 40)) as pilot:
        app.push_screen(modal)
        await pilot.pause()

        # Submit with pre-populated values
        modal.query_one("#btn-submit", Button).press()
        await pilot.pause()

        # Modal should be dismissed
        assert app.screen is not modal

        # Assert api_client.connect_account was called with pinned defaults
        mock_client.connect_account.assert_awaited_once()
        req = mock_client.connect_account.call_args[0][0]
        assert req.login == 4000073238
        assert req.server == "Darwinex-Live"
        assert req.path == r"C:\Program Files\Darwinex MetaTrader 5\terminal64.exe"
        assert req.mock_mode is False


# =============================================================================
# Issue #60: DarwinX Zero BDD Test Suite (Scenarios 2 to 6)
# =============================================================================

@pytest.mark.asyncio
async def test_live_mt5_ipc_connection_account_4000073238_scenario_2():
    """
    Scenario 2: Live MT5 IPC Connection for Account 4000073238 on Darwinex-Live
    Given the MetaTrader5 Python package is installed on Windows
    And the user submits Login "4000073238" on server "Darwinex-Live" with Mock Mode unchecked
    When the backend executes mt5.initialize() targeting the Darwinex terminal
    Then the TUI displays a green "[● CONNECTED (LIVE)]" status badge with server "Darwinex-Live" and Login "4000073238"
    And the SummaryCards display real account Balance, Equity, Margin, and Free Margin fetched from MT5
    And the StrategyPanel displays active Drawdown percentage against the strict 3.0% DarwinX Zero limit.
    """
    mock_client = AsyncMock(spec=DarwinApiClient)
    acc_info = AccountInfo(
        login=4000073238,
        server="Darwinex-Live",
        trade_mode="REAL",
        balance=1044115.25,
        equity=1042000.00,
        margin=5000.0,
        free_margin=1037000.0,
    )
    status_connected = ConnectionStatus(
        status=ConnectionState.CONNECTED,
        server="Darwinex-Live",
        mock_mode=False,
        latency_ms=15.2,
        account_info=acc_info,
    )
    mock_client.get_account_status.return_value = status_connected
    mock_client.get_account_info.return_value = acc_info
    mock_client.get_positions.return_value = []
    mock_client.get_strategy_status.return_value = {
        "status": "RUNNING",
        "strategy_name": "Darwin_Trend_ATR_V1",
        "symbol": "EURUSD",
        "account_balance": 1044115.25,
        "account_equity": 1042000.00,  # ~0.20% drawdown
    }

    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()

        # Check HeaderBar
        header = app.query_one(HeaderBar)
        badge = header.query_one("#status-badge")
        assert "[● CONNECTED (LIVE)]" in str(badge.content)
        assert "status-connected-live" in badge.classes

        info_text = header.query_one("#telemetry-info")
        assert "Darwinex-Live" in str(info_text.content)
        assert "4000073238" in str(info_text.content)

        # Check SummaryCards
        summary = app.query_one(SummaryCards)
        val_balance = summary.query_one("#card-balance-value")
        val_equity = summary.query_one("#card-equity-value")
        val_margin = summary.query_one("#card-margin-value")

        assert "1,044,115.25" in str(val_balance.content)
        assert "1,042,000.00" in str(val_equity.content)
        assert "5,000.00" in str(val_margin.content)

        # Check StrategyPanel drawdown against strict 3.0% DarwinX Zero limit
        strat = app.query_one(StrategyPanel)
        dd_widget = strat.query_one("#strategy-drawdown-value")
        assert "3.00%" in str(dd_widget.content)
        assert "0.20%" in str(dd_widget.content)
        assert "[● SAFE]" in str(dd_widget.content)
        assert "drawdown-safe" in dd_widget.classes


@pytest.mark.asyncio
async def test_mt5_attach_to_running_terminal_without_password_scenario_3(monkeypatch):
    """
    Scenario 3: Attach to Already-Running MT5 Terminal Instance Without Password
    Given the Darwinex MetaTrader 5 application is already running on the laptop with an active session for 4000073238
    When the user clicks "Connect" in the TUI without entering a password
    Then the backend calls mt5.initialize() without spawning a new process
    And successfully attaches to the existing terminal session via local Win32 IPC
    And live account telemetry populates immediately without prompting for password re-entry.
    """
    import os
    monkeypatch.setattr(os.path, "exists", lambda path: True)

    mock_client = AsyncMock(spec=DarwinApiClient)
    acc_info = AccountInfo(
        login=4000073238,
        server="Darwinex-Live",
        trade_mode="REAL",
        balance=1044115.25,
        equity=1044115.25,
    )
    mock_client.connect_account.return_value = AccountConnectResponse(
        status=ConnectionState.CONNECTED,
        message="Attached to existing terminal session via Win32 IPC",
        login=4000073238,
        server="Darwinex-Live",
        trade_mode="REAL",
        balance=1044115.25,
        currency="USD",
        account_info=acc_info,
    )
    mock_client.get_account_status.return_value = ConnectionStatus(
        status=ConnectionState.CONNECTED,
        server="Darwinex-Live",
        mock_mode=False,
        latency_ms=10.0,
        account_info=acc_info,
    )
    mock_client.get_account_info.return_value = acc_info
    mock_client.get_positions.return_value = []
    mock_client.get_strategy_status.return_value = {
        "status": "RUNNING",
        "strategy_name": "Darwin_Trend_ATR_V1",
        "symbol": "EURUSD",
        "daily_drawdown_pct": 0.0,
    }

    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test(size=(80, 40)) as pilot:
        # Open connect modal via hotkey
        await pilot.press("f2")
        await pilot.pause()

        assert isinstance(app.screen, ConnectModal)
        modal = app.screen

        # Ensure password field is left completely empty
        input_password = modal.query_one("#input-password", Input)
        assert input_password.value == ""

        # Press connect button
        modal.query_one("#btn-submit", Button).press()
        await pilot.pause()

        # ConnectModal should dismiss cleanly on success
        assert app.screen is not modal

        # Verify connect_account was called with empty password and correct path
        mock_client.connect_account.assert_awaited_once()
        req = mock_client.connect_account.call_args[0][0]
        assert req.login == 4000073238
        assert req.password == ""
        assert req.server == "Darwinex-Live"
        assert req.mock_mode is False

        # Live telemetry populates without password prompt
        header = app.query_one(HeaderBar)
        badge = header.query_one("#status-badge")
        assert "[● CONNECTED (LIVE)]" in str(badge.content)


@pytest.mark.asyncio
async def test_terminal_error_diagnostic_mapping_scenario_4():
    """
    Scenario 4: Terminal Error Diagnostic Mapping
    Given the user enters an invalid login ID or server in the Connect Modal
    When the user clicks Connect
    Then the backend maps the numeric MT5 error code from mt5.last_error() via MT5_ERROR_MESSAGES
    And the TUI Connect Modal displays a human-readable diagnostic banner
    And the modal remains open with inputs preserved for correction.
    """
    mock_client = AsyncMock(spec=DarwinApiClient)
    diagnostic_err = "MT5 Error 1: Invalid account credentials or authorization failed"
    mock_client.connect_account.return_value = AccountConnectResponse(
        status=ConnectionState.ERROR,
        message=diagnostic_err,
        login=9999999,
        server="Darwinex-Live",
        trade_mode="REAL",
        balance=0.0,
        currency="USD",
        error=diagnostic_err,
    )

    modal = ConnectModal(api_client=mock_client)
    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test(size=(80, 40)) as pilot:
        app.push_screen(modal)
        await pilot.pause()

        input_login = modal.query_one("#input-login", Input)
        input_login.value = "9999999"

        # Click submit
        modal.query_one("#btn-submit", Button).press()
        await pilot.pause()

        # Modal must remain open with error banner visible
        assert app.screen is modal
        banner = modal.query_one("#error-banner", Static)
        assert banner.has_class("visible")
        assert "Invalid account credentials or authorization failed" in str(banner.content)
        assert "MT5 Error 1" in str(banner.content)

        # Input values are preserved for user correction
        assert input_login.value == "9999999"


@pytest.mark.asyncio
async def test_darwinex_zero_risk_limits_and_buffer_warning_scenario_5():
    """
    Scenario 5: Darwinex Zero Risk Limits Visibility & Buffer Warning
    Given the TUI is connected to live DarwinX Zero account 4000073238
    When the account experiences floating drawdown
    Then the StrategyPanel displays the daily drawdown percentage alongside the strict 3.0% Darwinex Zero threshold
    And if drawdown reaches or exceeds the configured drawdown_warning_pct (2.5%), the drawdown indicator displays an amber "[⚠ WARNING]" badge
    And if drawdown remains below 2.0%, it displays a green "[● SAFE]" badge.
    """
    mock_client = AsyncMock(spec=DarwinApiClient)
    mock_client.get_account_status.return_value = ConnectionStatus(
        status=ConnectionState.CONNECTED,
        server="Darwinex-Live",
        account_info=AccountInfo(login=4000073238, server="Darwinex-Live", balance=100000.0, equity=100000.0),
    )
    mock_client.get_positions.return_value = []
    mock_client.get_strategy_status.return_value = {"status": "RUNNING"}

    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test():
        strat = app.query_one(StrategyPanel)
        dd_widget = strat.query_one("#strategy-drawdown-value")

        # Step 1: Drawdown < 2.0% (e.g. 1.25%) -> Green [● SAFE] badge
        strat.update_telemetry(
            strategy_data={
                "status": "RUNNING",
                "strategy_name": "Darwin_Trend_ATR_V1",
                "symbol": "EURUSD",
                "account_balance": 100000.0,
                "account_equity": 98750.0,  # 1.25% drawdown
            }
        )
        assert "1.25%" in str(dd_widget.content)
        assert "3.00%" in str(dd_widget.content)
        assert "[● SAFE]" in str(dd_widget.content)
        assert "drawdown-safe" in dd_widget.classes
        assert "drawdown-normal" in dd_widget.classes

        # Step 2: Drawdown reaches or exceeds warning buffer 2.5% (e.g. 2.60%) -> Amber [⚠ WARNING] badge
        strat.update_telemetry(
            strategy_data={
                "status": "RUNNING",
                "strategy_name": "Darwin_Trend_ATR_V1",
                "symbol": "EURUSD",
                "account_balance": 100000.0,
                "account_equity": 97400.0,  # 2.60% drawdown >= 2.50%
            }
        )
        assert "2.60%" in str(dd_widget.content)
        assert "3.00%" in str(dd_widget.content)
        assert "[⚠ WARNING]" in str(dd_widget.content)
        assert "drawdown-warning" in dd_widget.classes
        assert "drawdown-safe" not in dd_widget.classes

        # Step 3: Drawdown hard breach (>= 3.0%, e.g. 3.20%) -> Breach badge
        strat.update_telemetry(
            strategy_data={
                "status": "RUNNING",
                "strategy_name": "Darwin_Trend_ATR_V1",
                "symbol": "EURUSD",
                "account_balance": 100000.0,
                "account_equity": 96800.0,  # 3.20% drawdown >= 3.00%
            }
        )
        assert "3.20%" in str(dd_widget.content)
        assert "3.00%" in str(dd_widget.content)
        assert "[⛔ BREACH]" in str(dd_widget.content)
        assert "drawdown-breach" in dd_widget.classes


@pytest.mark.asyncio
async def test_graceful_mock_fallback_non_windows_or_missing_dep_scenario_6():
    """
    Scenario 6: Graceful Mock Fallback on Non-Windows or Missing Dependency
    Given the Darwin Trader backend or TUI is launched in an environment where MetaTrader5 is not installed or OS is not Windows
    When the application starts
    Then the connector automatically engages Simulation / Mock mode without raising unhandled import exceptions
    And the TUI displays a cyan/amber "[● SIMULATION]" badge.
    """
    mock_client = AsyncMock(spec=DarwinApiClient)
    # Backend reports mock/simulation mode due to missing dependency or non-Windows OS
    mock_client.get_account_status.return_value = ConnectionStatus(
        status=ConnectionState.CONNECTED,
        server="Darwinex-Simulated",
        mock_mode=True,
        latency_ms=0.5,
        account_info=AccountInfo(login=4000073238, server="Darwinex-Simulated", balance=100000.0, equity=100000.0),
    )
    mock_client.get_positions.return_value = []
    mock_client.get_strategy_status.return_value = {"status": "IDLE"}

    app = DarwinTraderApp(api_client=mock_client)
    async with app.run_test():
        header = app.query_one(HeaderBar)
        badge = header.query_one("#status-badge")

        # Badge reflects SIMULATION mode without unhandled errors
        assert "[● SIMULATION]" in str(badge.content)
        assert "status-simulation" in badge.classes



