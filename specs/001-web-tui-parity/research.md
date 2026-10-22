# Phase 0 Research: Unified Web & TUI Startup and Connection Parity

**Feature**: `001-web-tui-parity`
**Date**: 2026-10-22

## Research Decisions

### 1. Unified Process Orchestration for `npm run web` / `npm run dev` and `.\scripts\run-web.ps1`

- **Decision**: Implement a dual orchestration mechanism:
  1. A custom Vite server lifecycle plugin (`darwinGatewayPlugin` in `web/vite.config.ts`) that runs inside `configureServer` when Vite starts in dev mode (`npm run web` or `npm run dev`, bypassed under Vitest).
  2. A PowerShell launcher script (`scripts/run-web.ps1`) mirroring `scripts/run-tui.ps1`.
- **Rationale**:
  - Operators frequently start the Web app either from `web/` via `npm run web` / `npm run dev` or from the repository root via `.\scripts\run-web.ps1`.
  - Checking TCP connectivity on `127.0.0.1:8000` before spawning `python -m uvicorn api_gateway.main:app --host 127.0.0.1 --port 8000` ensures idempotency: if `run-web.ps1` (or the user) already started the Gateway, the Vite plugin detects port `8000` is open and does not spawn a duplicate process.
  - Tracking a boolean `gatewayStartedByProcess` flag ensures only the process that spawned the background Gateway terminates it upon exit.
- **Alternatives Considered**:
  - *`concurrently` npm package*: Unconditionally spawns Uvicorn every time `npm run web` runs, failing with `EADDRINUSE` if the Gateway is already running on port `8000`.
  - *PowerShell launcher only*: Fails to start the Gateway when the operator runs `npm run web` directly inside `web/`.

---

### 2. Zero-Click Live MT5 Auto-Connection Strategy

- **Decision**: Perform automatic live connection (`POST /api/v1/account/connect` with `{ login: 4000073238, server: "Darwinex-Live", path: "C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe", mock_mode: false }`) at two layers:
  1. **Startup Layer (`vite.config.ts` plugin & `scripts/run-web.ps1`)**: Immediately after verifying `GET http://127.0.0.1:8000/` is `ONLINE`, dispatch `POST /api/v1/account/connect` (unless `MOCK_MODE` / `-Mock` is explicitly set).
  2. **Frontend Mount Layer (`web/src/App.tsx`)**: On initial mount, inspect `GET /api/v1/account/status`. If the Gateway is still in its unconfigured startup default (`mock_mode === true` and `server === "Darwinex-Demo"`), call `accountApi.connect({ login: 4000073238, server: "Darwinex-Live", path: DEFAULT_TERMINAL_PATH, mock_mode: false })` once in the background without opening `ConnectModal`.
- **Rationale**:
  - Matches `scripts/run-tui.ps1` lines 78–94 where the launcher auto-connects the Gateway to `4000073238` on `Darwinex-Live`.
  - Adding the idempotent mount-time check in `App.tsx` guarantees that even if an operator started `uvicorn` manually in another terminal (which initializes `StrategyConfig(mock_mode=True, mt5_server="Darwinex-Demo")`), opening the Web app still transitions the Gateway to live `4000073238` (`Darwinex-Live`) automatically without popping open the Connect Modal.
  - Preserves `StrategyConfig(mock_mode=True)` at Python module import time in `api_gateway/routes_strategy.py` so headless `pytest` suites remain 100% isolated from live Win32 MT5 IPC.
- **Alternatives Considered**:
  - *Changing `global_config = StrategyConfig(mock_mode=False)` at module import time in `routes_strategy.py`*: Rejected because importing `api_gateway.main` in `pytest` would immediately attempt live Win32 IPC during unit test collection.

---

### 3. 1:1 `ConnectModal.tsx` Parity with TUI `ConnectModal` (`tui/screens/connect_modal.py`)

- **Decision**: Export shared constants in `web/src/components/ConnectModal.tsx` matching `tui/screens/connect_modal.py`:
  - `DEFAULT_TERMINAL_PATH = "C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe"`
  - `DEFAULT_LOGIN = 4000073238`
  - `DEFAULT_SERVER = "Darwinex-Live"`
  - `SERVER_CHOICES = ["Darwinex-Demo", "Darwinex-Live", "MetaQuotes-Demo"]`
  - `defaultMockMode = false`
  - Add the optional `Terminal Path` input (`data-testid="connect-path-input"`) pre-filled with `DEFAULT_TERMINAL_PATH` and include `path` in the `accountApi.connect()` payload.
- **Rationale**:
  - Enforces Principle III of the Darwin Trader Constitution (*Multi-Client Parity & Zero-Click Operational Readiness*).
  - Enables passwordless Win32 IPC attachment from the Web modal just by clicking "Connect".
- **Alternatives Considered**:
  - *Keeping a free-text Server input without predefined options or omitting `Terminal Path`*: Rejected by operator during `/grill-me` in favor of 1:1 parity with TUI.
