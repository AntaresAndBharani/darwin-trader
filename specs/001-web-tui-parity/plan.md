# Implementation Plan: Unified Web & TUI Startup and Connection Parity

**Branch**: `001-web-tui-parity` | **Date**: 2026-10-22 | **Spec**: [spec.md](file:///c:/Users/rogal/workspaces/ws-trading/darwin-trader/specs/001-web-tui-parity/spec.md)

**Input**: Feature specification from `/specs/001-web-tui-parity/spec.md`

## Summary

Unify the Web application (`web/`) startup, auto-connection, and `ConnectModal` behavior with the reference Terminal UI (`tui/`):
1. **Single-Command Server Startup**: Add a Vite dev server lifecycle plugin (`darwinGatewayPlugin` in `web/vite.config.ts`) and a root PowerShell launcher (`scripts/run-web.ps1`) so running `npm run web`, `npm run dev`, or `.\scripts\run-web.ps1` automatically checks if the FastAPI Gateway (`127.0.0.1:8000`) is running, spawns it if needed, and cleanly terminates any self-spawned Gateway process on exit.
2. **Zero-Click Live MT5 Attachment**: Automatically connect to Account `4000073238` on `Darwinex-Live` (`mock_mode: false`, `path: "C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe"`) on startup (in both the server launcher and `web/src/App.tsx` on initial mount when the gateway is still in its unconfigured default state) without opening `ConnectModal`.
3. **1:1 `ConnectModal` Parity**: Update `web/src/components/ConnectModal.tsx` to match `tui/screens/connect_modal.py` defaults (`DEFAULT_LOGIN = 4000073238`, `DEFAULT_SERVER = 'Darwinex-Live'`, `SERVER_CHOICES = ['Darwinex-Demo', 'Darwinex-Live', 'MetaQuotes-Demo']`, `DEFAULT_TERMINAL_PATH = 'C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe'`, optional password for Win32 IPC attach, and `mockMode = false` by default).

## Technical Context

**Language/Version**: TypeScript 5.6 (React 18, Node.js 20+), Python 3.11+, PowerShell 5.1/7+

**Primary Dependencies**: Vite 6, React 18.3, Axios 1.7, FastAPI, Uvicorn, Vitest 2.1, Testing Library

**Storage**: N/A (in-memory gateway runtime state & Win32 IPC to MetaTrader 5 `terminal64.exe`)

**Testing**: `vitest run` (`npm test`), `eslint .` (`npm run lint`), `tsc -b && vite build` (`npm run build`), and `pytest api_gateway/tests strategy_engine/tests tui/tests`

**Target Platform**: Windows workstation (with Darwinex MetaTrader 5 terminal) & headless Linux CI (`mock_mode` simulation)

**Project Type**: Full-stack Web + Terminal UI + FastAPI Gateway (`web/`, `tui/`, `api_gateway/`, `strategy_engine/`, `scripts/`)

**Performance Goals**: Single-command Web + API readiness and live MT5 IPC attachment in `< 10` seconds; immediate UI telemetry refresh on connect (`< 200ms` local IPC)

**Constraints**: Must never spawn background servers or attempt live MT5 connections during `vitest` or `pytest` runs; must not leave orphaned `uvicorn` processes on exit

**Scale/Scope**: 5 files modified/created across `web/` and `scripts/` (`<= 250` LOC diff)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Clean Architecture & Pure Quantitative Core**: ✅ PASS — All changes are strictly confined to the Presentation/Launcher tier (`web/`, `scripts/`). Zero changes or framework imports in `strategy_engine/`.
- **II. Darwinex Zero Risk & Capital Preservation**: ✅ PASS — Connects directly to live Darwinex account telemetry (`4000073238`) so real-time drawdown and open positions are monitored accurately.
- **III. Multi-Client Parity & Zero-Click Operational Readiness**: ✅ PASS — Directly fulfills Principle III by aligning Web startup, auto-connection, and `ConnectModal` defaults 1:1 with TUI (`run-tui.ps1` and `tui/screens/connect_modal.py`).
- **IV. Test-First & Platform-Independent Simulation**: ✅ PASS — `darwinGatewayPlugin` is disabled when `process.env.VITEST` is active, and `App.tsx` / `ConnectModal.tsx` unit tests mock API calls deterministically in Vitest.
- **V. Structured Concurrency, Lock Discipline & Observability**: ✅ PASS — Uses existing thread-safe `POST /api/v1/account/connect` endpoint guarded by `_state_lock` and `MT5Connector._lock`.

## Project Structure

### Documentation (this feature)

```text
specs/001-web-tui-parity/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── account-connect.md
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
scripts/
├── run-tui.ps1                          # Existing reference TUI + Gateway launcher
└── run-web.ps1                          # NEW: PowerShell Web + Gateway launcher with live auto-connect

web/
├── package.json                         # Includes "web": "vite" and "dev": "vite" scripts
├── vite.config.ts                       # MODIFIED: Adds darwinGatewayPlugin for auto-starting API + auto-connect
└── src/
    ├── App.tsx                          # MODIFIED: Mount-time auto-connect to 4000073238 / Darwinex-Live + status refresh
    ├── App.test.tsx                     # MODIFIED: Verifies auto-connect on mount and closed modal by default
    └── components/
        ├── ConnectModal.tsx             # MODIFIED: 1:1 TUI parity (4000073238, Darwinex-Live, path, mockMode=false)
        └── ConnectModal.test.tsx        # MODIFIED: Tests TUI-parity defaults, Terminal Path field, and IPC connect
```

**Structure Decision**: Extends the existing `web/` React/Vite frontend and `scripts/` PowerShell automation directory without introducing new packages or altering backend domain layers.

## Complexity Tracking

No constitution violations; table omitted.
