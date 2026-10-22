# Interface Contracts: Unified Web & TUI Startup and Connection Parity

**Feature**: `001-web-tui-parity`
**Date**: 2026-10-22

## 1. CLI & Script Launch Contracts

### A. `npm run web` / `npm run dev` (in `web/`)
- **Command**: `npm run web` (or `npm run dev`)
- **Pre-Server Hook (`darwinGatewayPlugin` in `web/vite.config.ts`)**:
  1. Checks TCP port `127.0.0.1:8000`.
  2. If closed, spawns `python -m uvicorn api_gateway.main:app --host 127.0.0.1 --port 8000` in repo root (`..`) and waits up to 10s for `GET http://127.0.0.1:8000/` to return `{"status": "ONLINE"}`.
  3. Unless `process.env.VITE_MOCK_MODE === 'true'`, sends:
     `POST http://127.0.0.1:8000/api/v1/account/connect`
     ```json
     {
       "login": 4000073238,
       "server": "Darwinex-Live",
       "path": "C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe",
       "mock_mode": false
     }
     ```
  4. On Vite server close / `SIGINT` / `SIGTERM`, kills the spawned `uvicorn` process if `gatewayStartedByVite === true`.

### B. `.\scripts\run-web.ps1` (in repository root)
- **Parameters**:
  - `[switch]$Mock = $false`
  - `[int]$Port = 8000`
  - `[int]$WebPort = 5173`
  - `[string]$HostAddress = "127.0.0.1"`
- **Behavior**:
  1. Verifies if `terminal64` process is running (warns if absent and not `-Mock`).
  2. Checks `127.0.0.1:$Port`; if closed, starts `python -m uvicorn api_gateway.main:app --host $HostAddress --port $Port` in background and waits up to 10s for health check.
  3. If not `-Mock`, posts `{ login = 4000073238; server = "Darwinex-Live"; mock_mode = $false }` to `POST /api/v1/account/connect`.
  4. Launches `npm --prefix web run web -- --port $WebPort` in the foreground and stops the background Gateway in `finally` if started by the script.

---

## 2. REST API Contract: `POST /api/v1/account/connect`

- **Request**:
  ```http
  POST /api/v1/account/connect HTTP/1.1
  Content-Type: application/json

  {
    "login": 4000073238,
    "password": "",
    "server": "Darwinex-Live",
    "path": "C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe",
    "mock_mode": false
  }
  ```
- **Response (`200 OK`)**:
  ```json
  {
    "status": "CONNECTED",
    "message": "Connected to MT5 account 4000073238 on Darwinex-Live",
    "login": 4000073238,
    "server": "Darwinex-Live",
    "trade_mode": "REAL",
    "balance": 100000.0,
    "currency": "EUR",
    "account_info": {
      "login": 4000073238,
      "trade_mode": "REAL",
      "server": "Darwinex-Live",
      "balance": 100000.0,
      "equity": 100000.0,
      "margin": 0.0,
      "free_margin": 100000.0,
      "margin_level": 0.0,
      "currency": "EUR",
      "profit": 0.0,
      "d_score": 78.2
    },
    "error": null
  }
  ```

---

## 3. UI Component Contract: `ConnectModal` (`web/src/components/ConnectModal.tsx`)

| Element | `data-testid` | Default Value |
| :--- | :--- | :--- |
| Server selector | `connect-server-input` | `'Darwinex-Live'` (options: `'Darwinex-Demo'`, `'Darwinex-Live'`, `'MetaQuotes-Demo'`) |
| Login input | `connect-login-input` | `4000073238` |
| Password input | `connect-password-input` | `''` (optional) |
| Terminal Path input | `connect-path-input` | `'C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe'` |
| Mock Mode checkbox | `connect-mock-mode-input` | `false` (unchecked) |
| Submit button | `connect-submit-btn` | `'Connect'` |
| Cancel button | `connect-cancel-btn` | `'Cancel'` |
