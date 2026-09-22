"""
Data models for signals, candles, positions, and strategy engine state.
"""
from enum import Enum
from typing import Optional, List, Dict
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
    swap: float = 0.0
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


class ConnectionState(str, Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"


class AccountConnectRequest(BaseModel):
    login: int = 0
    password: str = ""
    server: str = "Darwinex-Demo"
    path: Optional[str] = None
    mock_mode: bool = True


class AccountConnectResponse(BaseModel):
    status: ConnectionState = ConnectionState.CONNECTED
    message: str = ""
    login: int = 0
    server: str = "Darwinex-Demo"
    trade_mode: str = "DEMO"
    balance: float = 100000.0
    currency: str = "USD"
    account_info: Optional[AccountInfo] = None
    error: Optional[str] = None


class ConnectionStatus(BaseModel):
    status: ConnectionState = ConnectionState.DISCONNECTED
    server: str = "Darwinex-Demo"
    mock_mode: bool = True
    latency_ms: float = 0.0
    connected_at: Optional[datetime] = None
    last_error: Optional[str] = None
    account_info: Optional[AccountInfo] = None


class AssetCategory(str, Enum):
    ALL = "all"
    STOCKS = "stocks"
    ETFS = "etfs"
    FOREX = "forex"


class AssetInfo(BaseModel):
    symbol: str
    description: str = ""
    category: str = ""
    currency: str = "USD"
    visible: bool = True
    lot_min: float = 0.01
    lot_max: float = 100.0
    lot_step: float = 0.01
    digits: int = 2
    point: float = 0.01
    filling_mode: int = 1
    trade_mode: int = 4
    bid: Optional[float] = None
    ask: Optional[float] = None


class Timeframe(str, Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"
    MN1 = "MN1"


TIMEFRAME_TO_MT5: Dict[str, int] = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 16385,
    "H4": 16388,
    "D1": 16408,
    "W1": 32769,
    "MN1": 49153,
}


class HistoricalBar(BaseModel):
    symbol: str
    timeframe: str = "D1"
    time: int  # UNIX epoch timestamp (seconds)
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0
    spread: int = 0


class HistoricalRatesRequest(BaseModel):
    symbol: str
    timeframe: str = "D1"
    limit: int = 500
    offset: int = 0


class HistoricalRatesResponse(BaseModel):
    symbol: str
    timeframe: str = "D1"
    bars: List[HistoricalBar] = []
    total_bars: int = 0
    limit: int = 500
    offset: int = 0
    page: int = 1
    total_pages: int = 1


class HistoricalSyncStatus(BaseModel):
    job_id: Optional[str] = None
    status: str = "IDLE"  # "IDLE", "IN_PROGRESS", "COMPLETED", "FAILED"
    completed_assets: int = 0
    failed_assets: int = 0
    total_assets: int = 0
    current_symbol: Optional[str] = None
    message: str = ""


class HistoricalSyncResponse(BaseModel):
    job_id: str
    status: str = "IN_PROGRESS"
    message: str = ""


