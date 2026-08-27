# Changelog

All notable changes to the Darwin Trader project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Android Account Settings & Connection Screen**:
  - Added `AccountSettingsScreen.kt` Compose screen supporting MT5 login, password (with show/hide toggle), server selection, terminal path input, Mock/Live mode toggle, connection testing, and non-crashing troubleshooting guidance.
  - Added `AccountConnectRequest`, `AccountConnectResponse`, and `AccountStatusResponse` data models in `Models.kt`.
  - Added `connectAccount` and `getAccountStatus` suspend functions to `ApiService.kt`.
  - Integrated `Account` navigation tab and state synchronization into `MainActivity.kt`.
  - Added unit test suite `ModelsTest.kt` verifying serialization/deserialization across success and error response formats.
  - Extended Maestro E2E test flows (`04_navigation_flow.yaml`, `05_account_connection_flow.yaml`) and delta flow mapping.
- **Dynamic MT5 Account Connect & Status Endpoints**:
  - Added `POST /api/v1/account/connect` endpoint to configure MT5 credentials, toggle mock/live execution, and authenticate dynamically.
  - Added `GET /api/v1/account/status` endpoint reporting connection state (`CONNECTED`, `DISCONNECTED`, `ERROR`), server mode, latency measurement in milliseconds, and error diagnostics.
  - Extended `MT5Connector` with connection timestamping, latency calculation, disconnect capability, and comprehensive initialize/login error tracking.
  - Added Pydantic models `AccountConnectRequest`, `AccountConnectResponse`, `ConnectionState`, and `ConnectionStatus` in `strategy_engine/models.py`.
- **E2E Testing Framework with Maestro**:
  - Declarative E2E flows in `e2e/flows/` covering Dashboard metrics (`01_dashboard_flow.yaml`), Strategy parameters (`02_strategy_control_flow.yaml`), Backtest analytics (`03_backtest_analytics_flow.yaml`), and Navigation (`04_navigation_flow.yaml`).
  - Delta execution mapping (`e2e/flow-mapping.json`) mapping modified file globs across Android and Backend to targeted E2E tags.
  - Automated PowerShell test runner (`scripts/run-e2e-tests.ps1`) supporting `-Delta`, `-Tags`, `-CaptureArtifacts`, `-PushArtifacts`, auto-booting emulator, building snapshot APK, and generating summary reports.
  - Sticky PR evidence publisher (`scripts/post-e2e-evidence.ps1`) posting `<!-- e2e-evidence -->` markdown tables with pass/fail icons and screenshot links.
  - Unit test summarizer (`scripts/summarize-unit-tests.ps1`) parsing JUnit XML test results into sticky PR comments.
- **Agentic SDLC Pipeline (5-Node Graph & Local CLI Executor)**:
  - Antigravity scheduled tasks and local prompt templates (`.antigravity/tasks/dev-test.md`, `dev-test-implement.md`, `dev-test-fixup.md`, `three-amigos.md`, `backlog-triage.md`).
  - Claude CLI prompt templates in `.claude/tasks/` (`architect-decompose.md`, `architect-restructure.md`, `architect-answer-clarifications.md`, `pr-review.md`, `three-amigos-judge.md`).
  - Local CLI Pipeline wrapper scripts in `scripts/local-pipeline/`:
    - `run-backlog-triage.ps1`: Deterministic issue fetch/cluster/close with judgment-only `agy.exe` (Gemini 3.7 Flash Medium).
    - `run-pr-review.ps1`: Head-SHA tracked PR review with judgment-only `claude.exe` (Claude Sonnet 5, `--tools ""`, `--effort medium`).
    - `run-architect.ps1`: Multi-mode story decomposition with read-only `claude.exe` (Claude Sonnet 5 with Medium Effort, `--tools "Read,Grep,Glob"`, `--effort medium`).
    - `run-three-amigos-and-dev-test.ps1`: 5-step batch review, auto-rebase of approved conflicting PRs, agentic fix-up, in-flight concurrency gating, and new implementation.
    - `register-local-tasks.ps1`: Windows Task Scheduler registration for `DT-BacklogTriage`, `DT-PRReview`, `DT-Architect`, and `DT-ThreeAmigosDevTest`.
  - Scoped agent personas (`.antigravity/agents/developer.md`, `tester.md`) and workspace rules (`.antigravity/rules.md`).
  - SMART GitHub issue templates (`.github/ISSUE_TEMPLATE/user-story.yml`, `subtask.yml`, `config.yml`).
  - Automated GitHub Actions workflows (`architect.yml`, `three-amigos.yml`, `dev-test.yml`, `pr-review.yml`, `merge.yml`) and prompt files in `.github/workflows/prompts/`.
- **Project Configuration & Rules**:
  - Configured `.gitattributes` with `CHANGELOG.md merge=union` and line ending normalizations.
  - Updated `.gitignore` to ignore `logs/local-pipeline/`.
  - Created `GEMINI.md` defining development guidelines, quick commands, and Definition of Done.
  - Updated `README.md` with complete architecture, test commands, and pipeline documentation.
