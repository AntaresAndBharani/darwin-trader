"""
Unit tests for Python strategy engine components.
"""
import pytest
import pandas as pd
from datetime import datetime

from strategy_engine.config import StrategyConfig
from strategy_engine.models import SignalType, TradeSignal, AccountInfo, Position, OrderType
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
