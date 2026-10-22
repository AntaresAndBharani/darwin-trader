# Quickstart & Validation Guide: Unified Web & TUI Startup and Connection Parity

**Feature**: `001-web-tui-parity`
**Date**: 2026-10-22

## Prerequisites

- **Python 3.11+** with `api_gateway` and `strategy_engine` dependencies installed
- **Node.js 20+** with `web/` dependencies installed (`npm install` in `web/`)
- **Darwinex MetaTrader 5** (`C:\Program Files\Darwinex MetaTrader 5\terminal64.exe`) running and logged into account `4000073238` (`Darwinex-Live`) for live IPC verification

---

## Scenario 1: Single-Command Launch via `npm run web`

1. Ensure no process is listening on port `8000` or `5173`.
2. From `c:\Users\rogal\workspaces\ws-trading\darwin-trader\web`, run:
   ```powershell
   npm run web
   ```
3. **Expected Outcome**:
   - Vite automatically starts the FastAPI Gateway on `http://127.0.0.1:8000`.
   - Vite automatically dispatches `POST /api/v1/account/connect` for account `4000073238` on `Darwinex-Live` (`mock_mode: false`).
   - Open `http://localhost:5173/`: the Status Ribbon displays `CONNECTED` and `Darwinex-Live` with live balance/equity, and the Connect Modal is **closed**.

---

## Scenario 2: Single-Command Launch via `.\scripts\run-web.ps1`

1. From `c:\Users\rogal\workspaces\ws-trading\darwin-trader`, run:
   ```powershell
   .\scripts\run-web.ps1
   ```
2. **Expected Outcome**:
   - Verifies `terminal64.exe`, starts or reuses the FastAPI Gateway on `127.0.0.1:8000`, auto-connects to `4000073238` on `Darwinex-Live`, and starts the Vite Web server.
   - Pressing `Ctrl+C` stops the Web server and cleanly stops the background FastAPI Gateway if `run-web.ps1` spawned it.

---

## Scenario 3: Verify Connect Modal TUI Parity

1. Open `http://localhost:5173/` and click **Connect MT5...** in the header.
2. **Expected Outcome**:
   - **Server** defaults to `Darwinex-Live` (with `Darwinex-Demo`, `Darwinex-Live`, `MetaQuotes-Demo` options).
   - **MT5 Login Account** is pre-filled with `4000073238`.
   - **Password** is empty and optional.
   - **Terminal Path** is pre-filled with `C:\Program Files\Darwinex MetaTrader 5\terminal64.exe`.
   - **Simulation / Mock Mode** is **unchecked**.
3. Click **Connect** without typing a password and confirm it connects and closes the modal.

---

## Automated Test Suite Validation

```powershell
# 1. Run Frontend Unit & Integration Tests, Linter, and Build
cd c:\Users\rogal\workspaces\ws-trading\darwin-trader\web
npm test
npm run lint
npm run build

# 2. Run Backend & TUI Test Suites
cd c:\Users\rogal\workspaces\ws-trading\darwin-trader
pytest api_gateway/tests strategy_engine/tests tui/tests
```
