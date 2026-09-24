# Darwin Trader - Project Instructions & Context

## Project Overview
- **Application:** Darwin Trader — Algorithmic Trading Platform (Python Textual TUI Client + Python FastAPI Gateway + MetaTrader5 Strategy Engine).
- **Stack:**
  - **Terminal UI (TUI):** Python 3.11+, Textual, Rich, AsyncIO, HTTPX.
  - **Backend Gateway:** Python 3.11+, FastAPI, Uvicorn, WebSockets, Pydantic v2.
  - **Strategy Engine:** Python 3.11+, MetaTrader5, Pandas, NumPy, SQLite, pytest.

## Quick Commands
- **GitHub Token Setup:** `& C:\Users\rogal\workspaces\Set-GhToken-Antares.ps1` (Run before git push / gh commands)
- **Run Test Suite:** `pytest api_gateway/tests strategy_engine/tests tui/tests`
- **Launch Terminal UI (TUI):** `powershell .\scripts\run-tui.ps1` (or `python -m tui.app`)
- **Local Pipeline Nodes (CLI):**
  - **Register All Scheduled Tasks:** `.\scripts\local-pipeline\register-local-tasks.ps1`
  - **Run Backlog Triage:** `.\scripts\local-pipeline\run-backlog-triage.ps1`
  - **Run PR Review:** `.\scripts\local-pipeline\run-pr-review.ps1`
  - **Run Architect:** `.\scripts\local-pipeline\run-architect.ps1`
  - **Run Three Amigos & Dev-Test:** `.\scripts\local-pipeline\run-three-amigos-and-dev-test.ps1`

## Core Development Guidelines
1. **Architecture:**
   - **Terminal UI:** Textual reactive UI (`tui/`), widgets (`summary_cards.py`, `positions_table.py`, `strategy_panel.py`, `header_bar.py`), modal screens (`connect_modal.py`, `asset_explorer_modal.py`, `confirm_modal.py`), API client (`api_client.py`).
   - **Backend:** Modular FastAPI routes (`routes_account.py`, `routes_strategy.py`, `routes_assets.py`) + Strategy Engine (`backtester.py`, `risk_manager.py`, `mt5_connector.py`, `cli_history.py`).
2. **Testing & CI Parity:** Prior to opening a PR, run the full test suite (`pytest api_gateway/tests strategy_engine/tests tui/tests`) and ensure 100% green pass.
3. **GitHub Permissions:** Always run `C:\Users\rogal\workspaces\Set-GhToken-Antares.ps1` for Git push and `gh` operations under the `AntaresAndBharani` organization.
4. **CI/CD Lifecycle & Definition of Done:**
   - **PR Workflow:** Opening/updating a PR triggers the hard-gated Python CI workflow in `.github/workflows/build.yml`.
   - **Agent Completion Gate:** Development is only complete when local tests pass, all changes are committed, PR is opened, and remote CI checks pass (100% Green).

## Agentic SDLC Pipeline
The 5-node autonomous pipeline (Architect → Three Amigos → Dev & Test → PR Review → Merge & Backlog) runs across GitHub Actions and Antigravity Scheduled Tasks:

- **As PO, draft a User Story** with the `user-story.yml` issue template. Relabel `status:ready-for-architect` to hand off.
- **Label meanings:**
  - `status:definition` — PO drafting
  - `status:ready-for-architect` — PO says go; Architect decomposes into subtasks
  - `status:needs-po-input` — Architect / Dev escalation needing PO decision
  - `status:review` — Architect hands subtasks to Three Amigos for batch review
  - `status:needs-revision` / `status:needs-clarification` — Three Amigos feedback loop
  - `status:awaiting-approval` — Three Amigos internal clearance marker on subtasks
  - `status:ready` — Three Amigos auto-promotes story to ready; Dev & Test starts implementation
  - `status:done` — set automatically once all subtasks are closed; closes story
