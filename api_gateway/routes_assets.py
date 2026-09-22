"""
Asset discovery, taxonomy categorization, historical rates, and sync routes.
Strict route ordering: static history routes registered strictly BEFORE /{symbol}.
"""
import logging
import threading
import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse

from strategy_engine.historical_db import HistoricalRatesDB
from strategy_engine.models import (
    AssetInfo,
    HistoricalRatesResponse,
    HistoricalSyncResponse,
    HistoricalSyncStatus,
    TIMEFRAME_TO_MT5,
)
from .routes_strategy import connector, _state_lock

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/assets", tags=["Assets & Instruments"])

# Single-active-job mutex and sync progress telemetry
_sync_lock = threading.Lock()
_active_sync_thread: Optional[threading.Thread] = None
_sync_status = HistoricalSyncStatus(
    job_id=None,
    status="IDLE",
    completed_assets=0,
    failed_assets=0,
    total_assets=0,
    current_symbol=None,
    message="",
)


def _reset_sync_state() -> None:
    """Reset historical sync state (used by test suites)."""
    global _active_sync_thread
    with _sync_lock:
        _sync_status.job_id = None
        _sync_status.status = "IDLE"
        _sync_status.completed_assets = 0
        _sync_status.failed_assets = 0
        _sync_status.total_assets = 0
        _sync_status.current_symbol = None
        _sync_status.message = ""
        _active_sync_thread = None


def _set_sync_state_for_testing(
    status: str = "IN_PROGRESS",
    job_id: Optional[str] = "mock-active-job-xyz",
    total_assets: int = 1,
) -> None:
    """Explicitly set sync state for concurrency tests."""
    with _sync_lock:
        _sync_status.status = status
        _sync_status.job_id = job_id
        _sync_status.total_assets = total_assets


def _sync_worker(job_id: str, symbols: List[str], timeframe: str, fresh: bool, throttle_sec: float = 0.025) -> None:
    """Background worker thread performing non-blocking rates ingestion with 25ms yield."""
    global _sync_status
    db = HistoricalRatesDB()
    try:
        for sym in symbols:
            with _sync_lock:
                if _sync_status.job_id != job_id:
                    return
                _sync_status.current_symbol = sym

            bars, _ = connector.sync_historical_rates(
                symbol=sym,
                timeframe=timeframe,
                fresh=fresh,
                db=db,
            )

            with _sync_lock:
                if _sync_status.job_id != job_id:
                    return
                if bars is None:
                    logger.warning(f"Historical rates fetch returned None for {sym}; incrementing failed_assets.")
                    _sync_status.failed_assets += 1
                else:
                    _sync_status.completed_assets += 1

            if throttle_sec > 0:
                time.sleep(throttle_sec)

        with _sync_lock:
            if _sync_status.job_id == job_id:
                _sync_status.status = "COMPLETED"
                _sync_status.current_symbol = None
                _sync_status.message = (
                    f"Sync completed: {_sync_status.completed_assets} succeeded, "
                    f"{_sync_status.failed_assets} failed."
                )
    except Exception as exc:
        logger.error(f"Historical sync job {job_id} failed: {exc}", exc_info=True)
        with _sync_lock:
            if _sync_status.job_id == job_id:
                _sync_status.status = "FAILED"
                _sync_status.current_symbol = None
                _sync_status.message = f"Sync failed: {exc}"


