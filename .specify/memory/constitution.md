# Darwin Trader Constitution

## Core Principles

### I. Clean Architecture & Pure Quantitative Core
Dependencies MUST point strictly inward from Presentation (`tui/`, `web/`, `api_gateway/`) through Data/Infrastructure (`mt5_connector.py`, `historical_db.py`, `yahoo_db.py`, `yahoo_fetcher.py`, `config.py`) to the Domain Core (`models.py`, `strategy_base.py`, `indicators.py`, `risk_manager.py`, `backtester.py`, `committee_calculator.py`).
- Domain models, risk rules, and technical indicators MUST remain pure Python with zero imports of `FastAPI`, `Uvicorn`, `Textual`, or `MetaTrader5`.
- Presentation clients (`tui/` and `web/`) MUST NOT instantiate broker/market-data SDKs (`MetaTrader5`, `yahooquery`) or query SQLite directly; all state transitions, market data queries, strategy backtests, and telemetry MUST flow through the FastAPI Gateway (`/api/v1/*` and `/ws/live`).
- Multi-timeframe indicator alignment (such as Weekly Heikin-Ashi aligned onto Daily bars or weekly/monthly OHLCV resampling) MUST enforce a strict zero-lookahead invariant so intra-period bars never observe unclosed higher-timeframe candles.
- *Rationale*: Isolating quantitative math and domain invariants from transport and external data I/O guarantees deterministic backtesting, zero lookahead bias, and effortless UI portability.

### II. Darwinex Zero Risk & Capital Preservation (NON-NEGOTIABLE)
Every live/broker trade signal and portfolio action MUST comply with Darwinex Zero institutional evaluation guardrails before reaching the MT5 execution layer.
- No live strategy signal may execute without passing `RiskManager.validate_signal()`, enforcing hard daily floating drawdown caps (`max_daily_drawdown_pct = 3.0%`), warning buffers (`drawdown_warning_pct = 2.5%`), maximum open position limits, and minimum free margin reserves (`>= 5%` of balance).
- Position queries, margin checks, drawdown calculations, and Emergency Kill-Switch liquidations MUST include all open positions across all symbols, including discretionary/manual trades (`magic == 0`).
- Client UIs MUST safeguard the Emergency Kill Switch with explicit confirmation when open positions exist, and pause the strategy without dispatching redundant order liquidations when zero positions are open.
- *Rationale*: Darwinex Zero enforces an uncompromising 3.0% daily drawdown boundary; bypassing pre-trade risk validation or ignoring manual positions risks immediate account disqualification.

### III. Zero-Click Operational Readiness & Scoped Client Evolution
The Terminal UI (`tui/`) and Web UI (`web/`) are first-class clients of the FastAPI Gateway and MUST share identical startup automation and broker connection defaults, while allowing analytical workspaces to evolve cleanly per client scope.
- Starting either client (`.\scripts\run-tui.ps1`, `.\scripts\run-web.ps1`, or `npm run web` / `npm run dev`) MUST automatically verify whether the FastAPI Gateway (`127.0.0.1:8000`) is online, spawn it in the background if not running, and cleanly terminate any self-spawned gateway process upon exit.
- On startup, the system MUST automatically connect to the configured live Darwinex MT5 environment (Account `4000073238`, Server `Darwinex-Live`, `mock_mode: false`) via passwordless Win32 IPC attachment to the running `terminal64.exe` instance, without blocking the operator behind a manual connection modal.
- Manual connection dialogs (`ConnectModal` in both TUI and Web) MUST share identical pinned defaults (`Login = 4000073238`, `Server = Darwinex-Live`, `Terminal Path = C:\Program Files\Darwinex MetaTrader 5\terminal64.exe`, optional password for IPC attach, and `Mock Mode = false`).
- Web-specific multi-tab workspaces (`Darwinex MT5`, `Yahoo Finance`, and `Strategy Lifecycle` in `web/`) MUST promote the Strategy Lifecycle experience to a dedicated full-screen workspace and remove the legacy `StrategySidebar` card from the Darwinex MT5 dashboard without breaking TUI workflows.
- *Rationale*: Operators require a single-command launch experience (`start server and start working`) free of repetitive credential entry, while enabling rapid iteration on rich full-screen web visualization and strategy evaluation workspaces.

