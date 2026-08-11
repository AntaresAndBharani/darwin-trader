"""
FastAPI Server Gateway Entrypoint with WebSockets and REST routes.
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
from datetime import datetime

from .routes_strategy import router as strategy_router, connector
from .routes_account import router as account_router

app = FastAPI(
    title="Darwin Trader API Gateway",
    description="FastAPI Bridge connecting Python MT5 Strategy Engine to Android Mobile App",
    version="1.0.0"
)

# Enable CORS for Android App / Web client connectivity
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(strategy_router)
app.include_router(account_router)


@app.get("/")
def read_root():
    return {
        "app": "Darwin Trader API Gateway",
        "version": "1.0.0",
        "status": "ONLINE",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.websocket("/ws/live")
async def websocket_live_stream(websocket: WebSocket):
    """
    WebSocket endpoint streaming real-time account equity, balance, PnL & tick data to Android App.
    """
    await websocket.accept()
    try:
        while True:
            acc = connector.get_account_info()
            positions = connector.get_open_positions()
            
            payload = {
                "timestamp": datetime.utcnow().isoformat(),
                "balance": acc.balance,
                "equity": acc.equity,
                "profit": acc.profit,
                "free_margin": acc.free_margin,
                "d_score": acc.d_score,
                "positions_count": len(positions),
                "open_positions": [p.model_dump() for p in positions]
            }
            await websocket.send_text(json.dumps(payload, default=str))
            await asyncio.sleep(1.0)  # Push 1Hz telemetry updates
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_gateway.main:app", host="0.0.0.0", port=8000, reload=True)
