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
