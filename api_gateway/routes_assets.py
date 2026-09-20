"""
Asset discovery, taxonomy categorization, and contract specification routes.
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from strategy_engine.models import AssetInfo
from .routes_strategy import connector, _state_lock

router = APIRouter(prefix="/api/v1/assets", tags=["Assets & Instruments"])


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
