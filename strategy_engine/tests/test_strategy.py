"""
Unit tests for Python strategy engine components.
"""
import pytest
import pandas as pd
from datetime import datetime

from pydantic import ValidationError

from strategy_engine.config import StrategyConfig
from strategy_engine.models import (
    SignalType,
    TradeSignal,
    AccountInfo,
    Position,
    OrderType,
    ConnectionState,
    AccountConnectRequest,
    AccountConnectResponse,
    ConnectionStatus,
)
from strategy_engine.sample_strategy import DarwinTrendStrategy
from strategy_engine.risk_manager import RiskManager
from strategy_engine.backtester import Backtester, generate_mock_ohlcv
from strategy_engine.mt5_connector import MT5Connector


def test_strategy_signal_generation():
    config = StrategyConfig(mock_mode=True)
    strategy = DarwinTrendStrategy(config)
    
    df = generate_mock_ohlcv(bars=100)
    signal = strategy.generate_signal(df)
    
    assert isinstance(signal, TradeSignal)
    assert signal.symbol == "EURUSD"
    assert signal.signal_type in [SignalType.ENTER_LONG, SignalType.ENTER_SHORT, SignalType.HOLD]


def test_risk_manager_drawdown_limit():
    config = StrategyConfig(max_daily_drawdown_pct=3.0)
    rm = RiskManager(config)
    
    signal = TradeSignal(symbol="EURUSD", signal_type=SignalType.ENTER_LONG, price=1.0850)
    
    # Normal account -> Allowed
    acc_normal = AccountInfo(balance=100000.0, equity=99000.0, free_margin=90000.0)
    allowed, reason = rm.validate_signal(signal, acc_normal, [])
    assert allowed is True
    
    # Account in 4% drawdown -> Blocked by risk manager
    acc_drawdown = AccountInfo(balance=100000.0, equity=95500.0, free_margin=90000.0)
    allowed, reason = rm.validate_signal(signal, acc_drawdown, [])
    assert allowed is False
    assert "drawdown breach" in reason.lower()


def test_backtester_run():
    config = StrategyConfig()
    strategy = DarwinTrendStrategy(config)
    backtester = Backtester(strategy, config, initial_balance=100000.0)
    
    df = generate_mock_ohlcv(bars=300)
    res = backtester.run(df)
    
    assert "final_balance" in res
    assert "total_trades" in res
    assert "win_rate_pct" in res
    assert "max_drawdown_pct" in res
    assert res["initial_balance"] == 100000.0


def test_mt5_connector_mock():
    config = StrategyConfig(mock_mode=True)
    connector = MT5Connector(config)
    
    ok, msg = connector.initialize()
    assert ok is True
    
    acc = connector.get_account_info()
    assert acc.balance == 100000.0
    
    # Execute mock order
    sig = TradeSignal(symbol="EURUSD", signal_type=SignalType.ENTER_LONG, price=1.0850, lot_size=0.1)
    executed, exec_msg = connector.execute_order(sig)
    assert executed is True
    
    positions = connector.get_open_positions()
    assert len(positions) == 1
    assert positions[0].volume == 0.1
    
    # Trigger Kill Switch
    count, kill_msg = connector.close_all_positions()
    assert count == 1
    assert len(connector.get_open_positions()) == 0


def test_mt5_connector_status_and_disconnect():
    config = StrategyConfig(mock_mode=True, mt5_server="Darwinex-Demo")
    connector = MT5Connector(config)
    assert connector.is_connected is False
    status = connector.get_connection_status()
    assert status.status == "DISCONNECTED"

    ok, msg = connector.initialize()
    assert ok is True
    assert connector.is_connected is True
    assert connector.connected_at is not None
    assert connector.latency_ms >= 0.0

    status = connector.get_connection_status()
    assert status.status == "CONNECTED"
    assert status.server == "Darwinex-Demo"
    assert status.mock_mode is True
    assert status.last_error is None
    assert status.account_info is not None

    ok_disc, msg_disc = connector.disconnect()
    assert ok_disc is True
    assert connector.is_connected is False
    status = connector.get_connection_status()
    assert status.status == "DISCONNECTED"


