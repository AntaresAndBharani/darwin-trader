"""
Configuration management for strategy parameters, Darwinex Zero limits, and MT5 setup.
"""
from pydantic import BaseModel
import os


class StrategyConfig(BaseModel):
    # Strategy General Settings
    strategy_name: str = "Darwin_Trend_ATR_V1"
    symbol: str = "EURUSD"
    timeframe: str = "M15"
    magic_number: int = 20260811
    
    # Execution Mode: True = Simulated/Mock execution, False = Live MT5 execution
    mock_mode: bool = True
    
    # Strategy Indicator Parameters
    fast_ema_period: int = 12
    slow_ema_period: int = 26
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    atr_period: int = 14
    atr_multiplier: float = 2.0  # SL = ATR * Multiplier
    
    # Position & Risk Management (Darwinex Zero Focused)
    risk_per_trade_pct: float = 1.0     # 1% per trade
    max_daily_drawdown_pct: float = 3.0 # Hard cap daily drawdown at 3%
    max_open_positions: int = 2
    max_spread_pips: float = 2.5
    
    # MT5 Account Configuration
    mt5_login: int = int(os.getenv("MT5_LOGIN", "0"))
    mt5_password: str = os.getenv("MT5_PASSWORD", "")
    mt5_server: str = os.getenv("MT5_SERVER", "Darwinex-Demo")
    mt5_path: str = os.getenv("MT5_PATH", "C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe")

    def reset_from(self, other: "StrategyConfig | None" = None, **overrides) -> "StrategyConfig":
        """
        Reset instance fields to match another StrategyConfig instance or fresh defaults with optional overrides.
        Avoids directly manipulating private pydantic internals like __dict__ and __pydantic_fields_set__.
        """
        if other is not None:
            source = other.model_copy(update=overrides) if overrides else other
        else:
            source = StrategyConfig(**overrides)
        for key, value in source.model_dump().items():
            setattr(self, key, value)
        return self


# Default global instance
default_config = StrategyConfig()
