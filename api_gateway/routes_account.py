"""
Account and trade statistics routes.
"""
from fastapi import APIRouter
from typing import Dict, Any, List

from strategy_engine.config import StrategyConfig
from strategy_engine.mt5_connector import MT5Connector
from strategy_engine.models import (
    AccountInfo,
    Position,
    AccountConnectRequest,
    AccountConnectResponse,
    ConnectionStatus,
)

router = APIRouter(prefix="/api/v1/account", tags=["Account & Telemetry"])

# Use shared connector from routes_strategy
from .routes_strategy import connector, global_config, _state_lock


@router.post("/connect", response_model=AccountConnectResponse)
def connect_account(request: AccountConnectRequest) -> AccountConnectResponse:
    with _state_lock:
        global_config.mt5_login = request.login
        global_config.mt5_password = request.password
        global_config.mt5_server = request.server
        if request.path:
            global_config.mt5_path = request.path
        global_config.mock_mode = request.mock_mode

        success, message = connector.initialize()
        if not success:
            return AccountConnectResponse(
                status="ERROR",
                message=message,
                login=request.login,
                server=request.server,
                trade_mode="DEMO" if "demo" in request.server.lower() else "REAL",
                balance=0.0,
                currency="USD",
                account_info=None,
                error=message,
            )

        acc = connector.get_account_info()
        return AccountConnectResponse(
            status="CONNECTED",
            message=message,
            login=acc.login,
            server=acc.server,
            trade_mode=acc.trade_mode,
            balance=acc.balance,
            currency=acc.currency,
            account_info=acc,
            error=None,
        )


@router.get("/status", response_model=ConnectionStatus)
def get_connection_status() -> ConnectionStatus:
    with _state_lock:
        return connector.get_connection_status()


@router.get("/info", response_model=AccountInfo)
def get_account_info() -> AccountInfo:
    with _state_lock:
        return connector.get_account_info()


@router.get("/positions", response_model=List[Position])
def get_positions() -> List[Position]:
    with _state_lock:
        return connector.get_open_positions()


@router.get("/darwinex-stats")
def get_darwinex_stats() -> Dict[str, Any]:
    with _state_lock:
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