### IV. Test-First & Platform-Independent Simulation (NON-NEGOTIABLE)
All backend, quantitative, TUI, and Web features MUST be verified by automated tests capable of running deterministically on headless CI runners without a physical Windows MetaTrader 5 installation or live external network dependencies.
- `MT5Connector` MUST maintain a platform-independent Mock Simulation Engine (`mock_mode = True` or when `MetaTrader5` Win32 bindings are absent) providing deterministic synthetic bars, virtual order tickets, and an 8-symbol catalog fixture.
- External market-data integrations (such as Yahoo Finance via `yahooquery` and external database migrations) MUST be injectable/mockable in unit and integration tests so CI suites run 100% offline and deterministically.
- Every feature or bug fix MUST include automated unit and integration tests covering Gherkin BDD acceptance scenarios across Python (`pytest api_gateway/tests strategy_engine/tests tui/tests`) and TypeScript (`npm test`, `npm run lint`, `npm run build` in `web/`).
- *Rationale*: Because proprietary broker terminals and live financial APIs are unavailable or rate-limited on headless CI runners, deterministic offline testability is mandatory for continuous integration and regression defense.

### V. Structured Concurrency, Lock Discipline & Observability
All shared runtime state, SQLite storage, and external I/O calls MUST be synchronized against race conditions, handle leaks, and event-loop starvation.
- FastAPI route mutations and background synchronization tasks MUST synchronize shared state via `_state_lock` (`threading.Lock`) and `MT5Connector._lock` (`threading.RLock`), extracting shallow snapshots (`list(cache.values())`) before iterating over cached catalogs.
- All SQLite storage engines (`HistoricalRatesDB` and `YahooFinanceDB`) MUST operate in `WAL` mode with explicit context-managed connection closure, `BEGIN IMMEDIATE` write transactions, and bounded exponential-backoff retries on `SQLITE_BUSY` / `SQLITE_LOCKED`.
- CLI tools (`strategy_engine.cli`) MUST route all logs and progress bars exclusively to `stderr` while keeping `stdout` strictly reserved for machine-readable output contracts (JSON/Markdown/summary lines).
- *Rationale*: Concurrent 1Hz WebSocket telemetry, multi-worker historical ingestion, and UI polling will corrupt state or leak Windows file handles (`WinError 32`) without strict lock and resource discipline.

### VI. Multi-Provider Data Isolation & Self-Contained Storage
Darwin Trader MUST support both broker-specific CFD telemetry (Darwinex MT5) and real-exchange historical price, metadata, fundamental datasets, and strategy backtesting (Yahoo Finance) in isolated, zero-server local databases.
- Darwinex MT5 historical bars MUST reside in `data/historical_rates.db` (`HistoricalRatesDB`), while Yahoo Finance tickers, daily OHLCV + quarterly earnings (`stock_prices`), and quarterly valuation multiples (`valuation_history`) MUST reside in a dedicated `data/yahoo_finance.db` (`YahooFinanceDB`).
- Strategy evaluations and historical backtests executed from the Web Strategy Lifecycle Control Panel MUST run strictly against Yahoo Finance data (`YahooFinanceDB`, supporting `D1`, `W1`, and `MN1` resampled series across single-asset or multi-asset/sector selections) and MUST NEVER query or mutate Darwinex Zero MT5 data or live broker positions.
- Runtime operation of Darwin Trader MUST NOT require an external PostgreSQL or Docker database server; external databases (such as legacy `fractanomicsdb`) are used strictly as one-time or on-demand migration sources into `data/yahoo_finance.db`.
- *Rationale*: Separating the multi-gigabyte MT5 tick/bar cache from Yahoo Finance exchange, fundamental, and strategy backtest datasets prevents SQLite write-lock contention, guarantees provider isolation, and ensures zero-dependency local execution.

## Architectural & Stack Constraints