def test_mt5_connector_live_init_failure(monkeypatch):
    import strategy_engine.mt5_connector as mc
    monkeypatch.setattr(mc, "HAS_MT5", True)

    class FakeMT5:
        @staticmethod
        def initialize(**kwargs):
            return False

        @staticmethod
        def last_error():
            return (-10004, "Terminal not reachable")

        @staticmethod
        def shutdown():
            pass

    monkeypatch.setattr(mc, "mt5", FakeMT5)

    config = StrategyConfig(mock_mode=False, mt5_login=12345, mt5_password="bad", mt5_server="Darwinex-Live")
    connector = MT5Connector(config)
    ok, msg = connector.initialize()
    assert ok is False
    assert "MT5 initialize failed" in msg
    assert connector.last_error is not None

    status = connector.get_connection_status()
    assert status.status == "ERROR"
    assert status.last_error == msg
    assert status.account_info is None

    # Verify disconnect clears last_error and transitions status back to DISCONNECTED (Issue #10)
    disc_ok, disc_msg = connector.disconnect()
    assert disc_ok is True
    assert connector.last_error is None
    status_after_disc = connector.get_connection_status()
    assert status_after_disc.status == "DISCONNECTED"
    assert status_after_disc.last_error is None
    assert status_after_disc.account_info is None


def test_mt5_connector_disconnect_clears_prior_error():
    """
    Given an MT5 connector with a prior error (e.g. failed connect),
    When disconnect() is explicitly invoked,
    Then last_error is cleared and get_connection_status() reports DISCONNECTED instead of ERROR.
    """
    config = StrategyConfig(mock_mode=True)
    connector = MT5Connector(config)
    connector.last_error = "Prior connection failed"
    status_before = connector.get_connection_status()
    assert status_before.status == "ERROR"
    assert status_before.last_error == "Prior connection failed"

    ok, msg = connector.disconnect()
    assert ok is True
    assert connector.last_error is None
    assert connector.is_connected is False
    status_after = connector.get_connection_status()
    assert status_after.status == "DISCONNECTED"
    assert status_after.last_error is None


def test_connection_state_validation():
    for state in [ConnectionState.CONNECTED, ConnectionState.DISCONNECTED, ConnectionState.ERROR]:
        resp = AccountConnectResponse(status=state)
        assert resp.status == state
        assert resp.model_dump()["status"] == state.value

        resp_str = AccountConnectResponse(status=state.value)
        assert resp_str.status == state
        assert resp_str.model_dump()["status"] == state.value

        conn = ConnectionStatus(status=state)
        assert conn.status == state
        assert conn.model_dump()["status"] == state.value

        conn_str = ConnectionStatus(status=state.value)
        assert conn_str.status == state
        assert conn_str.model_dump()["status"] == state.value

    with pytest.raises(ValidationError):
        AccountConnectResponse(status="BOGUS")

    with pytest.raises(ValidationError):
        ConnectionStatus(status="BOGUS")


def test_account_connect_request_path_default():
    req_default = AccountConnectRequest()
    assert req_default.path is None

    req_none = AccountConnectRequest(path=None)
    assert req_none.path is None

    req_custom = AccountConnectRequest(path="C:\\Custom\\MT5\\terminal64.exe")
    assert req_custom.path == "C:\\Custom\\MT5\\terminal64.exe"


def test_mt5_connector_concurrency():
    """
    Verifies that concurrent calls to MT5Connector (initialize, execute_order,
    get_connection_status, close_all_positions) are thread-safe and do not corrupt state.
    """
    import concurrent.futures

    config = StrategyConfig(mock_mode=True, mt5_server="Darwinex-Demo")
    connector = MT5Connector(config)
    connector.initialize()

    def place_orders(worker_id: int):
        for j in range(5):
            sig = TradeSignal(
                symbol="EURUSD",
                signal_type=SignalType.ENTER_LONG,
                price=1.0800 + (worker_id * 0.001) + (j * 0.0001),
                lot_size=0.01,
                reason=f"worker-{worker_id}"
            )
            ok, msg = connector.execute_order(sig)
            assert ok is True
            status = connector.get_connection_status()
            assert status.status == ConnectionState.CONNECTED

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(place_orders, i) for i in range(5)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    positions = connector.get_open_positions()
    assert len(positions) == 25

    closed, msg = connector.close_all_positions()
    assert closed == 25
    assert len(connector.get_open_positions()) == 0


