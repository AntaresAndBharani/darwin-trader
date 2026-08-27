# Changelog

All notable changes to the Darwin Trader project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- **Default AccountConnectRequest.path to None with StrategyConfig Fallback**:
  - Changed `AccountConnectRequest.path` in `strategy_engine/models.py` (and Android `Models.kt`) to default to `None` instead of a hardcoded path.
  - Verified route fallback preserves configured `StrategyConfig.mt5_path` when `path` is omitted or `None`, while allowing explicit override.
  - Added unit and API tests in `strategy_engine/tests/test_strategy.py`, `api_gateway/tests/test_api.py`, and `ModelsTest.kt`.
- **ConnectionState Enum Typing on Account Connection Models**:
  - Typed `AccountConnectResponse.status` and `ConnectionStatus.status` as `ConnectionState` enum in `strategy_engine/models.py` to enforce strict validation against allowed states (`CONNECTED`, `DISCONNECTED`, `ERROR`).
  - Added unit test `test_connection_state_validation` in `strategy_engine/tests/test_strategy.py` verifying serialization and asserting `ValidationError` is raised for invalid status strings.

### Added
- **Explicit MT5 Path Teardown Fixture for Connect Tests**:
  - Added `preserve_mt5_path` fixture in `api_gateway/tests/conftest.py` that snapshots `global_config.mt5_path` and restores it in a teardown `finally` block.
  - Updated `test_account_connect_path_fallback_preserves_config` and `test_account_connect_explicit_path_overrides_config` in `api_gateway/tests/test_api.py` to use `preserve_mt5_path` explicitly.
- **StrategyConfig.reset_from Helper for Safe Fixture State Reset**:
  - Added `StrategyConfig.reset_from(other, **overrides)` in `strategy_engine/config.py` enabling bulk resets of live configuration singleton instances without manipulating private Pydantic internals (`__dict__`, `__pydantic_fields_set__`).
  - Refactored `api_gateway/tests/conftest.py` autouse isolation fixture to use `global_config.reset_from()`.
  - Added unit tests in `strategy_engine/tests/test_strategy.py` verifying field resets, default fallback, keyword overrides, and idempotency.
- **API Gateway Test Isolation Fixture & Deterministic Test Execution**:
  - Added `api_gateway/tests/conftest.py` with an autouse `reset_shared_state` fixture resetting `connector`, `global_config` singleton, and `current_status` before and after each test.
  - Added `pytest-randomly>=3.0.0` to `api_gateway/requirements.txt` to enforce order-independent and deterministic test execution across random seeds.
- **Thread Safety & Concurrency Locking for Shared Connector and Global Config Singleton**:
  - Introduced shared `_state_lock = threading.Lock()` in `api_gateway/routes_strategy.py` guarding `global_config` and `connector` singleton mutations and reads across endpoints.
  - Protected `connect_account`, `get_connection_status`, `get_account_info`, `get_positions`, and `get_darwinex_stats` in `api_gateway/routes_account.py` with `_state_lock` to ensure atomic state updates and prevent torn reads during concurrent requests.
  - Enhanced `MT5Connector` in `strategy_engine/mt5_connector.py` with an internal `threading.RLock()` guarding `initialize`, `disconnect`, `get_connection_status`, `get_account_info`, `get_open_positions`, `execute_order`, and `close_all_positions`.
  - Added concurrency test suites in `api_gateway/tests/test_api.py` (`test_concurrent_account_connect`, `test_concurrent_connect_and_status`) and `strategy_engine/tests/test_strategy.py` (`test_mt5_connector_concurrency`).
- **Android Dashboard Live Connection Telemetry Badge**:
  - Updated `DashboardScreen.kt` with live connection status badge (`Connected (Live)`, `Connected (Demo)`, `Simulation`, `Disconnected`) and Account ID display sourced from connection telemetry alongside strategy status.
  - Extended `MainActivity.kt` telemetry polling loop (`LaunchedEffect`) and tab-switch triggers to fetch `GET /api/v1/account/status` via `ApiService.getAccountStatus()` and propagate live status to `DashboardScreen`.
  - Added `getConnectionBadgeText()` helper extension on `AccountStatusResponse` in `Models.kt` mapping server mode, mock flag, and error status safely.
  - Added unit test suite in `ModelsTest.kt` testing connection badge label derivation across Live, Demo, Simulation, Disconnected, and Error states.
  - Updated `android/app/build.gradle.kts` snapshot flavor applicationId and added automatic local backend gateway launching in `scripts/run-e2e-tests.ps1` for end-to-end Maestro verification.
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