- **Backend & Quantitative Engine**: Python 3.11+, FastAPI, Uvicorn, WebSockets, Pydantic v2 (`ConfigDict(extra="ignore")` and non-finite float sanitization), Pandas, NumPy, SQLite (`WITHOUT ROWID` clustered composite keys), `MetaTrader5`, and `yahooquery`.
- **Terminal Client (`tui/`)**: Python Textual and Rich with `httpx.AsyncClient` connection pooling and keyed differential table updates (`DataTable.update_cell`).
- **Web Client (`web/`)**: React 18, TypeScript, Vite, TailwindCSS, Axios, TradingView Lightweight Charts, and Vitest, proxying `/api` and `/ws` to `http://127.0.0.1:8000`.
- **Credential & Path Hygiene**: Passwords and private credentials MUST NEVER be committed to version control; environment variables (`MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_PATH`, `MOCK_MODE`, `PG_HOST`, `PG_PORT`, `PG_DB`, `PG_USER`, `PG_PASS`) and runtime payloads govern authentication.

## Development Workflow & Quality Gates

1. **Specification & Slicing Gate**: Features MUST be specified with clear Gherkin BDD Acceptance Criteria (`Given`/`When`/`Then`) and sized to maintain clean, reviewable diffs before implementation.
2. **Local Verification Gate**: Prior to opening or updating a Pull Request, all Python test suites (`pytest api_gateway/tests strategy_engine/tests tui/tests`) and Web checks (`npm test`, `npm run lint`, `npm run build` in `web/`) MUST pass 100% locally.
3. **Changelog & Documentation Maintenance**: Every user-facing or architectural change MUST be recorded under `## [Unreleased]` in `CHANGELOG.md` following the Keep a Changelog format, and architectural changes MUST synchronize with `.graph/architecture.md`.
4. **Remote CI, Automated PR Review & Auto-Merge Gate**:
   - Changes MUST be pushed on a feature branch (`feat/[task-summary]`) with a Pull Request verified against GitHub Actions CI (`.github/workflows/build.yml`) and Automated PR Review (`.github/workflows/pr-review.yml`).
   - `.github/workflows/pr-review.yml` MUST own the complete review-to-merge lifecycle (Claude Opus 5.5 High review, in-place `[skip pr-review]` auto-fix commit/push, idempotent `gh label create --force` label provisioning, follow-up backlog issue creation, strict `--commit "$CURRENT_SHA"` CI verification with an explicit `CI_PASSED="true"` gate, squash-merge, and post-merge parent-story closure) without competing secondary merge workflows.
   - Concurrency on `pr-review-<PR>` MUST set `cancel-in-progress: false` to prevent `[skip pr-review]` auto-fix pushes from self-cancelling active runs, and `steps.meta` MUST provide a zero-token `merge_only` fast-path for open PRs whose latest `[skip pr-review]` commit already has an `APPROVED` verdict comment.

## Governance

This Constitution is the supreme engineering governance document for Darwin Trader and supersedes conflicting ad-hoc practices across all human and autonomous agent workflows (`GEMINI.md`, `.graph/architecture.md`, and Spec Kit pipelines).
- **Amendment Procedure**: Any amendment to this Constitution MUST be made via `.specify/memory/constitution.md`, accompanied by a Sync Impact Report, rationale for version increment, and synchronization with `GEMINI.md` and `.graph/architecture.md` if stack or workflow rules change.
- **Versioning Policy**: This Constitution follows Semantic Versioning (`MAJOR.MINOR.PATCH`):
  - `MAJOR`: Backward-incompatible principle removals or governance redefinitions.
  - `MINOR`: Addition of a new core principle, section, or materially expanded architectural constraint.
  - `PATCH`: Wording clarifications, typo fixes, or non-semantic refinements.
- **Compliance Review**: Every specification (`/speckit-specify`), implementation plan (`/speckit-plan`), task breakdown (`/speckit-tasks`), and code review MUST verify compliance with the 6 Core Principles defined herein.

**Version**: 1.3.0 | **Ratified**: 2026-10-22 | **Last Amended**: 2026-10-23