def test_strategy_config_reset_from_instance():
    """
    Given a StrategyConfig instance with mutated fields,
    when .reset_from(StrategyConfig(mock_mode=True)) is called,
    then all fields match the fresh instance's values without touching private internals.
    """
    config = StrategyConfig(
        symbol="GBPUSD",
        timeframe="H1",
        risk_per_trade_pct=2.5,
        max_daily_drawdown_pct=5.0,
        mt5_login=987654,
        mt5_server="Darwinex-Live",
        mock_mode=False,
        fast_ema_period=9,
        slow_ema_period=21,
    )

    fresh = StrategyConfig(mock_mode=True)
    res = config.reset_from(fresh)

    assert res is config
    assert config.symbol == "EURUSD"
    assert config.timeframe == "M15"
    assert config.risk_per_trade_pct == 1.0
    assert config.max_daily_drawdown_pct == 3.0
    assert config.mt5_login == 0
    assert config.mt5_server == "Darwinex-Demo"
    assert config.mock_mode is True
    assert config.fast_ema_period == 12
    assert config.slow_ema_period == 26
    assert config.model_dump() == fresh.model_dump()


def test_strategy_config_reset_from_defaults_and_overrides():
    """
    Verifies reset_from() with kwargs overrides and empty arguments resets to default values.
    """
    config = StrategyConfig(symbol="USDJPY", mock_mode=False, mt5_login=123)
    config.reset_from(symbol="BTCUSD", mock_mode=True)

    assert config.symbol == "BTCUSD"
    assert config.mock_mode is True
    assert config.mt5_login == 0

    # Calling reset_from() without arguments restores defaults
    config.reset_from()
    assert config.symbol == "EURUSD"
    assert config.mock_mode is True


def test_strategy_config_reset_from_idempotency_and_side_effects():
    """
    Given reset_from(), when called repeatedly in sequence,
    then it is idempotent and side-effect free beyond the target instance.
    """
    source = StrategyConfig(symbol="AUDUSD", mock_mode=True, fast_ema_period=8)
    target = StrategyConfig()

    # First call
    target.reset_from(source)
    assert target.symbol == "AUDUSD"
    assert target.fast_ema_period == 8

    # Second call (idempotent)
    target.reset_from(source)
    assert target.symbol == "AUDUSD"
    assert target.fast_ema_period == 8

    # Verify mutating source afterwards does not affect target
    source.symbol = "NZDUSD"
    assert target.symbol == "AUDUSD"


def test_strategy_config_drawdown_warning_pct():
    """
    Given StrategyConfig default instantiation,
    Then drawdown_warning_pct is present with default value 2.5.
    """
    config = StrategyConfig()
    assert hasattr(config, "drawdown_warning_pct")
    assert config.drawdown_warning_pct == 2.5

    # Can be customized
    custom = StrategyConfig(drawdown_warning_pct=2.0)
    assert custom.drawdown_warning_pct == 2.0


def test_mt5_error_messages_mapping():
    """
    Verify MT5_ERROR_MESSAGES dictionary maps expected codes to human-readable strings.
    """
    from strategy_engine.mt5_connector import MT5_ERROR_MESSAGES, format_mt5_error

    assert 1 in MT5_ERROR_MESSAGES
    assert MT5_ERROR_MESSAGES[1] == "Invalid account credentials or authorization failed"
    assert -10004 in MT5_ERROR_MESSAGES
    assert MT5_ERROR_MESSAGES[-10004] == "Terminal not reachable or IPC connection failed"
    assert -10003 in MT5_ERROR_MESSAGES
    assert -10005 in MT5_ERROR_MESSAGES

    # Test format_mt5_error
    formatted_1 = format_mt5_error((1, "Authorization failed"))
    assert "MT5 Error 1" in formatted_1
    assert "Invalid account credentials" in formatted_1

    formatted_10004 = format_mt5_error(-10004)
    assert formatted_10004 == "MT5 Error -10004: Terminal not reachable or IPC connection failed"

    # Unknown error code fallback
    formatted_unknown = format_mt5_error((-99999, "Custom internal message"))
    assert "MT5 Error -99999: Custom internal message" in formatted_unknown


