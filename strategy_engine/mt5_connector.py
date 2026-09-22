"""
MetaTrader 5 Connector Module with Live MT5 API and Mock MT5 execution engine for platform independence.
"""
from typing import List, Optional, Tuple, Union, Any
from datetime import datetime
import platform
import threading
import time
import hashlib
import random
import asyncio

from .config import StrategyConfig
from .models import (
    AccountInfo,
    Position,
    OrderType,
    TradeSignal,
    SignalType,
    ConnectionStatus,
    AssetInfo,
    AssetCategory,
    HistoricalBar,
    HistoricalSyncStatus,
    Timeframe,
    TIMEFRAME_TO_MT5,
)

# Try importing MetaTrader5 (available on Windows platform)
mt5 = None
HAS_MT5 = False
if platform.system() == "Windows":
    try:
        import MetaTrader5 as mt5
        HAS_MT5 = True
    except ImportError:
        HAS_MT5 = False

# Mapping of MT5 numeric error codes to human-readable diagnostic messages
MT5_ERROR_MESSAGES = {
    1: "Invalid account credentials or authorization failed",
    -1: "General failure",
    -2: "Invalid parameters passed to terminal IPC call",
    -3: "No memory",
    -4: "Not found",
    -5: "Invalid version",
    -6: "Authorization failed",
    -7: "Unsupported method or feature",
    -8: "Auto trading disabled in terminal settings",
    -10000: "Internal IPC failure",
    -10001: "Internal IPC fail send",
    -10002: "Internal IPC fail receive",
    -10003: "Terminal not found or internal fail init",
    -10004: "Terminal not reachable or IPC connection failed",
    -10005: "IPC timeout or terminal not responding",
}


def format_mt5_error(error_code_or_tuple) -> str:
    """Formats MT5 error code or tuple into a human-readable diagnostic string."""
    if isinstance(error_code_or_tuple, (tuple, list)):
        code = error_code_or_tuple[0] if error_code_or_tuple else 0
        detail = error_code_or_tuple[1] if len(error_code_or_tuple) > 1 else ""
    elif isinstance(error_code_or_tuple, int):
        code = error_code_or_tuple
        detail = ""
    else:
        return str(error_code_or_tuple)

    mapped_msg = MT5_ERROR_MESSAGES.get(code)
    if mapped_msg:
        if detail and detail != mapped_msg:
            return f"MT5 Error {code}: {mapped_msg} ({detail})"
        return f"MT5 Error {code}: {mapped_msg}"
    return f"MT5 Error {code}: {detail}" if detail else f"MT5 Error {code}"


