# 📋 Implementation Plan & Specification: Web & TUI Startup, Auto-Connect, and ConnectModal Parity

## 📝 Initial Draft Proposal (Operator Requisite)

> "The node application is requesting me data to connect to DarwinX Zero, but the TUI is doing it automatically. I want the same exact behaviour in both, and the TUI is the correct one. TUI is also executing the API at the same time is running. I just want to start the server and start working. Let analyze this."

---

## 🔍 Root-Cause Analysis & Ground Truth Comparison (TUI vs. Web)

| Capability | TUI (`scripts/run-tui.ps1` + `tui/screens/connect_modal.py`) | Web App (`web/` prior to fix) |
| :--- | :--- | :--- |
| **Single-Command Server Startup** | `.\scripts\run-tui.ps1` checks if `127.0.0.1:8000` is open; if not, spawns `python -m uvicorn api_gateway.main:app --host 127.0.0.1 --port 8000` in the background, waits for `ONLINE`, and stops it on exit. | `npm run web` / `npm run dev` only starts Vite (`port 5173`), requiring a separate manual terminal for the FastAPI Gateway. |
| **Zero-Click Auto-Connect to Live MT5** | Automatically sends `POST /api/v1/account/connect` with `{ login: 4000073238, server: "Darwinex-Live", mock_mode: false }`. Because `password` is omitted, `MT5Connector.initialize()` attaches directly to the running `terminal64.exe` via IPC without prompting. | Never calls `/api/v1/account/connect` on startup; leaves the API Gateway in its initial `StrategyConfig(mock_mode=True, mt5_server="Darwinex-Demo")` state. |
| **Connect Modal Default Server** | `Darwinex-Live` (Select with `Darwinex-Demo`, `Darwinex-Live`, `MetaQuotes-Demo`) | `Darwinex-Demo` |
| **Connect Modal Default Login** | `4000073238` | `""` (empty) |
| **Connect Modal Terminal Path** | `C:\Program Files\Darwinex MetaTrader 5\terminal64.exe` (`#input-path`) | Missing |
| **Connect Modal Default Mock Mode** | `False` (unchecked when MT5 terminal exists) | `True` (checked by default) |

---

## 🎯 Final Decision Plan & User Story Specification

### User Story
**As an** algorithmic trader using Darwin Trader,
**I want** the Web application (`npm run web` / `.\scripts\run-web.ps1`) to automatically start the FastAPI Gateway if it is not running, automatically attach to my live Darwinex MT5 terminal (`4000073238` on `Darwinex-Live`, `mock_mode: false`) without prompting for credentials, and pre-populate the Connect Modal with the exact same defaults as the TUI,
**So that** I can launch the Web server with a single command and start working immediately with live DarwinX Zero telemetry.

### Architectural Decisions (Resolved via `/grill-me`)

1. **Dual Single-Command Startup (`web/vite.config.ts` + `scripts/run-web.ps1`):**
   - **Vite Dev Server Lifecycle Plugin (`web/vite.config.ts`):**
     - Implement `darwinGatewayPlugin()` executing inside `configureServer` (skipped when running under Vitest or production build).
     - Checks TCP connectivity to `127.0.0.1:8000`. If port `8000` is not open, spawns `python -m uvicorn api_gateway.main:app --host 127.0.0.1 --port 8000` with `cwd` set to the repository root (`..`), polls `http://127.0.0.1:8000/` until `"status": "ONLINE"` (up to 10 seconds), and hooks server/process termination to cleanly kill the spawned Python process on exit.
     - Whether the Gateway was spawned by Vite or was already running on port `8000`, dispatches `POST http://127.0.0.1:8000/api/v1/account/connect` with `{ login: 4000073238, server: "Darwinex-Live", path: "C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe", mock_mode: false }` (unless `VITE_MOCK_MODE=true` is set).
   - **PowerShell Launcher (`scripts/run-web.ps1`):**
     - Mirrors `scripts/run-tui.ps1`: checks if `terminal64.exe` is running, checks/starts the FastAPI Gateway on `127.0.0.1:8000`, auto-connects to `4000073238` on `Darwinex-Live` (unless `-Mock` is passed), runs `npm --prefix web run web`, and stops the background Gateway on exit if started by the script.

2. **Frontend Auto-Connect Assurance (`web/src/App.tsx`):**
   - On initial mount in `App.tsx`, checks `api.getConnectionStatus()`. If the Gateway has not yet connected to live (`mock_mode === true` and `server === 'Darwinex-Demo'`), dispatches `accountApi.connect({ login: 4000073238, server: 'Darwinex-Live', path: DEFAULT_TERMINAL_PATH, mock_mode: false })` once in the background.
   - Does **not** open `ConnectModal` automatically; `ConnectModal` opens only when the operator clicks `"Connect MT5..."` or `"Broker Connection Settings..."`.