def test_mt5_connector_attach_to_running_instance(monkeypatch):
    """
    Given MT5 terminal is already running,
    When MT5Connector.initialize() is called without password,
    Then it attaches directly via mt5.initialize(path=...) without spawning/calling login.
    """
    import strategy_engine.mt5_connector as mc
    monkeypatch.setattr(mc, "HAS_MT5", True)

    calls = {"initialize": [], "login": []}

    class FakeRunningMT5:
        @staticmethod
        def initialize(**kwargs):
            calls["initialize"].append(kwargs)
            return True

        @staticmethod
        def login(**kwargs):
            calls["login"].append(kwargs)
            return True

        @staticmethod
        def last_error():
            return (0, "")

        @staticmethod
        def account_info():
            from collections import namedtuple
            Acc = namedtuple("Acc", ["login", "trade_mode", "server", "balance", "equity", "margin", "margin_free", "profit", "currency"])
            return Acc(4000073238, 2, "Darwinex-Live", 1044115.25, 1044115.25, 0.0, 1044115.25, 0.0, "USD")

    monkeypatch.setattr(mc, "mt5", FakeRunningMT5)

    config = StrategyConfig(
        mock_mode=False,
        mt5_login=4000073238,
        mt5_password="",  # No password supplied: attach to running instance
        mt5_server="Darwinex-Live",
        mt5_path="C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe"
    )
    connector = MT5Connector(config)
    ok, msg = connector.initialize()

    assert ok is True
    assert "Connected to MetaTrader 5 live terminal" in msg
    assert connector.is_connected is True
    assert len(calls["initialize"]) == 1
    assert calls["initialize"][0]["path"] == "C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe"
    # Login should NOT be invoked when no password is provided
    assert len(calls["login"]) == 0

    # Account info reflects attached session
    info = connector.get_account_info()
    assert info.login == 4000073238
    assert info.server == "Darwinex-Live"
    assert info.trade_mode == "REAL"


def test_get_open_positions_all_symbols_and_filtering(monkeypatch):
    from collections import namedtuple
    import strategy_engine.mt5_connector as mc

    FakePos = namedtuple("FakePos", [
        "ticket", "symbol", "type", "magic", "volume",
        "price_open", "price_current", "sl", "tp", "profit", "swap", "time"
    ])

    fake_positions = (
        FakePos(101, "AMZN", 0, 0, 40.0, 246.72, 253.67, 195.0, 0.0, 278.0, 0.0, 1767994216),
        FakePos(102, "NVDA", 0, 0, 500.0, 186.97, 221.76, 0.0, 0.0, 17395.0, 0.0, 1768253775),
        FakePos(103, "EURUSD", 1, 20260811, 1.0, 1.0850, 1.0820, 1.090, 0.0, 300.0, -2.5, 1768254624),
    )

    class FakeMT5:
        @staticmethod
        def positions_get(symbol=None):
            if symbol is not None:
                return tuple(p for p in fake_positions if p.symbol == symbol)
            return fake_positions

    monkeypatch.setattr(mc, "HAS_MT5", True)
    monkeypatch.setattr(mc, "mt5", FakeMT5)

    config = StrategyConfig(mock_mode=False)
    connector = MT5Connector(config)
    connector.is_connected = True

    # Retrieve all open positions across symbols and magics
    all_positions = connector.get_open_positions()
    assert len(all_positions) == 3
    symbols = [p.symbol for p in all_positions]
    assert symbols == ["AMZN", "NVDA", "EURUSD"]
    assert all_positions[0].magic == 0
    assert all_positions[0].volume == 40.0
    assert all_positions[0].pnl == 278.0

    # Retrieve filtered by symbol
    amzn_positions = connector.get_open_positions(symbol="AMZN")
    assert len(amzn_positions) == 1
    assert amzn_positions[0].symbol == "AMZN"
    assert amzn_positions[0].ticket == 101

    # Empty for nonexistent symbol
    none_positions = connector.get_open_positions(symbol="NONEXISTENT")
    assert len(none_positions) == 0



