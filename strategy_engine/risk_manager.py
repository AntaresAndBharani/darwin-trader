"""
Risk Management Engine tailored specifically for Darwinex Zero evaluation parameters.
Enforces max drawdown limits, maximum open trades, and dynamic position sizing.
"""
from typing import List, Tuple
from .models import TradeSignal, SignalType, Position, AccountInfo
from .config import StrategyConfig


class RiskManager:
    def __init__(self, config: StrategyConfig):
        self.config = config

    def validate_signal(
        self,
        signal: TradeSignal,
        account: AccountInfo,
        open_positions: List[Position]
    ) -> Tuple[bool, str]:
        """
        Returns (is_allowed, refusal_reason).
        Validates trade execution against Darwinex Zero safety rules.
        """
        if signal.signal_type == SignalType.HOLD:
            return False, "Signal is HOLD"

        # 1. Check Max Open Positions Limit
        if len(open_positions) >= self.config.max_open_positions:
            return False, f"Max open positions limit reached ({len(open_positions)}/{self.config.max_open_positions})"

        # 2. Check Daily Max Drawdown Cap
        floating_drawdown_pct = 0.0
        if account.balance > 0:
            floating_drawdown_pct = max(0.0, (account.balance - account.equity) / account.balance * 100.0)

        if floating_drawdown_pct >= self.config.max_daily_drawdown_pct:
            return False, f"Max daily drawdown breach ({floating_drawdown_pct:.2f}% >= {self.config.max_daily_drawdown_pct}%)"

        # 3. Check Account Free Margin
        if account.free_margin < (account.balance * 0.05):
            return False, f"Insufficient free margin (${account.free_margin:.2f})"

        return True, "Valid"

    def calculate_lot_size(self, account_balance: float, stop_loss_pips: float, point_value: float = 10.0) -> float:
        """
        Calculates position lot size based on fixed account risk % per trade.
        """
        if stop_loss_pips <= 0:
            return 0.01

        risk_amount = account_balance * (self.config.risk_per_trade_pct / 100.0)
        lot_size = risk_amount / (stop_loss_pips * point_value)
        # Round to 2 decimal places (standard micro-lots = 0.01)
        lot_size = round(max(0.01, min(10.0, lot_size)), 2)
        return lot_size
