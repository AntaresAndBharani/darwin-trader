---
description: "Task list for Unified Web & TUI Startup and Connection Parity"
---

# Tasks: Unified Web & TUI Startup and Connection Parity

**Input**: Design documents from `/specs/001-web-tui-parity/`

**Prerequisites**: [plan.md](file:///c:/Users/rogal/workspaces/ws-trading/darwin-trader/specs/001-web-tui-parity/plan.md), [spec.md](file:///c:/Users/rogal/workspaces/ws-trading/darwin-trader/specs/001-web-tui-parity/spec.md), [research.md](file:///c:/Users/rogal/workspaces/ws-trading/darwin-trader/specs/001-web-tui-parity/research.md), [data-model.md](file:///c:/Users/rogal/workspaces/ws-trading/darwin-trader/specs/001-web-tui-parity/data-model.md), [account-connect.md](file:///c:/Users/rogal/workspaces/ws-trading/darwin-trader/specs/001-web-tui-parity/contracts/account-connect.md)

**Tests**: Automated unit and integration tests are included per Principle IV of the Darwin Trader Constitution (*Test-First & Platform-Independent Simulation (NON-NEGOTIABLE)*).

**Organization**: Tasks are grouped by user story (`US1`, `US2`, `US3`) to enable independent implementation and verification.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`)
- Exact file paths are included in every task description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Ensure package scripts and shared connection constants are in place.

- [X] T001 Ensure `"web": "vite"` and `"dev": "vite"` scripts are defined in `web/package.json`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared TUI-parity default constants and `AccountConnectRequest` contract alignment in `web/src/components/ConnectModal.tsx` and `web/src/api/account.ts`.

**⚠️ CRITICAL**: Must be complete before user stories depend on shared connection defaults.

- [X] T002 Export TUI-parity constants (`DEFAULT_LOGIN = 4000073238`, `DEFAULT_SERVER = 'Darwinex-Live'`, `SERVER_CHOICES = ['Darwinex-Demo', 'Darwinex-Live', 'MetaQuotes-Demo']`, `DEFAULT_TERMINAL_PATH = 'C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe'`) in `web/src/components/ConnectModal.tsx`

**Checkpoint**: Shared constants ready — User Story phases can now execute.

---

## Phase 3: User Story 1 - Single-Command Server Launch with Automatic Gateway Orchestration (Priority: P1) 🎯 MVP

**Goal**: Starting the Web server via `npm run web`, `npm run dev`, or `.\scripts\run-web.ps1` automatically checks if the FastAPI Gateway (`127.0.0.1:8000`) is listening, starts it in the background if not running, and cleanly terminates any self-spawned Gateway process on exit.

**Independent Test**: Stop any process on port `8000`, run `npm run web` (or `.\scripts\run-web.ps1`), verify `http://127.0.0.1:8000/` returns `{"status": "ONLINE"}` and `http://localhost:5173/` loads, then stop the server and confirm port `8000` is freed.

### Implementation for User Story 1

- [X] T003 [P] [US1] Implement `darwinGatewayPlugin` in `web/vite.config.ts` (disabled when `process.env.VITEST` is set) to check TCP port `127.0.0.1:8000`, spawn `python -m uvicorn api_gateway.main:app --host 127.0.0.1 --port 8000` from repo root (`..`) if closed, poll `http://127.0.0.1:8000/` up to 10s until `status === "ONLINE"`, and terminate the child process on Vite server close/exit
- [X] T004 [P] [US1] Create `scripts/run-web.ps1` mirroring `scripts/run-tui.ps1` with parameters `-Mock`, `-Port 8000`, `-WebPort 5173`, and `-HostAddress "127.0.0.1"` to check `terminal64.exe`, start/reuse the FastAPI Gateway, launch `npm --prefix web run web`, and stop any self-spawned Gateway in `finally`

**Checkpoint**: User Story 1 is functional — single-command startup orchestrates both Web and FastAPI Gateway.

---

## Phase 4: User Story 2 - Zero-Click Automatic Attachment to Live Darwinex Account (Priority: P1)

**Goal**: Automatically connect to Account `4000073238` on `Darwinex-Live` (`mock_mode: false`, `path: "C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe"`) on startup and initial Web dashboard load without opening `ConnectModal`.

**Independent Test**: Launch the Web dashboard while `terminal64.exe` is running (or against a Gateway in default `Darwinex-Demo` mock state) and verify `POST /api/v1/account/connect` is called automatically with `{ login: 4000073238, server: "Darwinex-Live", path: "C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe", mock_mode: false }` and `ConnectModal` remains closed.

### Tests for User Story 2

- [X] T005 [P] [US2] Add unit test in `web/src/App.test.tsx` verifying that on initial mount, when `api.getConnectionStatus()` reports default unconfigured state (`server: 'Darwinex-Demo'`, `mock_mode: true`), `App` automatically calls `accountApi.connect` with `{ login: 4000073238, server: 'Darwinex-Live', path: 'C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe', mock_mode: false }` while keeping `ConnectModal` closed

### Implementation for User Story 2

- [X] T006 [P] [US2] Extend `darwinGatewayPlugin` in `web/vite.config.ts` and `scripts/run-web.ps1` to dispatch `POST http://127.0.0.1:8000/api/v1/account/connect` with `{ login: 4000073238, server: "Darwinex-Live", path: "C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe", mock_mode: false }` as soon as the Gateway is online (unless `-Mock` or `VITE_MOCK_MODE=true` is set)
- [X] T007 [US2] Update `web/src/App.tsx` to check `api.getConnectionStatus()` on mount and automatically invoke `accountApi.connect({ login: DEFAULT_LOGIN, server: DEFAULT_SERVER, path: DEFAULT_TERMINAL_PATH, mock_mode: false })` if the Gateway has not yet connected to `Darwinex-Live`, keeping `isConnectOpen` `false` by default

**Checkpoint**: User Stories 1 and 2 are complete — launching the server automatically starts the API and attaches to live `4000073238` on `Darwinex-Live`.

---

## Phase 5: User Story 3 - 1:1 Connection Modal Defaults & Passwordless Terminal Attachment (Priority: P2)

**Goal**: Align `web/src/components/ConnectModal.tsx` 1:1 with TUI's `tui/screens/connect_modal.py` (`login = 4000073238` required positive integer `> 0`, `server = 'Darwinex-Live'` selectable from `['Darwinex-Demo', 'Darwinex-Live', 'MetaQuotes-Demo']`, `path = 'C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe'` normalized to `null` if blank, optional `password = ''` for passwordless IPC attach, and `mockMode = false` by default).

**Independent Test**: Open `ConnectModal` in the Web UI, verify all 5 fields match TUI defaults, click "Connect" with an empty password, and verify `accountApi.connect` is called with the expected payload.

### Tests for User Story 3

- [X] T008 [P] [US3] Update and expand unit tests in `web/src/components/ConnectModal.test.tsx` to verify default values (`4000073238`, `'Darwinex-Live'`, `'C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe'`, `mockMode = false`, empty password), server options (`Darwinex-Demo`, `Darwinex-Live`, `MetaQuotes-Demo`), terminal path normalization (`null` when blank), and passwordless IPC submission

### Implementation for User Story 3

- [X] T009 [US3] Update `web/src/components/ConnectModal.tsx` to default `defaultServer = DEFAULT_SERVER` (`'Darwinex-Live'`), `defaultLogin = DEFAULT_LOGIN` (`4000073238`), `defaultPath = DEFAULT_TERMINAL_PATH`, and `defaultMockMode = false`, render a `<select data-testid="connect-server-input">` with `SERVER_CHOICES`, add the optional Terminal Path input (`data-testid="connect-path-input"`), and pass `path: path.trim() || null` and `mock_mode: mockMode` to `accountApi.connect()`

**Checkpoint**: All 3 user stories are independently functional and tested.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation, documentation sync, and live server restart.

- [X] T010 [P] Update `README.md` and `CHANGELOG.md` under `## [Unreleased]` documenting `.\scripts\run-web.ps1`, `npm run web` auto-gateway orchestration, live auto-connect, and `ConnectModal` TUI parity
- [X] T011 Run full validation suite (`npm test`, `npm run lint`, `npm run build` in `web/` and `pytest api_gateway/tests strategy_engine/tests tui/tests` in root) and restart the running Web server so live `Darwinex-Live` (`4000073238`) connection is active

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — starts immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 — exports shared constants used by `US2` and `US3`.
- **User Story 1 (Phase 3 - P1)**: Can execute in parallel across `web/vite.config.ts` and `scripts/run-web.ps1`.
- **User Story 2 (Phase 4 - P1)**: Depends on Phase 2 & Phase 3.
- **User Story 3 (Phase 5 - P2)**: Depends on Phase 2; can run in parallel with `US1`/`US2`.
- **Polish (Phase 6)**: Depends on Phases 3, 4, and 5 completion.

### Parallel Opportunities

- `T003` (`web/vite.config.ts`) and `T004` (`scripts/run-web.ps1`) touch different files and can run in parallel.
- `T005` (`web/src/App.test.tsx`) and `T008` (`web/src/components/ConnectModal.test.tsx`) touch different test files and can run in parallel.

---

## Parallel Example: User Story 1 & 3

```bash
# Parallel Launcher Tasks (US1):
Task T003: "Implement darwinGatewayPlugin in web/vite.config.ts"
Task T004: "Create scripts/run-web.ps1 mirroring scripts/run-tui.ps1"

# Parallel Test Tasks (US2 & US3):
Task T005: "Add mount-time auto-connect unit test in web/src/App.test.tsx"
Task T008: "Update TUI-parity default & submission tests in web/src/components/ConnectModal.test.tsx"
```

---

## Implementation Strategy

### MVP First (User Stories 1 & 2 — Both Priority P1)

1. Complete Phase 1 (`T001`) and Phase 2 (`T002`).
2. Complete Phase 3 (`T003`–`T004`) and Phase 4 (`T005`–`T007`) to achieve single-command server launch + automatic live connection to `4000073238` (`Darwinex-Live`).
3. Complete Phase 5 (`T008`–`T009`) for 1:1 `ConnectModal` parity.
4. Complete Phase 6 (`T010`–`T011`) to verify all tests and update the running server.