3. **1:1 `ConnectModal.tsx` Parity with TUI (`web/src/components/ConnectModal.tsx`):**
   - Aligns constants with `tui/screens/connect_modal.py`:
     - `DEFAULT_LOGIN = 4000073238`
     - `DEFAULT_SERVER = 'Darwinex-Live'`
     - `SERVER_CHOICES = ['Darwinex-Demo', 'Darwinex-Live', 'MetaQuotes-Demo']`
     - `DEFAULT_TERMINAL_PATH = 'C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe'`
     - `defaultMockMode = false`
   - Adds optional **Terminal Path** input (`data-testid="connect-path-input"`) pre-filled with `DEFAULT_TERMINAL_PATH`.
   - Updates **Server** field (`data-testid="connect-server-input"`) to offer `SERVER_CHOICES` defaulting to `'Darwinex-Live'`.
   - Pre-fills **MT5 Login Account** (`data-testid="connect-login-input"`) with `4000073238`.
   - Keeps **Password** (`data-testid="connect-password-input"`) optional so empty password performs passwordless IPC attach to the running `terminal64.exe` instance.
   - Sets **Simulation / Mock Mode** (`data-testid="connect-mock-mode-input"`) to `false` (unchecked) by default.

---

### Component Impact Table (Pattern A — Standalone Slice)

| File | Action | Description |
| :--- | :--- | :--- |
| `web/vite.config.ts` | Modify | Add `darwinGatewayPlugin` to auto-start FastAPI Gateway on `127.0.0.1:8000` (if not running), auto-connect to `4000073238` / `Darwinex-Live` during `npm run web` / `npm run dev`, and clean up on exit. |
| `scripts/run-web.ps1` | Create | PowerShell launcher mirroring `scripts/run-tui.ps1` for one-command Web + API launch and teardown. |
| `web/src/components/ConnectModal.tsx` | Modify | Align defaults (`4000073238`, `Darwinex-Live`, `mockMode = false`, `DEFAULT_TERMINAL_PATH`, server selector) 1:1 with TUI `ConnectModal`. |
| `web/src/App.tsx` | Modify | Add mount-time auto-connect check to `4000073238` / `Darwinex-Live` if gateway is still in initial default mock state, while keeping `ConnectModal` closed by default. |
| `web/src/components/ConnectModal.test.tsx` & `web/src/App.test.tsx` | Modify | Update and expand unit/integration tests verifying TUI-parity defaults, Terminal Path payload, and auto-connect behavior. |

---

### Gherkin BDD Acceptance Criteria

```gherkin
Feature: Unified Web & TUI Startup, Auto-Connect, and ConnectModal Parity

  Scenario 1: Single-command Web startup automatically starts FastAPI Gateway and connects to Darwinex-Live
    Given the FastAPI Gateway on 127.0.0.1:8000 is not running
    When the operator executes "npm run web" (or ".\scripts\run-web.ps1")
    Then the FastAPI Gateway is spawned automatically in the background on 127.0.0.1:8000
    And once the Gateway reports status "ONLINE", a POST request to "/api/v1/account/connect" is sent with login 4000073238, server "Darwinex-Live", and mock_mode false
    And when the Web server stops, the spawned FastAPI Gateway process is cleanly terminated

  Scenario 2: Starting Web server when FastAPI Gateway is already running reuses the Gateway and auto-connects
    Given the FastAPI Gateway is already listening on 127.0.0.1:8000
    When the operator executes "npm run web" (or opens the Web application)
    Then no duplicate FastAPI Gateway process is spawned
    And the Gateway is automatically connected to login 4000073238 on "Darwinex-Live" with mock_mode false
    And the Connect Modal remains closed on startup

  Scenario 3: ConnectModal pre-populates 1:1 with TUI defaults
    Given the Web application is loaded
    When the operator clicks "Connect MT5..." to open the Connect Modal
    Then the Login input is pre-filled with 4000073238
    And the Server selector defaults to "Darwinex-Live" with options "Darwinex-Demo", "Darwinex-Live", and "MetaQuotes-Demo"
    And the Terminal Path input is pre-filled with "C:\Program Files\Darwinex MetaTrader 5\terminal64.exe"
    And the Password input is empty and optional
    And the "Simulation / Mock Mode" checkbox is unchecked (false) by default

  Scenario 4: Passwordless IPC submission from ConnectModal
    Given the Connect Modal is open with default TUI-parity values (4000073238, "Darwinex-Live", mock_mode false, empty password)
    When the operator clicks "Connect"
    Then POST "/api/v1/account/connect" is dispatched with login 4000073238, password "", server "Darwinex-Live", path "C:\Program Files\Darwinex MetaTrader 5\terminal64.exe", and mock_mode false
    And the modal closes upon receiving status "CONNECTED"
```
