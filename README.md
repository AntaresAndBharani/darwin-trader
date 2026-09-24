# Darwin Trader

An algorithmic trading platform designed for MetaTrader 5 (MT5) with a modern Terminal User Interface (Textual TUI), a FastAPI gateway, and a high-performance Python quantitative strategy backtesting and execution engine.

---

## 🏛️ System Architecture

```
+-------------------------------------------------------------------------+
|                      Darwin Trader TUI (tui/)                           |
|                   Python · Textual · AsyncIO Telemetry                  |
+-------------------------------------------------------------------------+
                                    |
                                    v (REST API / WebSocket)
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

- **Real-Time Account Telemetry:** Monitor equity, balance, floating PnL, and live MT5 positions via 1Hz WebSocket streaming.
- **Interactive Terminal UI (TUI):** Asynchronous, keyboard-driven ANSI dashboard with interactive modals (Asset Explorer, Account Connection, Confirmation), live summary cards, and keyed differential tables.
- **Strategy Control & Risk Management:** Configure live risk percentage, max daily drawdown caps, and magic numbers directly from the TUI or REST API.
- **Backtesting Simulation Engine:** Run bar-by-bar backtests on EURUSD and major pairs, inspect win rates, profit factors, and maximum drawdown curves.
- **Multi-Symbol Historical Ingestion & Granular Purge:** Parallel historical bar ingestion with worker pool concurrency and granular timeframe/asset purge capabilities.
- **Darwinex Zero Compliance:** Prioritizes capital preservation, strict daily drawdown constraints, dynamic volatility-adjusted position sizing, and algorithmic consistency.

---

## 🧪 Testing & Execution

### 1. Run Complete Test Suite
```powershell
# Run all unit and integration tests across Gateway, Strategy Engine, and TUI
pytest api_gateway/tests strategy_engine/tests tui/tests
```

### 2. Launch Terminal User Interface (TUI)
```powershell
# Launch the Textual TUI dashboard
.\scripts\run-tui.ps1
# or directly via python
python -m tui.app
```

---

## 🤖 Agentic SDLC Pipeline

Darwin Trader runs the full 5-node Agentic SDLC state graph:
- **Architect (Claude Sonnet 5 - Medium Effort):** Decomposes PO User Stories (`user-story.yml`) into SMART subtasks (`subtask.yml`) via native GitHub Sub-issues with read-only repository tool exploration.
- **Three Amigos (Gemini 3.7 Flash):** Batch readiness review across all subtasks for a story; evaluates QA testability and assigns test suites.
- **Dev & Test (Gemini 3.7 Flash / Antigravity):** Implements subtasks, runs unit and integration tests, auto-resolves approved conflicting PRs, and opens PRs with test summaries.
- **PR Review (Claude Sonnet):** Authoritative code review inspecting diffs, acceptance criteria, and test coverage.
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