"""
Strategy control endpoints for starting, pausing, updating parameters, and triggering emergency kill switch.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any

from strategy_engine.config import StrategyConfig
from strategy_engine.models import StrategyState, StrategyStatus
from strategy_engine.mt5_connector import MT5Connector

router = APIRouter(prefix="/api/v1/strategy", tags=["Strategy Controls"])

# Shared runtime state
global_config = StrategyConfig(mock_mode=True)
connector = MT5Connector(global_config)
connector.initialize()

current_status = StrategyStatus.IDLE


@router.get("/status")
def get_strategy_status() -> Dict[str, Any]:
    acc = connector.get_account_info()
    positions = connector.get_open_positions()
    return {
        "status": current_status.value,
        "strategy_name": global_config.strategy_name,
        "symbol": global_config.symbol,
        "mock_mode": global_config.mock_mode,
        "open_positions_count": len(positions),
        "account_balance": acc.balance,
        "account_equity": acc.equity,
        "d_score": acc.d_score
    }


@router.post("/start")
def start_strategy() -> Dict[str, Any]:
    global current_status
    current_status = StrategyStatus.RUNNING
    return {"message": "Strategy started successfully", "status": current_status.value}


@router.post("/pause")
def pause_strategy() -> Dict[str, Any]:
    global current_status
    current_status = StrategyStatus.PAUSED
    return {"message": "Strategy paused", "status": current_status.value}


@router.post("/stop")
def stop_strategy() -> Dict[str, Any]:
    global current_status
    current_status = StrategyStatus.STOPPED
    return {"message": "Strategy stopped", "status": current_status.value}


@router.post("/kill-switch")
def trigger_kill_switch() -> Dict[str, Any]:
    global current_status
    closed_count, msg = connector.close_all_positions()
    current_status = StrategyStatus.PAUSED
    return {
        "message": "Emergency Kill Switch Activated",
        "positions_closed": closed_count,
        "detail": msg,
        "status": current_status.value
    }


@router.post("/config")
def update_config(new_config: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in new_config.items():
        if hasattr(global_config, key):
            setattr(global_config, key, value)
    return {"message": "Config updated", "current_config": global_config.model_dump()}
