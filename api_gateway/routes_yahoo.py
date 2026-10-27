"""
FastAPI Router for Yahoo Finance Market Data, Ticker Metadata, Fundamentals & Sync.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from strategy_engine.yahoo_backtester import (
    get_yahoo_strategies_catalog,
    run_yahoo_portfolio_backtest,
)
from strategy_engine.yahoo_db import YahooFinanceDB, parse_market_symbol
from strategy_engine.yahoo_fetcher import sync_yahoo_tickers

router = APIRouter(prefix="/api/v1/yahoo", tags=["Yahoo Finance"])

yahoo_db = YahooFinanceDB()
_yahoo_lock = threading.Lock()

_sync_state: Dict[str, Any] = {
    "status": "IDLE",
    "total_tickers": 0,
    "completed_tickers": 0,
    "failed_tickers": 0,
    "rows_upserted": 0,
    "valuations_upserted": 0,
    "message": "Idle",
}

_backtest_state: Dict[str, Any] = {
    "status": "IDLE",
    "strategy_id": "darwin_trend",
    "strategy_name": "Darwin Trend ATR",
    "timeframe": "D1",
    "total_symbols": 0,
    "completed_symbols": 0,
    "current_symbol": "",
    "progress_pct": 0.0,
    "elapsed_ms": 0,
    "message": "Idle",
}


class YahooTickerCreateRequest(BaseModel):
    symbol: str = Field(..., description="Ticker symbol or MARKET:SYMBOL")
    name: Optional[str] = ""
    market: Optional[str] = ""
    sector: Optional[str] = ""
    industry: Optional[str] = ""
    active: bool = True


class YahooTickerUpdateRequest(BaseModel):
    active: Optional[bool] = None
    name: Optional[str] = None
    market: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None


class YahooSyncRequest(BaseModel):
    symbol: Optional[str] = None
    symbols: Optional[List[str]] = None
    include_fundamentals: bool = True
    include_valuation: bool = True
    include_metadata: bool = True
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    workers: int = Field(default=5, ge=1, le=32)


class YahooBacktestRequest(BaseModel):
    strategy_id: str = Field(default="darwin_trend")
    symbols: Optional[List[str]] = None
    market: Optional[str] = None
    sector: Optional[str] = None
    timeframe: str = Field(default="D1")
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    initial_balance: float = Field(default=100000.0)
    risk_per_trade_pct: float = Field(default=10.0)
    strategy_params: Optional[Dict[str, Any]] = None


@router.get("/tickers")
def list_yahoo_tickers(
    market: Optional[str] = Query(default=None),
    sector: Optional[str] = Query(default=None),
    industry: Optional[str] = Query(default=None),
    active_only: bool = Query(default=False),
    active: Optional[bool] = Query(default=None),
    search: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """List Yahoo Finance tickers with optional filtering and filter dropdown facets."""
    tickers = yahoo_db.get_tickers(
        market=market,
        sector=sector,
        industry=industry,
        active=active,
        active_only=active_only,
        search=search,
    )
    facets = yahoo_db.get_filter_facets()
    return {
        "total": len(tickers),
        "tickers": tickers,
        "facets": facets,
    }


@router.post("/tickers")
def create_or_upsert_yahoo_ticker(req: YahooTickerCreateRequest) -> Dict[str, Any]:
    """Create or update a ticker in YahooFinanceDB."""
    sym, mkt = parse_market_symbol(req.symbol, req.market or "")
    if not sym:
        raise HTTPException(status_code=400, detail="Ticker symbol cannot be empty.")

    yahoo_db.upsert_tickers(
        [
            {
                "symbol": sym,
                "name": (req.name or sym).strip(),
                "market": mkt,
                "sector": (req.sector or "").strip(),
                "industry": (req.industry or "").strip(),
                "active": req.active,
            }
        ]
    )
    ticker = yahoo_db.get_ticker(sym)
    if not ticker:
        raise HTTPException(status_code=500, detail=f"Failed to persist ticker '{sym}'.")
    return ticker


@router.patch("/tickers/{symbol}")
def update_yahoo_ticker(symbol: str, req: YahooTickerUpdateRequest) -> Dict[str, Any]:
    """Update ticker active state or metadata."""
    sym, _ = parse_market_symbol(symbol)
    if not sym:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")

    updated = yahoo_db.update_ticker(
        sym,
        active=req.active,
        name=req.name,
        market=req.market,
        sector=req.sector,
        industry=req.industry,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Ticker '{sym}' not found.")
    return updated


@router.delete("/tickers/{symbol}")
def delete_yahoo_ticker(symbol: str) -> Dict[str, Any]:
    """Delete a ticker and all associated OHLCV and valuation records."""
    sym, _ = parse_market_symbol(symbol)
    if not sym:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")

    res = yahoo_db.delete_ticker(sym)
    if not res.get("deleted"):
        raise HTTPException(status_code=404, detail=f"Ticker '{sym}' not found.")
    return res


@router.get("/tickers/{symbol}/history")
def get_yahoo_ticker_history(
    symbol: str,
    timeframe: str = Query(default="D1"),
    limit: int = Query(default=1500, ge=1, le=10000),
) -> Dict[str, Any]:
    """Get daily or resampled weekly/monthly OHLCV bars for a ticker."""
    sym, _ = parse_market_symbol(symbol)
    if not sym:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")

    tf = (timeframe or "D1").strip().upper()
    if tf not in {"D1", "W1", "MN1"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported timeframe '{timeframe}'. Supported: D1, W1, MN1.",
        )

    bars, total_bars = yahoo_db.get_price_history(sym, timeframe=tf, limit=limit)
    return {
        "symbol": sym,
        "timeframe": tf,
        "total_bars": total_bars,
        "bars": bars,
    }


@router.get("/tickers/{symbol}/fundamentals")
def get_yahoo_ticker_fundamentals(symbol: str) -> Dict[str, Any]:
    """Get latest valuation snapshot, historical quarterly valuation table, and quarterly EPS/revenue."""
    sym, _ = parse_market_symbol(symbol)
    if not sym:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")

    return yahoo_db.get_fundamentals_summary(sym)


def _execute_sync_job(
    target_symbols: Optional[List[str]],
    include_fundamentals: bool,
    include_valuation: bool,
    include_metadata: bool,
    start_date: Optional[str],
    end_date: Optional[str],
    workers: int,
) -> Dict[str, Any]:
    """Internal worker that executes sync_yahoo_tickers and updates _sync_state."""
    def _on_progress(symbol: str = "", completed: int = 0, failed: int = 0, total: int = 0):
        with _yahoo_lock:
            _sync_state["total_tickers"] = total
            _sync_state["completed_tickers"] = completed
            _sync_state["failed_tickers"] = failed
            _sync_state["message"] = f"Syncing {symbol} ({completed + failed}/{total})..."

    try:
        summary = sync_yahoo_tickers(
            db=yahoo_db,
            symbols=target_symbols,
            include_fundamentals=include_fundamentals,
            include_valuation=include_valuation,
            include_metadata=include_metadata,
            start_date=start_date,
            end_date=end_date,
            workers=workers,
            progress_callback=_on_progress,
        )
        with _yahoo_lock:
            total = summary["total_symbols"]
            completed = summary["completed_symbols"]
            failed_cnt = len(summary["failed_symbols"])
            _sync_state.update(
                {
                    "status": "FAILED" if (total > 0 and completed == 0 and failed_cnt > 0) else "COMPLETED",
                    "total_tickers": total,
                    "completed_tickers": completed,
                    "failed_tickers": failed_cnt,
                    "rows_upserted": summary["upserted_prices"],
                    "valuations_upserted": summary["upserted_valuations"],
                    "message": f"Synced {completed}/{total} ticker(s)",
                }
            )
            return dict(_sync_state)
    except Exception as exc:
        with _yahoo_lock:
            _sync_state.update(
                {
                    "status": "FAILED",
                    "message": f"Sync error: {exc}",
                }
            )
            return dict(_sync_state)


@router.post("/sync", response_model=None)
def trigger_yahoo_sync(req: YahooSyncRequest, background_tasks: BackgroundTasks):
    """
    Trigger on-demand Yahoo Finance synchronization.
    - Single ticker (`symbol` provided): executes synchronously and returns 200 OK.
    - Batch catch-up (`symbol` omitted): runs in background and returns 202 Accepted.
    """
    with _yahoo_lock:
        if _sync_state["status"] == "IN_PROGRESS":
            raise HTTPException(
                status_code=409,
                detail="A Yahoo Finance synchronization job is already in progress.",
            )
        _sync_state.update(
            {
                "status": "IN_PROGRESS",
                "total_tickers": 1 if req.symbol else 0,
                "completed_tickers": 0,
                "failed_tickers": 0,
                "rows_upserted": 0,
                "valuations_upserted": 0,
                "message": "Starting Yahoo Finance synchronization...",
            }
        )

    target_symbols: Optional[List[str]] = None
    if req.symbol and req.symbol.strip():
        target_symbols = [req.symbol.strip()]
    elif req.symbols:
        target_symbols = [s.strip() for s in req.symbols if s and s.strip()]

    if target_symbols and len(target_symbols) == 1:
        result = _execute_sync_job(
            target_symbols=target_symbols,
            include_fundamentals=req.include_fundamentals,
            include_valuation=req.include_valuation,
            include_metadata=req.include_metadata,
            start_date=req.start_date,
            end_date=req.end_date,
            workers=1,
        )
        return result

    background_tasks.add_task(
        _execute_sync_job,
        target_symbols,
        req.include_fundamentals,
        req.include_valuation,
        req.include_metadata,
        req.start_date,
        req.end_date,
        req.workers,
    )
    with _yahoo_lock:
        snapshot = dict(_sync_state)
    return JSONResponse(status_code=202, content=snapshot)


@router.get("/sync/status")
def get_yahoo_sync_status() -> Dict[str, Any]:
    """Return current Yahoo Finance synchronization job status."""
    with _yahoo_lock:
        return dict(_sync_state)


@router.get("/strategies")
def list_yahoo_strategies() -> Dict[str, Any]:
    """Return registered Yahoo Finance strategies and their configurable parameter schemas."""
    return {"strategies": get_yahoo_strategies_catalog()}


@router.get("/strategies/backtest/status")
def get_yahoo_backtest_status() -> Dict[str, Any]:
    """Return current Yahoo Finance strategy backtest execution progress."""
    with _yahoo_lock:
        return dict(_backtest_state)


@router.post("/strategies/backtest")
def execute_yahoo_strategy_backtest(req: YahooBacktestRequest) -> Dict[str, Any]:
    """
    Execute an on-demand historical backtest for one or more Yahoo Finance tickers.
    Runs strictly against `YahooFinanceDB` (`data/yahoo_finance.db`), never touching Darwinex MT5.
    """
    start_ts = time.perf_counter()
    catalog = {s["id"]: s["name"] for s in get_yahoo_strategies_catalog()}
    strategy_name = catalog.get(req.strategy_id, req.strategy_id)
    tf_norm = (req.timeframe or "D1").strip().upper()
    initial_total = len(req.symbols) if req.symbols else 0

    with _yahoo_lock:
        _backtest_state.update(
            {
                "status": "RUNNING",
                "strategy_id": req.strategy_id,
                "strategy_name": strategy_name,
                "timeframe": tf_norm,
                "total_symbols": initial_total,
                "completed_symbols": 0,
                "current_symbol": req.symbols[0] if req.symbols else "",
                "progress_pct": 0.0,
                "elapsed_ms": 0,
                "message": (
                    f"Evaluating 1 / {initial_total} tickers — {req.symbols[0]}..."
                    if req.symbols
                    else "Starting strategy backtest..."
                ),
            }
        )

    def _on_backtest_progress(symbol: str, completed: int, total: int) -> None:
        elapsed_ms = int((time.perf_counter() - start_ts) * 1000)
        pct = round((completed / total) * 100.0, 1) if total > 0 else 0.0
        active_idx = min(completed + 1, total) if total > 0 else 1
        msg = (
            f"Evaluating {active_idx} / {total} tickers — {symbol}..."
            if completed < total
            else f"Completed {total} / {total} tickers"
        )
        with _yahoo_lock:
            _backtest_state.update(
                {
                    "status": "RUNNING",
                    "total_symbols": total,
                    "completed_symbols": completed,
                    "current_symbol": symbol,
                    "progress_pct": pct,
                    "elapsed_ms": elapsed_ms,
                    "message": msg,
                }
            )

    try:
        result = run_yahoo_portfolio_backtest(
            db=yahoo_db,
            strategy_id=req.strategy_id,
            symbols=req.symbols,
            market=req.market,
            sector=req.sector,
            timeframe=req.timeframe,
            from_date=req.from_date,
            to_date=req.to_date,
            initial_balance=req.initial_balance,
            risk_per_trade_pct=req.risk_per_trade_pct,
            strategy_params=req.strategy_params,
            progress_callback=_on_backtest_progress,
        )
        elapsed_ms = int((time.perf_counter() - start_ts) * 1000)
        total_req = int(result.get("total_symbols_requested") or 0)
        with _yahoo_lock:
            _backtest_state.update(
                {
                    "status": "COMPLETED",
                    "strategy_id": result.get("strategy_id", req.strategy_id),
                    "strategy_name": result.get("strategy_name", strategy_name),
                    "timeframe": result.get("timeframe", tf_norm),
                    "total_symbols": total_req,
                    "completed_symbols": total_req,
                    "progress_pct": 100.0,
                    "elapsed_ms": elapsed_ms,
                    "message": f"Completed {total_req} / {total_req} tickers",
                }
            )
        return result
    except ValueError as exc:
        elapsed_ms = int((time.perf_counter() - start_ts) * 1000)
        with _yahoo_lock:
            _backtest_state.update(
                {
                    "status": "FAILED",
                    "elapsed_ms": elapsed_ms,
                    "message": str(exc),
                }
            )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start_ts) * 1000)
        with _yahoo_lock:
            _backtest_state.update(
                {
                    "status": "FAILED",
                    "elapsed_ms": elapsed_ms,
                    "message": f"Backtest error: {exc}",
                }
            )
        raise
