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


