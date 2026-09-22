"""
Asynchronous HTTP client for Darwin Trader TUI.
Interacts with the FastAPI Gateway (api_gateway) with resilient offline fallback.
"""
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel

from strategy_engine.models import (
    AccountConnectRequest,
    AccountConnectResponse,
    AccountInfo,
    AssetInfo,
    ConnectionState,
    ConnectionStatus,
    HistoricalRatesResponse,
    HistoricalSyncResponse,
    HistoricalSyncStatus,
    Position,
)


class ApiResponse(BaseModel):
    """Generic wrapper for API responses with fallback metadata."""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    is_offline: bool = False


class DarwinApiClient:
    """
    Asynchronous client wrapper over httpx.AsyncClient.
    Provides resilient error handling and safe fallback defaults when the gateway is unreachable.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        timeout: float = 3.0,
        historical_timeout: float = 15.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.historical_timeout = historical_timeout
        self._external_client = client
        self._client: Optional[httpx.AsyncClient] = client

    async def get_client(self) -> httpx.AsyncClient:
        """Returns the active httpx.AsyncClient or initializes a new connection pool."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def close(self) -> None:
        """Closes the underlying HTTP client session if owned."""
        if self._external_client is None and self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def get_account_status(self) -> ConnectionStatus:
        """
        GET /api/v1/account/status
        Returns connection status telemetry. Falls back to DISCONNECTED with error if unreachable.
        """
        try:
            client = await self.get_client()
            resp = await client.get("/api/v1/account/status")
            resp.raise_for_status()
            data = resp.json()
            return ConnectionStatus(**data)
        except Exception as exc:
            return ConnectionStatus(
                status=ConnectionState.DISCONNECTED,
                server="Unknown",
                mock_mode=True,
                latency_ms=0.0,
                last_error=str(exc) or "Gateway unreachable",
            )

    async def get_account_info(self) -> Optional[AccountInfo]:
        """
        GET /api/v1/account/info
        Returns current account balances and metrics. Returns None if unreachable.
        """
        try:
            client = await self.get_client()
            resp = await client.get("/api/v1/account/info")
            resp.raise_for_status()
            return AccountInfo(**resp.json())
        except Exception:
            return None

    async def get_positions(self) -> List[Position]:
        """
        GET /api/v1/account/positions
        Returns open positions list. Returns empty list if unreachable.
        """
        try:
            client = await self.get_client()
            resp = await client.get("/api/v1/account/positions")
            resp.raise_for_status()
            raw_list = resp.json()
            return [Position(**p) for p in raw_list]
        except Exception:
            return []

    async def get_strategy_status(self) -> Optional[Dict[str, Any]]:
        """
        GET /api/v1/strategy/status
        Returns strategy running state. Returns None if unreachable.
        """
        try:
            client = await self.get_client()
            resp = await client.get("/api/v1/strategy/status")
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    async def start_strategy(self) -> Dict[str, Any]:
        """
        POST /api/v1/strategy/start
        Starts the algorithmic trading strategy.
        """
        try:
            client = await self.get_client()
            resp = await client.post("/api/v1/strategy/start")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"message": "Failed to start strategy", "status": "ERROR", "detail": str(exc)}

    async def pause_strategy(self) -> Dict[str, Any]:
        """
        POST /api/v1/strategy/pause
        Pauses the algorithmic trading strategy without liquidating positions.
        """
        try:
            client = await self.get_client()
            resp = await client.post("/api/v1/strategy/pause")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"message": "Failed to pause strategy", "status": "ERROR", "detail": str(exc)}

    async def connect_account(self, request: AccountConnectRequest) -> AccountConnectResponse:
        """
        POST /api/v1/account/connect
        Submits login credentials to MT5 gateway. Falls back to ERROR response on network exception.
        """
        try:
            client = await self.get_client()
            resp = await client.post("/api/v1/account/connect", json=request.model_dump())
            resp.raise_for_status()
            return AccountConnectResponse(**resp.json())
        except Exception as exc:
            return AccountConnectResponse(
                status=ConnectionState.ERROR,
                message=f"Gateway connection error: {exc}",
                login=request.login,
                server=request.server,
                trade_mode="DEMO" if "demo" in request.server.lower() else "REAL",
                balance=0.0,
                currency="USD",
                account_info=None,
                error=str(exc) or "Network error",
            )

    async def kill_switch(self) -> Dict[str, Any]:
        """
        POST /api/v1/strategy/kill-switch
        Emergency stop that closes all positions and pauses strategy.
        """
        try:
            client = await self.get_client()
            resp = await client.post("/api/v1/strategy/kill-switch")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {
                "message": "Failed to activate kill switch",
                "positions_closed": 0,
                "detail": str(exc),
                "status": "ERROR",
            }

    async def get_assets(
        self,
        category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[AssetInfo]:
        """
        GET /api/v1/assets
        Returns available tradeable assets filtered by category and/or search substring.
        Returns empty list if gateway is unreachable or an error occurs.
        """
        try:
            client = await self.get_client()
            params: Dict[str, str] = {}
            if category:
                params["category"] = category
            if search:
                params["search"] = search
            resp = await client.get("/api/v1/assets", params=params)
            resp.raise_for_status()
            raw_list = resp.json()
            return [AssetInfo(**item) for item in raw_list]
        except Exception:
            return []

    async def get_asset_info(self, symbol: str) -> Optional[AssetInfo]:
        """
        GET /api/v1/assets/{symbol}
        Fetches full contract specifications for a single asset symbol.
        Returns None if not found or gateway is unreachable.
        """
        try:
            client = await self.get_client()
            resp = await client.get(f"/api/v1/assets/{symbol.strip()}")
            resp.raise_for_status()
            return AssetInfo(**resp.json())
        except Exception:
            return None

    async def sync_historical_rates(
        self,
        symbol: Optional[str] = None,
        category: Optional[str] = None,
        timeframe: str = "D1",
        fresh: bool = False,
    ) -> HistoricalSyncResponse:
        """
        POST /api/v1/assets/history/sync
        Submits an asynchronous historical rates synchronization request with 15.0s timeout.
        Handles 409 Conflict if a sync job is already in progress.
        """
        try:
            client = await self.get_client()
            params: Dict[str, Any] = {
                "timeframe": timeframe,
                "fresh": fresh,
            }
            if symbol:
                params["symbol"] = symbol
            if category:
                params["category"] = category

            resp = await client.post(
                "/api/v1/assets/history/sync",
                params=params,
                timeout=httpx.Timeout(self.historical_timeout),
            )
            if resp.status_code == 409:
                data = resp.json()
                return HistoricalSyncResponse(
                    job_id=data.get("current_job_id") or "",
                    status="IN_PROGRESS",
                    message=data.get("detail", "Sync job already in progress"),
                )
            resp.raise_for_status()
            return HistoricalSyncResponse(**resp.json())
        except Exception as exc:
            return HistoricalSyncResponse(
                job_id="",
                status="ERROR",
                message=f"Sync request failed: {exc}",
            )

    async def get_sync_status(self) -> HistoricalSyncStatus:
        """
        GET /api/v1/assets/history/sync/status
        Queries current historical sync job status and telemetry with 15.0s timeout.
        """
        try:
            client = await self.get_client()
            resp = await client.get(
                "/api/v1/assets/history/sync/status",
                timeout=httpx.Timeout(self.historical_timeout),
            )
            resp.raise_for_status()
            return HistoricalSyncStatus(**resp.json())
        except Exception as exc:
            return HistoricalSyncStatus(
                job_id=None,
                status="IDLE",
                completed_assets=0,
                failed_assets=0,
                total_assets=0,
                current_symbol=None,
                message=f"Gateway unreachable: {exc}",
            )

    async def get_historical_rates(
        self,
        symbol: str,
        timeframe: str = "D1",
        limit: int = 500,
        offset: int = 0,
    ) -> HistoricalRatesResponse:
        """
        GET /api/v1/assets/{symbol}/history?timeframe={timeframe}&limit={limit}&offset={offset}
        Queries paginated historical OHLCV bars with dedicated 15.0s timeout.
        Falls back to empty HistoricalRatesResponse if gateway is unreachable.
        """
        clean_sym = symbol.strip().upper()
        clean_tf = timeframe.strip().upper()
        try:
            client = await self.get_client()
            params = {
                "timeframe": clean_tf,
                "limit": limit,
                "offset": offset,
            }
            resp = await client.get(
                f"/api/v1/assets/{clean_sym}/history",
                params=params,
                timeout=httpx.Timeout(self.historical_timeout),
            )
            resp.raise_for_status()
            return HistoricalRatesResponse(**resp.json())
        except Exception:
            return HistoricalRatesResponse(
                symbol=clean_sym,
                timeframe=clean_tf,
                bars=[],
                total_bars=0,
                limit=limit,
                offset=offset,
                page=1,
                total_pages=1,
            )


