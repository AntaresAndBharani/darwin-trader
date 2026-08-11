"""
MetaTrader 5 Connector Module with Live MT5 API and Mock MT5 execution engine for platform independence.
"""
from typing import List, Optional, Tuple
from datetime import datetime
import os
import platform

from .config import StrategyConfig
from .models import AccountInfo, Position, OrderType, TradeSignal, SignalType

# Try importing MetaTrader5 (available on Windows platform)
HAS_MT5 = False
if platform.system() == "Windows":
    try:
        import MetaTrader5 as mt5
        HAS_MT5 = True
    except ImportError:
        HAS_MT5 = False


class MT5Connector:
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.is_connected = False
        # Mock internal state for dev mode
        self._mock_positions: List[Position] = []
        self._mock_balance: float = 100000.0
        self._mock_ticket_counter: int = 100001

    def initialize(self) -> Tuple[bool, str]:
        """
        Initializes connection to MT5 terminal or starts mock mode.
        """
        if self.config.mock_mode or not HAS_MT5:
            self.is_connected = True
            return True, "Initialized MT5 in MOCK / Simulation Mode"

        # Live MT5 execution branch
        if not mt5.initialize(
            path=self.config.mt5_path,
            login=self.config.mt5_login,
            password=self.config.mt5_password,
            server=self.config.mt5_server
        ):
            error_code = mt5.last_error()
            return False, f"MT5 initialize failed: {error_code}"

        self.is_connected = True
        return True, "Connected to MetaTrader 5 live terminal"

    def get_account_info(self) -> AccountInfo:
        """
        Fetches live account statistics or returns mock account data.
        """
        if self.config.mock_mode or not HAS_MT5 or not self.is_connected:
            floating_pnl = sum(p.pnl for p in self._mock_positions)
            return AccountInfo(
                login=self.config.mt5_login or 1234567,
                trade_mode="DEMO",
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

    def get_open_positions(self) -> List[Position]:
        """
        Returns list of active open positions for strategy magic number.
        """
        if self.config.mock_mode or not HAS_MT5 or not self.is_connected:
            return self._mock_positions

        mt5_positions = mt5.positions_get(symbol=self.config.symbol)
        if mt5_positions is None:
            return []

        positions = []
        for pos in mt5_positions:
            if pos.magic == self.config.magic_number:
                order_type = OrderType.BUY if pos.type == 0 else OrderType.SELL
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
                    magic=pos.magic
                ))
        return positions

    def execute_order(self, signal: TradeSignal) -> Tuple[bool, str]:
        """
        Executes market order on MT5 terminal or updates mock state.
        """
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
