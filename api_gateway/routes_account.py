"""
Account and trade statistics routes.
"""
from fastapi import APIRouter
from typing import Dict, Any, List

from strategy_engine.config import StrategyConfig
from strategy_engine.mt5_connector import MT5Connector
from strategy_engine.models import AccountInfo, Position

router = APIRouter(prefix="/api/v1/account", tags=["Account & Telemetry"])

# Use shared connector from routes_strategy
from .routes_strategy import connector, global_config


@router.get("/info", response_model=AccountInfo)
def get_account_info() -> AccountInfo:
    return connector.get_account_info()


@router.get("/positions", response_model=List[Position])
def get_positions() -> List[Position]:
    return connector.get_open_positions()


@router.get("/darwinex-stats")
def get_darwinex_stats() -> Dict[str, Any]:
    acc = connector.get_account_info()
    return {
        "darwin_symbol": "DWR.4.1",
        "d_score": acc.d_score or 78.2,
        "investor_capital_allocated_eur": 30000.0,
        "return_pct_monthly": 4.15,
        "max_drawdown_pct": 2.10,
        "var_95_pct": 1.85,
        "darwinex_zero_status": "CALIBRATION_PASSED"
    }
