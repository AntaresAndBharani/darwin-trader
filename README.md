# Darwin Trader

An algorithmic trading platform designed for MetaTrader 5 (MT5) with a modern Android companion app (Jetpack Compose), a FastAPI gateway, and a high-performance Python strategy backtesting engine.

---

## 🏛️ System Architecture

```
+-------------------------------------------------------------------------+
|                      Darwin Trader Mobile App (Android)                 |
|            Kotlin · Jetpack Compose · Material 3 · Retrofit             |
+-------------------------------------------------------------------------+
                                    |
                                    v (REST API)
+-------------------------------------------------------------------------+
|                     FastAPI Gateway (api_gateway/)                      |
|                  Routes: Account Telemetry · Strategy Control           |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                    Strategy Engine (strategy_engine/)                   |
|                MT5 Connector · Risk Manager · Backtester                |
+-------------------------------------------------------------------------+
```

---

## 🚀 Features

- **Real-Time Account Telemetry:** Monitor equity, balance, floating PnL, and live MT5 positions.
- **Strategy Control & Risk Management:** Configure live risk percentage, max daily drawdown caps, and magic numbers directly from mobile.
- **Backtesting Simulation Engine:** Run backtests on EURUSD and major pairs, inspect win rates, profit factors, and maximum drawdown curves.
- **Dual Flavor Releases:**
  - `prod` (`com.darwintrader.app`) — Production trading client.
  - `snapshot` (`com.darwintrader.app.snapshot`) — Development build installable side-by-side for live testing without touching production data.

---

## 🧪 Testing & E2E Verification

Darwin Trader incorporates the **Graph Engineering 5-Pillar Testing Architecture**:

### 1. Local Unit & Snapshot Build
```powershell
# Android Unit Tests & Snapshot Build
cd android
.\gradlew.bat testSnapshotDebugUnitTest assembleSnapshot -PsnapshotLabel=localtest --no-daemon
cd ..

# Backend Unit Tests
pytest api_gateway/tests strategy_engine/tests
```

### 2. End-to-End (E2E) UI Testing with Maestro
```powershell
# Run delta-targeted E2E test flows based on changed files
.\scripts\run-e2e-tests.ps1 -Delta

# Run specific domain flow tags
.\scripts\run-e2e-tests.ps1 -Tags "dashboard","strategies"

# Capture visual artifacts & sync to docs/screenshots
.\scripts\run-e2e-tests.ps1 -CaptureArtifacts -Version "latest" -PushArtifacts
```

### 3. Declarative E2E Flow Catalog (`e2e/flows/`)
- `01_dashboard_flow.yaml`: Verifies dashboard telemetry, equity, balance, and position cards.
- `02_strategy_control_flow.yaml`: Verifies strategy parameters, risk limits, and save actions.
- `03_backtest_analytics_flow.yaml`: Verifies backtesting simulation UI and performance metrics.
- `04_navigation_flow.yaml`: Verifies full bottom navigation bar screen transitions.

---

## 🤖 Agentic SDLC Pipeline

Darwin Trader runs the full 5-node Agentic SDLC state graph:
- **Architect (Claude Sonnet 5 - High Effort):** Decomposes PO User Stories (`user-story.yml`) into SMART subtasks (`subtask.yml`) via native GitHub Sub-issues with read-only repository tool exploration.
- **Three Amigos (Gemini 3.7 Flash):** Batch readiness review across all subtasks for a story; evaluates QA testability and assigns E2E flow tags.
- **Dev & Test (Gemini 3.7 Flash / Antigravity):** Implements subtasks, runs unit & delta E2E tests, auto-resolves approved conflicting PRs, and opens PRs with sticky test evidence.
- **PR Review (Claude Sonnet):** Authoritative code review inspecting diffs, acceptance criteria, and `<!-- e2e-evidence -->` test comments.
- **Merge & Backlog (Deterministic):** Auto-merges approved PRs and relabels/closes parent stories (`status:done`).
- **Backlog Triage (Gemini 3.7 Flash):** Periodically clusters non-blocking `tech-debt` and `enhancement` issues into actionable user stories.

### Local CLI Execution (Windows Task Scheduler)
The autonomous nodes can be executed locally via Windows Task Scheduler using `scripts/local-pipeline/`:
```powershell
# Register all four scheduled tasks in Task Scheduler (DT-BacklogTriage, DT-PRReview, DT-Architect, DT-ThreeAmigosDevTest)
.\scripts\local-pipeline\register-local-tasks.ps1

# Run individual nodes on demand
.\scripts\local-pipeline\run-backlog-triage.ps1
.\scripts\local-pipeline\run-pr-review.ps1
.\scripts\local-pipeline\run-architect.ps1
.\scripts\local-pipeline\run-three-amigos-and-dev-test.ps1
```

---

## 📋 Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history, release notes, and migration details.

## 📄 License

See [LICENSE](LICENSE).