# 1. POST /history/sync (preceding dynamic /{symbol})
@router.post("/history/sync", status_code=status.HTTP_202_ACCEPTED, response_model=HistoricalSyncResponse)
def trigger_historical_sync(
    symbol: Optional[str] = Query(None, description="Optional single asset symbol to synchronize"),
    category: Optional[str] = Query(None, description="Optional asset category (all, stocks, etfs, forex)"),
    timeframe: str = Query("D1", description="Historical bar timeframe (e.g. D1)"),
    fresh: bool = Query(False, description="Clear existing records and perform fresh inception sync"),
):
    """
    Initiate an asynchronous background historical rates sync job.
    Guarded by single-active-job mutex; rejects overlapping requests with HTTP 409 Conflict.
    """
    global _sync_status, _active_sync_thread

    clean_tf = timeframe.strip().upper()
    if clean_tf not in TIMEFRAME_TO_MT5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported timeframe '{timeframe}'. Supported timeframes: {', '.join(TIMEFRAME_TO_MT5.keys())}",
        )

    with _sync_lock:
        if _sync_status.status == "IN_PROGRESS":
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "detail": "Sync job already in progress",
                    "current_job_id": _sync_status.job_id,
                    "status": "IN_PROGRESS",
                },
            )

        if symbol:
            symbols = [symbol.strip().upper()]
        else:
            cat = category or "all"
            try:
                assets = connector.get_available_assets(category=cat)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
            except ConnectionError as exc:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
            symbols = [a.symbol for a in assets]

        job_id = str(uuid.uuid4())
        _sync_status = HistoricalSyncStatus(
            job_id=job_id,
            status="IN_PROGRESS",
            completed_assets=0,
            failed_assets=0,
            total_assets=len(symbols),
            current_symbol=symbols[0] if symbols else None,
            message="Sync job initiated",
        )

        _active_sync_thread = threading.Thread(
            target=_sync_worker,
            args=(job_id, symbols, clean_tf, fresh),
            daemon=True,
            name=f"HistoricalSyncWorker-{job_id[:8]}",
        )
        _active_sync_thread.start()

        return HistoricalSyncResponse(
            job_id=job_id,
            status="IN_PROGRESS",
            message="Historical sync job started",
        )


# 2. GET /history/sync/status (preceding dynamic /{symbol})
@router.get("/history/sync/status", response_model=HistoricalSyncStatus)
def get_historical_sync_status() -> HistoricalSyncStatus:
    """
    Retrieve telemetry and execution progress for the active or latest historical sync job.
    """
    with _sync_lock:
        return _sync_status


# 3. GET /{symbol}/history (preceding dynamic /{symbol})
@router.get("/{symbol}/history", response_model=HistoricalRatesResponse)
def get_historical_rates_endpoint(
    symbol: str,
    timeframe: str = Query("D1", description="Historical bar timeframe (e.g. D1, H1)"),
    limit: int = Query(500, ge=1, le=5000, description="Max bars per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> HistoricalRatesResponse:
    """
    Retrieve paginated historical OHLCV bars from local SQLite storage.
    """
    clean_tf = timeframe.strip().upper()
    if clean_tf not in TIMEFRAME_TO_MT5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported timeframe '{timeframe}'. Supported timeframes: {', '.join(TIMEFRAME_TO_MT5.keys())}",
        )

    clean_sym = symbol.strip().upper()

    db = HistoricalRatesDB()
    bars, total_bars = db.get_rates(
        symbol=clean_sym,
        timeframe=clean_tf,
        limit=limit,
        offset=offset,
    )

    if total_bars <= 0:
        total_pages = 1
        page = 1
    else:
        total_pages = max(1, (total_bars + limit - 1) // limit)
        page = min(total_pages, (offset // limit) + 1)

    return HistoricalRatesResponse(
        symbol=clean_sym,
        timeframe=clean_tf,
        bars=bars,
        total_bars=total_bars,
        limit=limit,
        offset=offset,
        page=page,
        total_pages=total_pages,
    )


# 4. GET /{symbol} (single asset spec)
@router.get("/{symbol}", response_model=AssetInfo)
def get_asset_by_symbol(symbol: str) -> AssetInfo:
    """
    Fetch full contract specifications and current quotes for a single asset symbol.
    """
    try:
        with _state_lock:
            asset = connector.get_asset_info(symbol)
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if asset is None:
        raise HTTPException(
            status_code=404,
            detail=f"Asset '{symbol}' not found in broker catalog",
        )

    return asset


# 5. GET / and GET "" (assets catalog)
@router.get("", response_model=List[AssetInfo])
@router.get("/", response_model=List[AssetInfo], include_in_schema=False)
def get_assets(
    category: Optional[str] = Query(None, description="Asset category filter (all, stocks, etfs, forex)"),
    search: Optional[str] = Query(None, description="Substring search filter on symbol or description"),
) -> List[AssetInfo]:
    """
    Retrieve available tradeable assets with category and search filtering.
    """
    try:
        with _state_lock:
            return connector.get_available_assets(category=category, search=search)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
