# Feature Specification: Unified Web & TUI Startup and Connection Parity

**Feature Branch**: `001-web-tui-parity`

**Created**: 2026-10-22

**Status**: Draft

**Input**: User description: "The node application is requesting me data to connect to DarwinX Zero, but the TUI is doing it automatically. I want the same exact behaviour in both, and the TUI is the correct one. TUI is also executing the API at the same time is running. I just want to start the server and start working."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Single-Command Server Launch with Automatic Gateway Orchestration (Priority: P1)

As an algorithmic trader launching the Web dashboard, I want starting the Web application (either via the standard web start command or the dedicated launcher script) to automatically verify whether the backend trading gateway service is running and start it in the background if needed, so that I never have to manage two separate server processes manually.

**Why this priority**: The operator's primary workflow requirement is "start the server and start working." Requiring separate manual startup of the backend service before launching the Web dashboard introduces friction and diverges from the single-command TUI experience.

**Independent Test**: Can be fully tested by stopping all running backend processes, launching the Web server with a single command, verifying that both the backend gateway and the Web interface become reachable, and confirming that stopping the Web server cleanly terminates the background gateway it started.

**Acceptance Scenarios**:

1. **Given** the backend trading gateway is not currently running, **When** the operator starts the Web application via the web command or launcher script, **Then** the system automatically starts the backend trading gateway in the background and waits until it reports healthy before serving the Web dashboard.
2. **Given** the backend trading gateway was started automatically by the Web application launcher, **When** the operator terminates the Web application session, **Then** the background trading gateway process is cleanly stopped without leaving orphaned background processes.
3. **Given** the backend trading gateway is already running prior to launching the Web application, **When** the operator starts the Web application, **Then** the system reuses the existing backend gateway without spawning a duplicate process and leaves that external gateway running when the Web session exits.

---

### User Story 2 - Zero-Click Automatic Attachment to Live Darwinex Account (Priority: P1)

As an algorithmic trader opening the Web dashboard, I want the system to automatically connect to my live Darwinex trading account (`4000073238` on `Darwinex-Live` in live mode) by attaching directly to the active MetaTrader 5 terminal without prompting me for credentials, so that live balance, equity, positions, and DarwinX Zero risk metrics are immediately active on launch.

**Why this priority**: In the TUI reference implementation, launching the client immediately connects to `4000073238` on `Darwinex-Live` without opening a login modal or defaulting to demo simulation. The Web dashboard must behave identically so the trader never works against unintended demo/mock telemetry.

**Independent Test**: Can be fully tested by launching the Web dashboard while the desktop trading terminal is running and verifying that the status ribbon immediately reflects `CONNECTED` to `Darwinex-Live` for account `4000073238` in live mode, with the connection dialog remaining closed.

**Acceptance Scenarios**:

1. **Given** the desktop trading terminal is running on the workstation, **When** the Web application starts up or loads in the browser, **Then** the system automatically establishes a live connection to account `4000073238` on server `Darwinex-Live` (`mock_mode` disabled) without displaying the connection modal.
2. **Given** the backend gateway was previously started in its unconfigured default simulation state (`Darwinex-Demo` / simulation mode), **When** the Web dashboard loads, **Then** it automatically transitions the session to account `4000073238` on `Darwinex-Live` in live mode and refreshes account telemetry.
3. **Given** the Web dashboard is launched, **When** the initial view renders, **Then** the connection modal remains closed unless the operator explicitly selects the button to open connection settings.

---

### User Story 3 - 1:1 Connection Modal Defaults & Passwordless Terminal Attachment (Priority: P2)

As an algorithmic trader who manually opens the Connection Settings dialog in the Web dashboard to inspect or switch accounts, I want the dialog to pre-populate the exact same defaults as the TUI (`Login = 4000073238`, `Server = Darwinex-Live`, selectable broker servers, default terminal installation path, optional password, and simulation mode unchecked), so that reconnecting or switching accounts requires zero repetitive data entry.

**Why this priority**: Ensures complete visual and behavioral parity between the Web and TUI connection dialogs when manual reconnection or account switching is needed.

**Independent Test**: Can be tested independently by clicking "Connect MT5..." in the Web dashboard, verifying all five form fields match the TUI defaults, and clicking "Connect" with no password entered to confirm passwordless attachment to the running terminal.

**Acceptance Scenarios**:

1. **Given** the Web dashboard is open, **When** the operator clicks "Connect MT5..." or "Broker Connection Settings...", **Then** the modal displays with Server set to `Darwinex-Live` (offering `Darwinex-Demo`, `Darwinex-Live`, and `MetaQuotes-Demo`), Login pre-filled with `4000073238`, Terminal Path pre-filled with `C:\Program Files\Darwinex MetaTrader 5\terminal64.exe`, Password empty and optional, and Simulation / Mock Mode unchecked.
2. **Given** the Connection Modal is open with default values and an empty password, **When** the operator clicks "Connect", **Then** the system submits the connection request with the configured terminal path and live mode enabled, attaches to the running terminal session, updates the dashboard telemetry, and closes the modal.

---

### Edge Cases

- **Desktop trading terminal is not running at launch**: The launcher warns the operator that the desktop trading terminal process is not detected, attempts the live connection (which allows the local terminal binary at the configured path to initialize or reports a clear `ERROR` status badge in the status ribbon), and keeps the connection modal closed unless the operator chooses to open it.
- **Backend gateway fails to become healthy within the startup timeout**: If the spawned backend gateway does not respond as online within 10 seconds, the launcher logs a clear error message, terminates any partially started gateway process, and exits with a non-zero status code.
- **Explicit simulation override requested**: When the operator explicitly launches with a simulation flag (`-Mock` or environment override), the launcher skips live auto-connect and keeps the session in safe simulation mode.
- **Automated test suite execution**: Running headless unit or integration tests must never trigger background server spawning or live desktop terminal connections.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide single-command Web startup (via both the standard web package scripts and a root launcher script) that checks whether the backend gateway is listening on its configured port (`8000`) and automatically starts it in the background if not already running.
- **FR-002**: System MUST cleanly terminate any backend gateway process that it spawned when the Web server session stops, while leaving externally started gateway processes untouched.
- **FR-003**: System MUST automatically initiate a live account connection to login `4000073238` on server `Darwinex-Live` with simulation mode disabled (`mock_mode = false`) and default terminal path `C:\Program Files\Darwinex MetaTrader 5\terminal64.exe` during startup and upon initial Web dashboard load if the gateway is still in its unconfigured default state.
- **FR-004**: System MUST NOT automatically open the connection modal on Web dashboard startup; the modal MUST only open when explicitly triggered by user action.
- **FR-005**: The Web Connection Modal MUST pre-populate with the exact same defaults as the TUI Connection Modal: Login `4000073238`, Server `Darwinex-Live` (selectable from `Darwinex-Demo`, `Darwinex-Live`, `MetaQuotes-Demo`), Terminal Path `C:\Program Files\Darwinex MetaTrader 5\terminal64.exe`, empty optional Password, and Simulation / Mock Mode unchecked (`false`).
- **FR-006**: The Web Connection Modal MUST allow submitting a connection request with an empty password so that the backend attaches directly to the already-running desktop trading terminal session without requiring password re-entry.
- **FR-007**: Upon successful connection (automatic or manual), the Web dashboard MUST immediately synchronize account status, balance, equity, open positions, and strategy status without requiring a manual page reload.

### Key Entities

- **Account Connection Configuration**: Represents the target trading session parameters—Account Login ID (`4000073238`), Broker Server (`Darwinex-Live`, `Darwinex-Demo`, `MetaQuotes-Demo`), Optional Password (empty for IPC attach), Terminal Executable Path (`C:\Program Files\Darwinex MetaTrader 5\terminal64.exe`), and Execution Mode (Live vs. Simulation/Mock).
- **Gateway Process Lifecycle State**: Tracks whether the backend gateway was already online prior to Web launch or was spawned as a managed child process requiring teardown on exit.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operators can launch the complete Web + Backend stack and view live `Darwinex-Live` (`4000073238`) account telemetry using a single command in under 10 seconds, with zero manual credential entry.
- **SC-002**: 100% of default field values in the Web Connection Modal match the TUI Connection Modal reference (`Login`, `Server`, `Server Options`, `Terminal Path`, `Password` optionality, and `Mock Mode` state).
- **SC-003**: Terminating a self-spawned Web session leaves 0 orphaned background gateway processes on port `8000`.
- **SC-004**: 100% of automated backend, TUI, and Web test suites pass in headless environments without requiring a live trading terminal.

## Assumptions

- The operator's workstation has the Darwinex MetaTrader 5 terminal installed at the standard path `C:\Program Files\Darwinex MetaTrader 5\terminal64.exe` and logged into account `4000073238` (`Darwinex-Live`), matching the existing TUI configuration.
- Existing headless automated tests rely on simulation mode by default and will continue to run isolated from live terminal connections.
