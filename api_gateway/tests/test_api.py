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


def test_account_connect_path_fallback_preserves_config():
    from api_gateway.routes_strategy import global_config

    configured_path = "C:\\Configured\\Darwinex MetaTrader 5\\terminal64.exe"
    global_config.mt5_path = configured_path

    # Calling connect without 'path' field
    resp = client.post(
        "/api/v1/account/connect",
        json={
            "login": 123456,
            "password": "pwd",
            "server": "Darwinex-Demo",
            "mock_mode": True,
        },
    )
    assert resp.status_code == 200
    assert global_config.mt5_path == configured_path

    # Calling connect with explicit None 'path'
    resp_none = client.post(
        "/api/v1/account/connect",
        json={
            "login": 123456,
            "password": "pwd",
            "server": "Darwinex-Demo",
            "path": None,
            "mock_mode": True,
        },
    )
    assert resp_none.status_code == 200
    assert global_config.mt5_path == configured_path


def test_account_connect_explicit_path_overrides_config():
    from api_gateway.routes_strategy import global_config

    global_config.mt5_path = "C:\\Default\\Path\\terminal64.exe"
    explicit_path = "D:\\Custom\\MT5\\terminal64.exe"

    resp = client.post(
        "/api/v1/account/connect",
        json={
            "login": 654321,
            "password": "pwd",
            "server": "Darwinex-Demo",
            "path": explicit_path,
            "mock_mode": True,
        },
    )
    assert resp.status_code == 200
    assert global_config.mt5_path == explicit_path


def test_concurrent_account_connect():
    """
    Verifies that concurrent POST /api/v1/account/connect requests maintain atomicity
    and never produce a torn state in global_config or connector.
    """
    import concurrent.futures
    from api_gateway.routes_strategy import global_config, connector

    def send_connect(i: int):
        login_val = 100000 + i
        server_val = f"Darwinex-Server-{i}"
        resp = client.post(
            "/api/v1/account/connect",
            json={
                "login": login_val,
                "password": f"pwd-{i}",
                "server": server_val,
                "mock_mode": True
            }
        )
        return resp.status_code, resp.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(send_connect, i) for i in range(20)]
        results = [f.result() for f in futures]

    for status_code, data in results:
        assert status_code == 200
        assert data["status"] == "CONNECTED"
        assert data["error"] is None

    # Verify that final global_config and connector state match one atomic request
    acc_info = connector.get_account_info()
    assert global_config.mt5_login == acc_info.login
    assert global_config.mt5_server == acc_info.server
    # Verify login and server have matching index (no torn fields)
    if global_config.mt5_login >= 100000:
        idx = global_config.mt5_login - 100000
        assert global_config.mt5_server == f"Darwinex-Server-{idx}"


def test_concurrent_connect_and_status():
    """
    Verifies that GET /api/v1/account/status concurrent with POST /api/v1/account/connect
    never observes a torn/partial state (e.g. CONNECTED with None connected_at or stale error).
    """
    import concurrent.futures
    import threading

    stop_event = threading.Event()
    status_observations = []

    def status_poller():
        while not stop_event.is_set():
            resp = client.get("/api/v1/account/status")
            if resp.status_code == 200:
                status_observations.append(resp.json())

    def connect_worker(i: int):
        login_val = 200000 + i
        server_val = f"Darwinex-Demo-{i}"
        return client.post(
            "/api/v1/account/connect",
            json={
                "login": login_val,
                "password": f"pwd-{i}",
                "server": server_val,
                "mock_mode": True
            }
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        poller_future = executor.submit(status_poller)
        connect_futures = [executor.submit(connect_worker, i) for i in range(15)]
        for f in concurrent.futures.as_completed(connect_futures):
            res = f.result()
            assert res.status_code == 200
        stop_event.set()
        poller_future.result()

    assert len(status_observations) > 0
    for obs in status_observations:
        if obs["status"] == "CONNECTED":
            assert obs["connected_at"] is not None
            assert obs["last_error"] is None
            if obs["account_info"] is not None:
                login_val = obs["account_info"]["login"]
                if isinstance(login_val, int) and 200000 <= login_val < 200020:
                    idx = login_val - 200000
                    assert obs["server"] == f"Darwinex-Demo-{idx}"

