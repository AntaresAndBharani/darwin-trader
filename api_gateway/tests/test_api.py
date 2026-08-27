"""
Unit tests for API Gateway FastAPI endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from api_gateway.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "Darwin Trader API Gateway"
    assert data["status"] == "ONLINE"


def test_strategy_status_endpoint():
    response = client.get("/api/v1/strategy/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "account_balance" in data
    assert "mock_mode" in data


def test_strategy_control_endpoints():
    # Start strategy
    resp_start = client.post("/api/v1/strategy/start")
    assert resp_start.status_code == 200
    assert resp_start.json()["status"] == "RUNNING"
    
    # Pause strategy
    resp_pause = client.post("/api/v1/strategy/pause")
    assert resp_pause.status_code == 200
    assert resp_pause.json()["status"] == "PAUSED"
    
    # Trigger Kill Switch
    resp_ks = client.post("/api/v1/strategy/kill-switch")
    assert resp_ks.status_code == 200
    assert "Emergency Kill Switch" in resp_ks.json()["message"]


def test_account_endpoints():
    resp_info = client.get("/api/v1/account/info")
    assert resp_info.status_code == 200
    acc = resp_info.json()
    assert acc["balance"] > 0
    
    resp_pos = client.get("/api/v1/account/positions")
    assert resp_pos.status_code == 200
    assert isinstance(resp_pos.json(), list)
    
    resp_darwinex = client.get("/api/v1/account/darwinex-stats")
    assert resp_darwinex.status_code == 200
    assert "d_score" in resp_darwinex.json()


def test_account_connect_and_status_success():
    import time
    start = time.perf_counter()
    resp_connect = client.post(
        "/api/v1/account/connect",
        json={
            "login": 987654,
            "password": "secret_password",
            "server": "Darwinex-Demo",
            "mock_mode": True
        }
    )
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0
    assert resp_connect.status_code == 200
    data = resp_connect.json()
    assert data["status"] == "CONNECTED"
    assert data["login"] == 987654
    assert data["server"] == "Darwinex-Demo"
    assert data["trade_mode"] == "DEMO"
    assert data["balance"] == 100000.0
    assert data["currency"] == "USD"
    assert data["error"] is None

    # Verify status reflects connection
    resp_status = client.get("/api/v1/account/status")
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert status_data["status"] == "CONNECTED"
    assert status_data["server"] == "Darwinex-Demo"
    assert status_data["mock_mode"] is True
    assert status_data["latency_ms"] >= 0.0
    assert status_data["last_error"] is None
    assert status_data["account_info"] is not None
    assert status_data["account_info"]["login"] == 987654


def test_account_connect_and_status_failure(monkeypatch):
    import strategy_engine.mt5_connector as mc
    monkeypatch.setattr(mc, "HAS_MT5", True)

    class FakeMT5:
        @staticmethod
        def initialize(**kwargs):
            return False

        @staticmethod
        def last_error():
            return (-10005, "Invalid account login or password")

    monkeypatch.setattr(mc, "mt5", FakeMT5)

    resp_connect = client.post(
        "/api/v1/account/connect",
        json={
            "login": 111111,
            "password": "wrong_password",
            "server": "Darwinex-Live",
            "mock_mode": False
        }
    )
    assert resp_connect.status_code == 200
    data = resp_connect.json()
    assert data["status"] == "ERROR"
    assert "MT5 initialize failed" in data["message"]
    assert data["error"] is not None

    # Status endpoint reflects ERROR and error diagnostic
    resp_status = client.get("/api/v1/account/status")
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert status_data["status"] == "ERROR"
    assert status_data["server"] == "Darwinex-Live"
    assert status_data["mock_mode"] is False
    assert status_data["last_error"] == data["error"]
    assert status_data["account_info"] is None
