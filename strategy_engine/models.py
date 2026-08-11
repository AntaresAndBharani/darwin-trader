"""
Data models for signals, candles, positions, and strategy engine state.
"""
from enum import Enum
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class OrderType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NONE = "NONE"


class SignalType(str, Enum):
    ENTER_LONG = "ENTER_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    EXIT_LONG = "EXIT_LONG"
    EXIT_SHORT = "EXIT_SHORT"
    HOLD = "HOLD"


class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class TradeSignal(BaseModel):
    symbol: str
    signal_type: SignalType
    price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    lot_size: float = 0.01
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    reason: str = ""


class Position(BaseModel):
    ticket: int
    symbol: str
    order_type: OrderType
    volume: float
    open_price: float
    current_price: float
    sl: float = 0.0
    tp: float = 0.0
    pnl: float = 0.0
    open_time: datetime = Field(default_factory=datetime.utcnow)
    magic: int = 0


class AccountInfo(BaseModel):
    login: int = 0
    trade_mode: str = "DEMO"
    server: str = "Darwinex-Demo"
    balance: float = 100000.0
    equity: float = 100000.0
    margin: float = 0.0
    free_margin: float = 100000.0
    margin_level: float = 0.0
    currency: str = "USD"
    profit: float = 0.0
    d_score: Optional[float] = 75.4 # Darwinex Zero D-Score metric


class StrategyStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class StrategyState(BaseModel):
    status: StrategyStatus = StrategyStatus.IDLE
    symbol: str = "EURUSD"
    last_tick_time: Optional[datetime] = None
    open_positions: List[Position] = []
    account_info: AccountInfo = Field(default_factory=AccountInfo)
    daily_drawdown_pct: float = 0.0
    total_trades_today: int = 0
    active_magic: int = 20260811