class MT5Connector:
    def __init__(self, config: StrategyConfig):
        self.config = config
        self._lock = threading.RLock()
        self.is_connected = False
        self.connected_at: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.latency_ms: float = 0.0
        # Mock internal state for dev mode
        self._mock_positions: List[Position] = []
        self._mock_balance: float = 100000.0
        self._mock_ticket_counter: int = 100001
        self._mock_market_open: bool = True
        # In-memory asset catalog cache protected by self._lock
        self._symbols_cache: dict = {}
        self._cache_timestamp: float = 0.0
        self._cache_ttl: float = 60.0

    def initialize(self) -> Tuple[bool, str]:
        """
        Initializes connection to MT5 terminal or starts mock mode.
        Supports attaching to an already-running MT5 terminal instance without
        password re-entry, or initiating a new session with credentials.
        """
        with self._lock:
            # Clear symbol catalog cache on connection/account switch
            self._symbols_cache.clear()
            self._cache_timestamp = 0.0
            start_time = time.perf_counter()
            if self.config.mock_mode or not HAS_MT5:
                self.is_connected = True
                self.connected_at = datetime.utcnow()
                self.last_error = None
                self.latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return True, "Initialized MT5 in MOCK / Simulation Mode"

            # Live MT5 execution branch:
            # If no password is provided, attach to already-running MT5 terminal instance
            try:
                if not self.config.mt5_password:
                    init_kwargs = {}
                    if self.config.mt5_path:
                        init_kwargs["path"] = self.config.mt5_path
                    init_success = mt5.initialize(**init_kwargs)
                else:
                    init_success = mt5.initialize(
                        path=self.config.mt5_path,
                        login=self.config.mt5_login,
                        password=self.config.mt5_password,
                        server=self.config.mt5_server,
                    )
            except Exception as e:
                self.is_connected = False
                self.connected_at = None
                self.last_error = f"MT5 initialize exception: {e}"
                self.latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return False, self.last_error

            self.latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if not init_success:
                error_code = mt5.last_error()
                formatted_err = format_mt5_error(error_code)
                self.is_connected = False
                self.connected_at = None
                self.last_error = f"MT5 initialize failed: {formatted_err} ({error_code})"
                return False, self.last_error

            # If credentials and password were provided, perform explicit login
            if self.config.mt5_login and self.config.mt5_password:
                try:
                    login_success = mt5.login(
                        login=self.config.mt5_login,
                        password=self.config.mt5_password,
                        server=self.config.mt5_server,
                    )
                except Exception as e:
                    self.is_connected = False
                    self.connected_at = None
                    self.last_error = f"MT5 login exception: {e}"
                    return False, self.last_error

                if not login_success:
                    error_code = mt5.last_error()
                    formatted_err = format_mt5_error(error_code)
                    self.is_connected = False
                    self.connected_at = None
                    self.last_error = f"MT5 login failed: {formatted_err} ({error_code})"
                    return False, self.last_error

            self.is_connected = True
            self.connected_at = datetime.utcnow()
            self.last_error = None
            return True, "Connected to MetaTrader 5 live terminal"

    def disconnect(self) -> Tuple[bool, str]:
        """
        Disconnects from MT5 terminal.
        """
        with self._lock:
            self.last_error = None
            self._symbols_cache.clear()
            self._cache_timestamp = 0.0
            if HAS_MT5 and not self.config.mock_mode:
                try:
                    mt5.shutdown()
                except Exception as e:
                    self.last_error = str(e)
            self.is_connected = False
            self.connected_at = None
            return True, "Disconnected from MetaTrader 5"

    def get_connection_status(self) -> ConnectionStatus:
        """
        Returns connection state, latency, server mode, and diagnostic info.
        """
        with self._lock:
            status_str = "CONNECTED" if self.is_connected else ("ERROR" if self.last_error else "DISCONNECTED")
            acc = self.get_account_info() if self.is_connected else None
            return ConnectionStatus(
                status=status_str,
                server=self.config.mt5_server,
                mock_mode=self.config.mock_mode,
                latency_ms=self.latency_ms,
                connected_at=self.connected_at,
                last_error=self.last_error,
                account_info=acc
            )

    def get_account_info(self) -> AccountInfo:
        """
        Fetches live account statistics or returns mock account data.
        """
        with self._lock:
            if self.config.mock_mode or not HAS_MT5 or not self.is_connected:
                floating_pnl = sum(p.pnl for p in self._mock_positions)
                trade_mode = "DEMO" if "demo" in self.config.mt5_server.lower() else "REAL"
                return AccountInfo(
                    login=self.config.mt5_login or 1234567,
                    trade_mode=trade_mode,
                    server=self.config.mt5_server,
                    balance=self._mock_balance,
                    equity=self._mock_balance + floating_pnl,
                    margin=len(self._mock_positions) * 200.0,
                    free_margin=self._mock_balance + floating_pnl - (len(self._mock_positions) * 200.0),
                    profit=floating_pnl,
                    d_score=78.2
                )

            acc = mt5.account_info()
            if acc is None:
                return AccountInfo()

            return AccountInfo(
                login=acc.login,
                trade_mode="DEMO" if acc.trade_mode == 0 else "REAL",
                server=acc.server,
                balance=acc.balance,
                equity=acc.equity,
                margin=acc.margin,
                free_margin=acc.margin_free,
                profit=acc.profit,
                currency=acc.currency,
                d_score=78.2
            )

    def get_open_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """
        Returns list of active open positions for the account across all symbols,
        or filtered by symbol if specified.
        """
        with self._lock:
            if self.config.mock_mode or not HAS_MT5 or not self.is_connected:
                if symbol:
                    return [p for p in self._mock_positions if p.symbol == symbol]
                return list(self._mock_positions)

            if symbol:
                mt5_positions = mt5.positions_get(symbol=symbol)
            else:
                mt5_positions = mt5.positions_get()

            if mt5_positions is None:
                return []

            positions = []
            for pos in mt5_positions:
                order_type = OrderType.BUY if pos.type == 0 else OrderType.SELL
                open_time = datetime.utcnow()
                if hasattr(pos, "time") and pos.time:
                    try:
                        open_time = datetime.utcfromtimestamp(pos.time)
                    except Exception:
                        open_time = datetime.utcnow()

                positions.append(Position(
                    ticket=pos.ticket,
                    symbol=pos.symbol,
                    order_type=order_type,
                    volume=pos.volume,
                    open_price=pos.price_open,
                    current_price=pos.price_current,
                    sl=pos.sl,
                    tp=pos.tp,
                    pnl=pos.profit,
                    swap=getattr(pos, "swap", 0.0),
                    open_time=open_time,
                    magic=pos.magic
                ))
            return positions

    def execute_order(self, signal: TradeSignal) -> Tuple[bool, str]:
        """
        Executes market order on MT5 terminal or updates mock state.
        """
        with self._lock:
            if signal.signal_type not in (SignalType.ENTER_LONG, SignalType.ENTER_SHORT):
                return False, "Invalid signal for order execution"

            if self.config.mock_mode or not HAS_MT5 or not self.is_connected:
                ticket = self._mock_ticket_counter
                self._mock_ticket_counter += 1
                order_type = OrderType.BUY if signal.signal_type == SignalType.ENTER_LONG else OrderType.SELL
                
                pos = Position(
                    ticket=ticket,
                    symbol=signal.symbol,
                    order_type=order_type,
                    volume=signal.lot_size,
                    open_price=signal.price,
                    current_price=signal.price,
                    sl=signal.stop_loss or 0.0,
                    tp=signal.take_profit or 0.0,
                    pnl=0.0,
                    magic=self.config.magic_number
                )
                self._mock_positions.append(pos)
                return True, f"Mock Order Executed: Ticket #{ticket} {order_type.value} {signal.lot_size} lots @ {signal.price}"

            # MT5 Live Order execution
            order_type_mt5 = mt5.ORDER_TYPE_BUY if signal.signal_type == SignalType.ENTER_LONG else mt5.ORDER_TYPE_SELL
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": signal.symbol,
                "volume": signal.lot_size,
                "type": order_type_mt5,
                "price": signal.price,
                "sl": signal.stop_loss or 0.0,
                "tp": signal.take_profit or 0.0,
                "magic": self.config.magic_number,
                "comment": f"DarwinTrader {signal.reason[:20]}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                comment = result.comment if result else "Unknown MT5 error"
                return False, f"MT5 Order Execution Failed: {comment}"

            return True, f"Live MT5 Order Executed: Ticket #{result.order}"

    def close_all_positions(self) -> Tuple[int, str]:
        """
        Emergency Kill Switch: Closes all open positions.
        """
        with self._lock:
            closed_count = 0
            if self.config.mock_mode or not HAS_MT5 or not self.is_connected:
                closed_count = len(self._mock_positions)
                self._mock_positions.clear()
                return closed_count, f"Mock Kill Switch triggered: Closed {closed_count} positions"

            positions = self.get_open_positions()
            for pos in positions:
                order_type_mt5 = mt5.ORDER_TYPE_SELL if pos.order_type == OrderType.BUY else mt5.ORDER_TYPE_BUY
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": pos.symbol,
                    "volume": pos.volume,
                    "type": order_type_mt5,
                    "position": pos.ticket,
                    "price": pos.current_price,
                    "magic": self.config.magic_number,
                    "comment": "Kill Switch Close",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                res = mt5.order_send(request)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    closed_count += 1

            return closed_count, f"Live Kill Switch triggered: Closed {closed_count} open positions"

    def clear_cache(self) -> None:
        """
        Explicitly invalidates the in-memory symbol catalog cache under self._lock.
        """
        with self._lock:
            self._symbols_cache.clear()
            self._cache_timestamp = 0.0

    def _get_mock_catalog(self) -> List[AssetInfo]:
        """
        Returns deterministic mock assets fixture for headless testing:
        5 US stocks across Nasdaq/NYSE, 2 ETFs, and 1 Forex pair.
        """
        return [
            AssetInfo(symbol="AMZN", description="Amazon.com Inc", category="Stocks/US/Nasdaq"),
            AssetInfo(symbol="NVDA", description="NVIDIA Corp", category="Stocks/US/Nasdaq"),
            AssetInfo(symbol="MSFT", description="Microsoft Corp", category="Stocks/US/Nasdaq"),
            AssetInfo(symbol="PM", description="Philip Morris International", category="Stocks/US/NYSE"),
            AssetInfo(symbol="AAPL", description="Apple Inc", category="Stocks/US/Nasdaq"),
            AssetInfo(symbol="SPY", description="SPDR S&P 500 ETF Trust", category="ETFs/US/NYSE"),
            AssetInfo(symbol="QQQ", description="Invesco QQQ Trust", category="ETFs/US/Nasdaq"),
            AssetInfo(symbol="EURUSD", description="Euro vs US Dollar", category="Forex/Majors", digits=5, point=0.00001),
        ]

    def _refresh_symbols_cache_locked(self) -> None:
        """
        Populates or refreshes the symbols cache under self._lock.
        Decouples static contract specs from on-demand single tick queries.
        """
        if self.config.mock_mode or not HAS_MT5 or not self.is_connected:
            self._symbols_cache = {a.symbol: a for a in self._get_mock_catalog()}
            self._cache_timestamp = time.time()
            return

        # Query full broker catalog from MT5 master database without sequential symbol_select
        mt5_symbols = mt5.symbols_get()
        if mt5_symbols is None:
            self._symbols_cache = {}
            self._cache_timestamp = time.time()
            return

        cache = {}
        for s in mt5_symbols:
            norm_category = s.path.replace("\\", "/") if getattr(s, "path", None) else ""
            currency = (
                getattr(s, "currency_profit", None)
                or getattr(s, "currency_base", None)
                or "USD"
            )
            cache[s.name] = AssetInfo(
                symbol=s.name,
                description=getattr(s, "description", "") or "",
                category=norm_category,
                currency=currency,
                visible=bool(getattr(s, "visible", True)),
                lot_min=getattr(s, "volume_min", 0.01),
                lot_max=getattr(s, "volume_max", 100.0),
                lot_step=getattr(s, "volume_step", 0.01),
                digits=getattr(s, "digits", 2),
                point=getattr(s, "point", 0.01),
                filling_mode=getattr(s, "filling_mode", 0),
                trade_mode=getattr(s, "trade_mode", 4),
                bid=None,
                ask=None,
            )
        self._symbols_cache = cache
        self._cache_timestamp = time.time()

    def get_available_assets(
        self,
        category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[AssetInfo]:
        """
        Retrieves available tradeable assets with static contract specifications.
        Uses double-checked locking with shallow snapshots under self._lock to ensure
        thread safety and prevent dictionary mutation race conditions.
        """
        if not self.config.mock_mode and not self.is_connected:
            raise ConnectionError("MetaTrader 5 gateway disconnected")

        cat_clean: Optional[str] = None
        if category:
            cat_clean = (
                category.value.lower()
                if isinstance(category, AssetCategory)
                else str(category).strip().lower()
            )
            valid_categories = {c.value for c in AssetCategory}
            if cat_clean not in valid_categories:
                raise ValueError(
                    f"Invalid category '{category}'. Supported categories: all, stocks, etfs, forex"
                )

        now = time.time()
        if not self._symbols_cache or (now - self._cache_timestamp > self._cache_ttl):
            with self._lock:
                if not self._symbols_cache or (now - self._cache_timestamp > self._cache_ttl):
                    self._refresh_symbols_cache_locked()

        with self._lock:
            symbols = list(self._symbols_cache.values())

        if cat_clean and cat_clean != AssetCategory.ALL.value:
            prefix = f"{cat_clean}/"
            symbols = [s for s in symbols if s.category.lower().startswith(prefix)]

        if search:
            term = search.strip().lower()
            if term:
                symbols = [
                    s for s in symbols
                    if term in s.symbol.lower() or term in s.description.lower()
                ]

        return symbols

    def get_asset_info(self, symbol: str) -> Optional[AssetInfo]:
        """
        Fetches full contract specifications for a single symbol, including
        on-demand live bid/ask quotes. Returns None for bid/ask if the market is closed.
        """
        if not self.config.mock_mode and not self.is_connected:
            raise ConnectionError("MetaTrader 5 gateway disconnected")

        target = symbol.strip().upper()

        if self.config.mock_mode or not HAS_MT5:
            with self._lock:
                if not self._symbols_cache:
                    self._refresh_symbols_cache_locked()

                asset = self._symbols_cache.get(target)
                if not asset:
                    for a in self._symbols_cache.values():
                        if a.symbol.upper() == target:
                            asset = a
                            break
                if not asset:
                    return None

                mock_asset = asset.model_copy()
                if self._mock_market_open:
                    quotes = {
                        "AMZN": (185.50, 185.60),
                        "NVDA": (125.20, 125.30),
                        "MSFT": (420.10, 420.25),
                        "PM": (115.30, 115.45),
                        "AAPL": (225.40, 225.55),
                        "SPY": (550.00, 550.10),
                        "QQQ": (480.00, 480.15),
                        "EURUSD": (1.0850, 1.0852),
                    }
                    bid, ask = quotes.get(mock_asset.symbol, (100.0, 100.1))
                    mock_asset.bid = bid
                    mock_asset.ask = ask
                else:
                    mock_asset.bid = None
                    mock_asset.ask = None
                return mock_asset

        with self._lock:
            s = mt5.symbol_info(symbol)
            if s is None:
                return None

            tick = mt5.symbol_info_tick(symbol)
            bid = None
            ask = None
            if tick is not None:
                if getattr(tick, "bid", 0.0) > 0:
                    bid = tick.bid
                if getattr(tick, "ask", 0.0) > 0:
                    ask = tick.ask
            elif getattr(s, "bid", 0.0) > 0 or getattr(s, "ask", 0.0) > 0:
                bid = s.bid if getattr(s, "bid", 0.0) > 0 else None
                ask = s.ask if getattr(s, "ask", 0.0) > 0 else None

            norm_category = s.path.replace("\\", "/") if getattr(s, "path", None) else ""
            currency = (
                getattr(s, "currency_profit", None)
                or getattr(s, "currency_base", None)
                or "USD"
            )

            return AssetInfo(
                symbol=s.name,
                description=getattr(s, "description", "") or "",
                category=norm_category,
                currency=currency,
                visible=bool(getattr(s, "visible", True)),
                lot_min=getattr(s, "volume_min", 0.01),
                lot_max=getattr(s, "volume_max", 100.0),
                lot_step=getattr(s, "volume_step", 0.01),
                digits=getattr(s, "digits", 2),
                point=getattr(s, "point", 0.01),
                filling_mode=getattr(s, "filling_mode", 0),
                trade_mode=getattr(s, "trade_mode", 4),
                bid=bid,
                ask=ask,
            )

    def _generate_mock_historical_bars(
        self,
        symbol: str,
        timeframe: str = "D1",
        date_from: Optional[Union[datetime, int]] = None,
        date_to: Optional[Union[datetime, int]] = None,
    ) -> Optional[List[HistoricalBar]]:
        """
        Generates 100 synthetic historical OHLCV bars deterministically seeded
        by the symbol string MD5 hash. Simulates delisted/invalid symbols by returning None.
        """
        clean_sym = symbol.strip().upper()
        if clean_sym in ("DELISTED", "INVALID", "FAIL", "NULL") or clean_sym.endswith(".DELISTED"):
            return None

        # Deterministic seed from MD5 hash of uppercase symbol string
        seed = int(hashlib.md5(clean_sym.encode("utf-8")).hexdigest()[:8], 16)
        rng = random.Random(seed)

        # Standard base epoch timestamp (1700000000 = 2023-11-14 22:13:20 UTC)
        # Guarantees identical timestamps across symbols for multi-symbol collision tests
        base_time = 1700000000
        price = round(rng.uniform(50.0, 500.0), 2)

        bars = []
        for i in range(100):
            ts = base_time + (i * 86400)
            change = rng.uniform(-0.02, 0.02) * price
            close_p = round(max(1.0, price + change), 2)
            open_p = round(price, 2)
            high_p = round(max(open_p, close_p) + rng.uniform(0.1, 2.0), 2)
            low_p = round(max(0.5, min(open_p, close_p) - rng.uniform(0.1, 2.0)), 2)
            vol = rng.randint(1000, 100000)
            spread = rng.randint(1, 5)
            price = close_p
            bars.append(HistoricalBar(
                symbol=clean_sym,
                timeframe=timeframe,
                time=ts,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                tick_volume=vol,
                spread=spread,
            ))

        d_from_ts = int(date_from.timestamp()) if isinstance(date_from, datetime) else date_from
        d_to_ts = int(date_to.timestamp()) if isinstance(date_to, datetime) else date_to

        if d_from_ts is not None:
            bars = [b for b in bars if b.time >= d_from_ts]
        if d_to_ts is not None:
            bars = [b for b in bars if b.time <= d_to_ts]

        return bars

    def get_historical_rates(
        self,
        symbol: str,
        timeframe: str = "D1",
        date_from: Optional[Union[datetime, int]] = None,
        date_to: Optional[Union[datetime, int]] = None,
    ) -> Optional[List[HistoricalBar]]:
        """
        Fetches historical OHLCV bars for a given symbol and timeframe.
        Ensures symbol is active in Market Watch via mt5.symbol_select(symbol, True).
        Acquires self._lock strictly around MT5 Win32 IPC calls.
        Returns None for invalid/delisted symbols or upon fetch failures.
        """
        if self.config.mock_mode or not HAS_MT5 or not self.is_connected:
            return self._generate_mock_historical_bars(symbol, timeframe, date_from, date_to)

        tf_const = TIMEFRAME_TO_MT5.get(timeframe.upper(), 16408)
        d_from = (
            date_from
            if isinstance(date_from, datetime)
            else (datetime.utcfromtimestamp(date_from) if date_from else datetime(1990, 1, 1))
        )
        d_to = (
            date_to
            if isinstance(date_to, datetime)
            else (datetime.utcfromtimestamp(date_to) if date_to else datetime.utcnow())
        )

        with self._lock:
            try:
                selected = mt5.symbol_select(symbol, True)
                if not selected:
                    s_info = mt5.symbol_info(symbol)
                    if s_info is None:
                        return None
                rates_data = mt5.copy_rates_range(symbol, tf_const, d_from, d_to)
            except Exception as e:
                self.last_error = f"Error fetching rates for {symbol}: {e}"
                return None

        if rates_data is None or len(rates_data) == 0:
            return None

        bars = []
        for r in rates_data:
            bars.append(HistoricalBar(
                symbol=symbol,
                timeframe=timeframe,
                time=int(r["time"]),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                tick_volume=int(r["tick_volume"]),
                spread=int(r["spread"]),
            ))
        return bars

    def sync_historical_rates(
        self,
        symbol: str,
        timeframe: str = "D1",
        fresh: bool = False,
        db: Optional[Any] = None,
    ) -> Tuple[Optional[List[HistoricalBar]], int]:
        """
        Synchronizes historical rates for a single asset into the SQLite storage layer.
        If fresh=True, clears existing cached bars for symbol and pulls complete history.
        Otherwise queries MAX(time) and performs incremental upsert starting from MAX(time) inclusive.
        Returns (bars, inserted_count), or (None, 0) if asset failed / delisted.
        """
        if db is None:
            from .historical_db import HistoricalRatesDB
            db = HistoricalRatesDB()

        if fresh:
            db.clear_rates(symbol=symbol, timeframe=timeframe)
            date_from = datetime(1990, 1, 1)
        else:
            max_time = db.get_latest_timestamp(symbol=symbol, timeframe=timeframe)
            if max_time is not None:
                date_from = max_time
            else:
                date_from = datetime(1990, 1, 1)

        bars = self.get_historical_rates(symbol, timeframe, date_from=date_from)
        if bars is None:
            return None, 0

        if not bars:
            return [], 0

        inserted_count = db.insert_rates(bars)
        return bars, inserted_count

    async def sync_historical_batch(
        self,
        symbols: List[str],
        timeframe: str = "D1",
        fresh: bool = False,
        db: Optional[Any] = None,
        yield_ms: float = 0.025,
    ) -> HistoricalSyncStatus:
        """
        Asynchronously synchronizes historical rates for a batch of symbols.
        Releases connector lock between symbols, records failed_assets for delisted
        instruments, and yields for yield_ms (default 25ms) to prevent gateway starvation.
        """
        if db is None:
            from .historical_db import HistoricalRatesDB
            db = HistoricalRatesDB()

        status = HistoricalSyncStatus(
            status="IN_PROGRESS",
            total_assets=len(symbols),
        )

        for sym in symbols:
            status.current_symbol = sym
            bars, count = self.sync_historical_rates(
                symbol=sym, timeframe=timeframe, fresh=fresh, db=db
            )
            if bars is None:
                status.failed_assets += 1
            else:
                status.completed_assets += 1

            if yield_ms > 0:
                await asyncio.sleep(yield_ms)

        status.status = "COMPLETED"
        status.current_symbol = None
        return status


