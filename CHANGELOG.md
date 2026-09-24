# Changelog

All notable changes to the Darwin Trader project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Resilient High-Concurrency SQLite Ingestion & Fault-Isolated Batch Sync (Issue #118)**:
  - Implemented `@contextmanager def _connection(self)` in `strategy_engine/historical_db.py` with `isolation_level=None`, `row_factory = sqlite3.Row`, `PRAGMA synchronous=NORMAL`, `PRAGMA busy_timeout = {self.busy_timeout};`, `PRAGMA wal_autocheckpoint=10000;`, and guaranteed connection closure in `finally`, eliminating Windows file handle leaks (`WinError 32`).
  - Refactored `insert_rates` and `clear_rates` to acquire write locks with explicit `BEGIN IMMEDIATE;`, commit via `COMMIT;`, and retry up to 5 times with exponential backoff and randomized jitter on `SQLITE_BUSY`/`SQLITE_LOCKED` contentions, logging attempts at `DEBUG` level.
  - Ensured all storage read methods (`get_latest_timestamp`, `get_total_bars`, `get_rates`) and database initialization utilize `_connection()`, maintaining 100% backward compatibility for all public method signatures and row access contracts.
  - Implemented per-symbol fault isolation in `MT5Connector.sync_historical_batch` by wrapping worker timeframe execution in `try/except Exception as exc:`, logging debug tracebacks, capturing `sym_failed`, and recording failure reasons without aborting `asyncio.gather()`.
  - Added comprehensive automated test suite covering Gherkin Scenarios 1–7 in `strategy_engine/tests/test_historical_db.py` and `strategy_engine/tests/test_cli_history.py` (mixed reader/writer concurrency at 30 workers, guaranteed connection closure, transaction retry state, fast-failing lock retry within 3s, batch fault isolation, and 30-worker end-to-end batch ingestion).

- **Comprehensive CLI Logging & Progress Observability (Issue #116)**:
  - Added `rich>=13.0.0` dependency to `strategy_engine/requirements.txt` for ANSI terminal rendering.
  - Implemented `_sync_historical_rates_detailed` in `strategy_engine/mt5_connector.py` returning `(bars, count, error_reason)` while preserving the public 2-tuple `sync_historical_rates` and `List[HistoricalBar] | None` `get_historical_rates` interfaces.
  - Augmented `MT5Connector.sync_historical_batch` with `progress_callback` telemetry, stopwatch starting post-semaphore acquisition, local per-worker failure reason isolation without reading shared `connector.last_error`, and defensive try/except callback execution.
  - Implemented `setup_cli_logging` in `strategy_engine/cli.py` configuring `"strategy_engine"` logger idempotently writing to `stderr` with `propagate=False`, `[WARN]` formatting, and automatic handler cleanup across sequential invocations.
  - Added shared parent parser with `default=argparse.SUPPRESS` for `-v`/`--verbose` (DEBUG) and `-q`/`--quiet` (WARNING) across all subcommands (`sync-history`, `purge-history`, `committee`) with fail-fast mutual exclusion exiting with code 2.
  - Implemented dual-mode progress engine rendering Rich animated progress on `stderr` during interactive TTY sessions (or `--force-terminal`) and deterministic 10% decile milestone logging on `stderr` during headless non-interactive runs, while preserving stdout contract purity.
  - Added audit telemetry to `purge-history` on `stderr` tracking database path, target symbol, timeframe, and duration.
  - Added comprehensive automated test suite `TestCliLoggingAndObservability` in `strategy_engine/tests/test_cli_history.py` covering Gherkin Scenarios 1–8.

- **TUI Asset Explorer Metrics Drawer & Debounced Interaction (Issue #111, Parent #108)**:
  - Added consolidated `AssetMetricsResponse` model and updated `get_asset_metrics` in `tui/api_client.py` for asynchronous retrieval of institutional microstructure, volatility, and Kalman dynamic beta metrics.
  - Implemented collapsible metrics drawer enhancements in `tui/screens/asset_explorer_modal.py` with `[I]` toggle, amber degradation badges for uncached/insufficient benchmark states, synchronous loading label, 150ms debouncing, and stale response discard token guard.
  - Added widget test suite in `tui/tests/test_asset_explorer_metrics.py` covering Gherkin Scenario 7 state synchronization, debouncing, Dynamic Kalman Beta & OLS Beta rendering, amber degradation badges, and stale token discard.

- **Gateway Metrics Route & Committee Calculator Integration (Issue #110, Parent #108)**:
  - Updated `strategy_engine/committee_calculator.py` to hoist single SPY benchmark fetch in `calculate()`, accept optional pre-fetched `benchmark_bars` in `compute_benchmark_beta`, deduplicate telemetry `data_flags`, and populate lean Kalman scalars (`kalman_beta`, `kalman_alpha`, `kalman_trend`) in `CommitteeContext`.
  - Updated `GET /api/v1/assets/{symbol}/metrics` in `api_gateway/routes_assets.py` to compute and return consolidated `AssetMetricsResponse` including Kalman dynamic beta, OLS beta, relative strength, common overlap bar count, beta trajectory, and deduplicated telemetry data flags while preserving all microstructure metrics.
  - Added unit and integration tests in `strategy_engine/tests/test_committee_calculator.py` and `api_gateway/tests/test_assets.py` covering Gherkin Scenario 3 (zero network call uncached benchmark invariant) and Scenario 8 (route contract, field completeness, and route precedence), and asserting telemetry flag deduplication.

- **Core Mathematical State-Space Engine & Input Sanitization (Issue #109, Parent #108)**:
  - Implemented `compute_kalman_dynamic_beta` in `strategy_engine/indicators.py` with fast float Joseph-stabilized covariance recursion ($[\alpha_t, \beta_t]^T$) for zero-lag adaptive systematic risk tracking without matrix inversion overhead.
  - Added symmetric price input validation ($P_t > 0$ and `math.isfinite`) returning `[DATA_CORRUPT: NON_POSITIVE_PRICES]`, uncached benchmark detection emitting `[BENCHMARK: UNCACHED (STANDALONE REGIME)]`, and $<20$ common timestamp overlap guard emitting `[BENCHMARK: INSUFFICIENT_OVERLAP]`.
  - Added 20-bar beta displacement trend classification (`kalman_trend`: `EXPANDING`, `CONTRACTING`, `STABLE`) guarded by $N \ge 21$.
  - Added `KalmanBetaResult` and `AssetMetricsResponse` data models in `strategy_engine/models.py`, and enriched `CommitteeContext` with lean `kalman_beta`, `kalman_alpha`, and `kalman_trend` scalar fields.
  - Added unit and BDD acceptance test suite in `strategy_engine/tests/test_kalman_beta.py` covering Scenarios 1 (deterministic convergence), 2 (regime adaptation on jump), 3 (uncached benchmark), 4 (insufficient overlap), 5 (symmetrical corrupt/non-positive price guard), 6 (flat benchmark), and `kalman_trend` state transitions.

- **TUI Asset Explorer Institutional Drawer & Keyboard Binding (Issue #106, Parent #104)**:
  - Added async method `get_asset_metrics(symbol)` to `DarwinApiClient` in `tui/api_client.py` querying `GET /api/v1/assets/{symbol}/metrics`, returning `InstitutionalMetrics` on HTTP 200, and `None` on HTTP 404 (unsynced asset) or network failure.
  - Added collapsible `#institutional-metrics-drawer` container (fixed height 4) to `AssetExplorerModal` in `tui/screens/asset_explorer_modal.py`, styled with dedicated header and content widgets.
  - Implemented keyboard bindings `"i"` and `"I"` to toggle the metrics drawer open/closed when the asset table is focused, with search input isolation preventing accidental toggles while typing.
  - Implemented `self._metrics_request_symbol` race-condition token guard ensuring out-of-order or delayed responses from previous row selections are safely discarded during fast keyboard navigation.
  - Added 150ms debounced metrics fetch on `DataTable.RowHighlighted` when the drawer is open, preventing gateway request flooding while navigating.
  - Implemented graceful UI rendering across loading states (`Loading institutional metrics for {symbol}...`), unsynced 404 states (`No local rates synced for {symbol}. Press [H] to view/sync history.`), insufficient data states (`< 21` bars), and verified metrics with rich formatting.
  - Updated footer help hint bar with `[I] Metrics` and added pilot acceptance tests in `tui/tests/test_tui.py` covering Gherkin Scenarios 10–11, cold-start unsynced states, insufficient data states, and search input isolation.

- **Pure Calculation Engine & Fast Gateway Route for Institutional Metrics (Issue #105, Parent #104)**:
  - Implemented pure mathematical calculation engine in `strategy_engine/indicators.py` containing `compute_yang_zhang_volatility`, `compute_amihud_illiquidity`, `compute_vwap_and_bands`, and `compute_roll_spread` with automatic ascending chronological ordering (`time ASC`) normalization and zero-division / zero-$\sigma$ boundary guards.
  - Added `InstitutionalMetrics` Pydantic model in `strategy_engine/models.py` with model-level non-finite float validation sanitizing `NaN` and `Inf` to `None`.
  - Implemented `GET /api/v1/assets/{symbol}/metrics` in `api_gateway/routes_assets.py` reading strictly from local `HistoricalRatesDB` with `descending=True` to fetch latest bars, reversing to chronological order, with HTTP 404 (unsynced asset) and HTTP 200 (`insufficient_data=True`) handling without external MT5 network calls.
  - Added unit test suite in `strategy_engine/tests/test_indicators.py` covering Gherkin acceptance criteria Scenarios 1–6, analytical benchmarks, degenerate cases, and $< 50$ ms performance budget.
  - Added route integration tests in `api_gateway/tests/test_assets.py` covering Scenarios 7–9, zero-volume and flat-market non-crashing contracts, and timeframe validation.

- **Hierarchical Category Filters & Split Columns in Asset Explorer (Issue #101)**:
  - Implemented `parse_category_parts(category, symbol)` parsing hierarchical paths into distinct Class, Region, and Exchange tuples, stripping trailing symbol names case-insensitively, normalizing empty segments to `"--"`, and preserving exact source casing (e.g. `ETFs`).
  - Replaced single category dropdown with a 3-tier cascading filter bar (`#select-class`, `#select-region`, `#select-exchange`) where Region and Exchange are dynamically populated and enabled based on parent selection, resetting child options and values cleanly on parent changes.
  - Split single `Category` column in `AssetExplorerModal`'s `DataTable` into separate `Class`, `Region`, and `Exchange` columns alongside `Symbol`, `Description`, `CCY`, `Min Lot`, `Max Lot`, `Bid`, and `Ask` (10 columns).
  - Implemented real-time client-side in-memory multi-predicate filtering matching on Symbol and Description case-insensitively with formatted status reporting (`Showing {visible} of {total} assets matching [{hierarchy} | "{search}"]`).
  - Added `F4` hotkey and `#btn-reset-filters` button to reset all category and search filters to defaults, or trigger a full catalog retry reload if the initial load failed.
  - Added Enter keybinding on `#asset-search-input` (`Input.Submitted`) to shift focus directly to the `DataTable`.
  - Added comprehensive automated acceptance test suite covering all 6 Gherkin BDD scenarios in `tui/tests/test_tui.py`.

- **Pipeline, Workflow, Agent Governance, Prompts & Documentation Alignment (Issue #99, Parent #97)**:
  - Cleaned `api_gateway/main.py` docstrings and CORS comments to reference Terminal UI and Web clients rather than Android Mobile App.
  - Modernized `README.md`, `GEMINI.md`, and `.graph/architecture.md` to reflect the pure Python Textual TUI, FastAPI Gateway, and MetaTrader 5 Strategy Engine architecture, dropping obsolete mobile build/test instructions.
  - Cleaned `.gitignore` by removing legacy Android, Gradle, and keystore ignore rules.
  - Aligned Antigravity rules and agent personas (`.antigravity/rules.md`, `.antigravity/agents/{developer,tester}.md`, `.antigravity/tasks/{backlog-triage,dev-test-fixup,dev-test-implement,dev-test,three-amigos}.md`) to focus strictly on pure Python development and pytest execution across `api_gateway/tests`, `strategy_engine/tests`, and `tui/tests`.
  - Aligned CI workflow prompts in `.github/workflows/prompts/` (`dev-test-implement.md`, `dev-test-fixup.md`, `architect-decompose.md`, `pr-review.md`, `three-amigos.md`) and Claude tasks in `.claude/tasks/` (`architect-decompose.md`, `architect-restructure.md`, `pr-review.md`, `three-amigos-judge.md`).
  - Refactored GitHub issue templates in `.github/ISSUE_TEMPLATE/` (`subtask.yml`, `user-story.yml`) to use TUI and pytest verification placeholders.
  - Added comprehensive automated acceptance test suite in `strategy_engine/tests/test_pipeline_governance_alignment.py` verifying all Gherkin acceptance criteria (Scenarios 2-7) and zero dangling mobile references.

### Removed
- **Android Codebase & Legacy Mobile Scripts Decommissioning (Issue #98, Parent #97)**:
  - Removed entire Android client application source code, Gradle build system, and JUnit test suites under `android/`.
  - Removed Maestro E2E test flows, test mapping, and flow configurations under `e2e/`.
  - Removed local test build and APK summary directory `local_test/`.
  - Removed obsolete mobile test automation scripts `scripts/run-e2e-tests.ps1`, `scripts/post-e2e-evidence.ps1`, and `scripts/summarize-unit-tests.ps1`.
  - Removed obsolete Android production release workflow `.github/workflows/release.yml`.
  - Added acceptance criteria test suite in `strategy_engine/tests/test_mobile_decommission.py`.
### Changed
- **CI Workflow & Local Pipeline Streamlining (Issue #98, PR #100)**:
  - Streamlined `.github/workflows/build.yml` to execute Python backend and TUI test suites under Python 3.11 with hard gating, removing legacy Gradle and Android build steps while preserving job name `build` for branch protection.
  - Purged obsolete `Set up JDK 17` step from `.github/workflows/dev-test.yml`.
  - Updated `scripts/local-pipeline/run-three-amigos-and-dev-test.ps1` to run backend and TUI pytest suites (`api_gateway/tests`, `strategy_engine/tests`, `tui/tests`) without invoking deleted Gradle wrapper.

### Fixed
- **TUI HistoricalDataModal Layout Flex Alignment**:
  - Added explicit `width: auto` to `.control-label`, `#btn-fresh-restart`, `#simulation-badge`, and `#footer-status` in `tui/screens/historical_data_modal.py` to prevent flex layout collapse in Textual when `#footer-status` is empty.

### Added
- **Granular History Purge Command & Safety Guards (Issue #94, Parent #92)**:
  - Enhanced `HistoricalRatesDB.clear_rates` in `strategy_engine/historical_db.py` to support dual single/multi-symbol signatures (`symbol` and `symbols`), canonical `'ALL'` timeframe normalization (omitting timeframe clause without literal mismatch), connection-setup hygiene by moving `PRAGMA journal_mode=WAL;` to `_init_db()`, and returning total deleted row count.
  - Implemented `purge-history` CLI subcommand in `strategy_engine/cli.py` (`python -m strategy_engine.cli purge-history`) with `--symbol`, `--category`, `--timeframe` (default `'all'`), `--all`, `-y`/`--yes`, and `--db-path` flags.
  - Added fail-safe validation aborting with exit code 1 if no target (`--symbol`, `--category`, or `--all`) or empty/whitespace-only symbols are provided.
  - Added non-interactive headless confirmation guard failing fast with exit code 1 when stdin is not a TTY without `-y`/`--yes`.
  - Added interactive confirmation prompt with safe user cancellation exiting with code 0 (`"Operation cancelled by user."`) leaving database records untouched.
  - Added comprehensive test suite `TestCliHistoryGranularPurge` in `strategy_engine/tests/test_cli_history.py` covering Gherkin acceptance criteria (Scenarios 3, 4, 5, 6, 10, 11), granular timeframe purging, category-wide purging, safety guards, interactive confirmation/cancellation, and WAL pragma hygiene.

- **Parallel Batch Sync & Multi-Symbol Worker Pool (Issue #93, Parent #92)**:
  - Augmented `StrategyConfig` in `strategy_engine/config.py` with environment-driven `mock_mode` resolution from `MOCK_MODE` (defaulting to true).
  - Updated `HistoricalSyncStatus` in `strategy_engine/models.py` with `failed_symbols: List[str]` and `total_bars: int`, maintaining backward-compatible lockstep synchronization with `failed_assets`.
  - Upgraded `MT5Connector.sync_historical_batch` in `strategy_engine/mt5_connector.py` to support bounded concurrency via `asyncio.Semaphore(workers)` (range 1-50, default 10), dual-keyword timeframe signatures (`timeframe` / `timeframes`), canonical 9-timeframe expansion for `'all'`, and fast-fail delisted instrument short-circuiting on first timeframe failure.
  - Refactored `handle_sync_history` in `strategy_engine/cli.py` to route all sync requests unconditionally through the unified batch worker pool, adding input normalization for comma-separated/repeated symbols, fast-fail validation on empty symbols (`" , "`) and worker boundaries (`1 <= workers <= 50`), mutually exclusive `--live`/`--mock` flag group, and deterministic exit code contracts (`0` all ok, `1` fatal/all failed, `2` partial failure).
  - Added comprehensive unit test suite in `strategy_engine/tests/test_cli_history.py` covering Gherkin acceptance criteria for parallel multi-symbol sync, `--timeframe all` expansion, partial failure exit code 2, worker range validation, delisted symbol fast-fail, mutually exclusive mode flags, and keyword regression safety.

- **CLI Subcommand & Trading Committee Workspace Skill (Issue #85, Parent #83)**:
  - Added CLI `committee` subcommand in `strategy_engine/cli.py` (`python -m strategy_engine.cli committee <SYMBOL>`) supporting `--mode` (`entry`/`exit`), `--direction` (`long`/`short`), `--entry-price`, `--format` (`markdown`/`json`), `--benchmark`, and `--db-path`.
  - Implemented fail-closed error handling catching `HistoricalDataNotFoundError` for cold-start un-cached assets, advising the operator to execute `python -m strategy_engine.cli sync-history --symbol <SYMBOL>`.
  - Implemented deterministic `Technical Context Briefing` markdown formatting strictly separated from LLM wave narrative and consensus score.
  - Created Antigravity workspace skill `.agents/skills/trading-committee/SKILL.md` powered by Gemini 3.8 Flash (High), featuring a 4-persona deliberation panel (Regime Follower, Price Action Specialist, Wave Analyst, and Chief Risk Officer), a 4-stage workflow, a 3-round dispute resolution cap, and standardized Committee Trading Card output.
  - Added CLI integration test suite in `strategy_engine/tests/test_committee_cli.py` covering Gherkin acceptance criteria (help display, missing symbol, cold-start handling, JSON output validation against Pydantic schema, markdown format and strict briefing boundary verification, optional and positional arguments, H1 bar volume profiling, custom benchmarks, short-history degraded regime, and staleness detection).

- **Deterministic Technical Calculator & Domain Models (Issue #84)**:
  - Added Pydantic schemas in `strategy_engine/models.py`: `TradeAction` enum (`ENTER`, `WAIT`, `EXIT`, `SCALE_OUT`, `PASS`), `MarketRegime` enum (`STAGE_1_ACCUMULATION`, `STAGE_2_MARKUP`, `STAGE_3_DISTRIBUTION`, `STAGE_4_DECLINE`, `CHOPPY`), `CommitteeVerdict` (with optional non-actionable fields and `to_trade_signal()` helper), `CommitteeContext`, and fail-closed `HistoricalDataNotFoundError`.
  - Implemented pure deterministic technical calculator in `strategy_engine/committee_calculator.py` with zero network and MT5 imports.
  - Added recency fetch logic querying `get_rates(limit=250, descending=True)` with reverse sorting (`list(reversed(raw_bars))`) to guarantee chronological ascending order (`time ASC`) ending at the absolute latest bar recorded in SQLite.
  - Implemented rolling EMAs (20, 50, 200) with short-history fallback (`ema_200 = None`) and `[REGIME: SHORT_HISTORY_DEGRADED]` data flag for assets with $< 200$ bars.
  - Implemented Wilder's RSI(14) and ATR(14) calculations.
  - Added swing pivot detection with parameterized rolling extrema ($k=5$ bars left/right) and swing ceiling/floor identification.
  - Implemented 60-bar lookback dominant Fibonacci anchor grid with retracements (0.236..0.786) and extensions (1.272, 1.618).
  - Added vectorized 50-bin Typical Price `(H+L+C)/3` Volume Profile weighted by `tick_volume` on H1 bars (VPOC, HVN, LVN) with zero-volume fallback.
  - Implemented SPY benchmark beta calculation via daily timestamp inner-join with $< 20$ overlap guard (`[BENCHMARK: INSUFFICIENT_OVERLAP]`), uncached benchmark detection (`[BENCHMARK: UNCACHED (STANDALONE REGIME)]`), and data staleness detection (`[DATA_STALE]` for bars older than 5 trading days).
  - Added comprehensive test suite in `strategy_engine/tests/test_committee_calculator.py` covering Gherkin BDD Scenarios 1, 6, 7, 8, indicator helpers, and domain models.

- **TUI Historical DataTable Inspector & Fresh Restart Modal (Issue #82, #76)**:
  - Created `HistoricalDataModal` in `tui/screens/historical_data_modal.py` providing interactive historical OHLCV bar inspection with self-contained `DataTable`, timeframe filtering, and 500-bar viewport pagination.
  - Implemented keyboard bindings for dataset pagination (`]` / `PgDn` next page, `[` / `PgUp` previous page) with safe boundary handling (no-op on Page 1 underrun, `[End of history]` indicator on last page overrun) and dynamic page orientation (`Page X of Y`).
  - Added symbol-scoped fresh restart action (`F5` and button) submitting scoped background synchronization requests (`POST /api/v1/assets/history/sync?symbol={symbol}&fresh=true`) with in-place progress banner, client-side debouncing, polling status failure handling, and automatic `DataTable` reload upon completion.
  - Implemented HTTP 409 Conflict handling toast ("Sync already in progress; please wait for completion") and disconnected/mock mode telemetry indicator (`[SIMULATION HISTORY]` badge).
  - Integrated `HistoricalDataModal` into `AssetExplorerModal` (`tui/screens/asset_explorer_modal.py`) via `H` hotkey, `Enter` row selection, and "Inspect History" button.
  - Exported `HistoricalDataModal` in `tui/screens/__init__.py`.
  - Added comprehensive pilot and unit test suite in `tui/tests/test_tui.py` covering Gherkin BDD Scenarios 4 through 7 (modal invocation, 500-bar pagination navigation and boundary clamping, scoped fresh restart action, simulation history badge, 409 conflict toast, timeframe filtering, error banner handling, and modal dismissal).

- **CLI Ingestion Tool & FastAPI Background Sync Router (Issue #81, #75)**:
  - Created non-interactive CLI utility `sync-history` in `strategy_engine/cli.py` supporting `--symbol`, `--category`, `--timeframe`, and `--fresh` flags with robust error handling and execution reporting.
  - Implemented background synchronization router endpoints in `api_gateway/routes_assets.py` with strict route ordering preceding dynamic `/{symbol}`: `POST /api/v1/assets/history/sync`, `GET /api/v1/assets/history/sync/status`, and paginated read endpoint `GET /api/v1/assets/{symbol}/history`.
  - Added single-active-job mutex guard returning `HTTP 409 Conflict` with `{"detail": "Sync job already in progress", "current_job_id": "...", "status": "IN_PROGRESS"}` on overlapping synchronization triggers.
  - Implemented decoupled background worker with 25ms yield sleep, tracking `completed_assets`, `failed_assets`, `total_assets`, and `current_symbol` telemetry with non-fatal delisted symbol fault tolerance.
  - Expanded `DarwinApiClient` in `tui/api_client.py` with asynchronous historical methods (`sync_historical_rates`, `get_sync_status`, `get_historical_rates`) equipped with a dedicated 15.0-second timeout and offline resilience.
  - Added comprehensive test suite in `api_gateway/tests/test_assets.py` validating background synchronization telemetry, HTTP 409 conflict rejection, paginated reads, scoped re-sync, route ordering disambiguation, SDK methods, and CLI command execution.

- **SQLite Storage Layer, Models, .gitignore & MT5 Historical Connector (Issue #80, #74)**:
  - Created `HistoricalRatesDB` in `strategy_engine/historical_db.py` operating in SQLite WAL mode with 60-second busy timeout (`PRAGMA busy_timeout = 60000;`), automatic `data/` directory initialization, and composite primary key `(symbol, timeframe, time DESC) WITHOUT ROWID` guaranteeing clustered range seek performance.
  - Implemented `INSERT OR REPLACE` upsert semantics to cleanly update forming daily bars with finalized OHLCV data on subsequent synchronizations without duplicate row creation or key collisions.
  - Added indexed pagination `get_rates(symbol, timeframe, limit=500, offset=0)` returning `(bars, total_bars)` with safe boundary handling for underrun and overrun requests.
  - Added Pydantic data models in `strategy_engine/models.py`: `Timeframe` enum, `TIMEFRAME_TO_MT5` mapping dictionary, `HistoricalBar`, `HistoricalRatesRequest`, `HistoricalRatesResponse`, `HistoricalSyncStatus`, and `HistoricalSyncResponse`.
  - Added historical rate extraction methods in `strategy_engine/mt5_connector.py`: `get_historical_rates()` with `mt5.symbol_select(symbol, True)`, decoupled fine-grained Win32 IPC locking, non-fatal skip on `None` for delisted assets incrementing `failed_assets`, `sync_historical_rates()`, and async batch synchronization `sync_historical_batch()` with 25ms yield (`asyncio.sleep(0.025)`).
  - Implemented deterministic pseudo-random historical bar mock generator seeded by symbol MD5 hash for headless CI reliability.
  - Excluded `data/` and `*.db*` in `.gitignore` to prevent accidental database commits.
  - Added comprehensive test suite in `strategy_engine/tests/test_historical_db.py` validating composite PK collision safety, forming candle upsert, pagination, WAL pragmas, mock determinism, delisted symbol handling, and Market Watch symbol selection.

### Fixed
- **Multi-Symbol & Discretionary Positions Retrieval in MT5Connector**:
  - Broadened `MT5Connector.get_open_positions(symbol=None)` in `strategy_engine/mt5_connector.py` to retrieve all open positions across all traded symbols and asset classes (stocks, forex, indices) when `symbol` is omitted.
  - Removed strict `pos.magic == self.config.magic_number` filter so manual and discretionary positions (`magic == 0`) opened in the terminal are populated in the TUI positions table and account telemetry.
  - Extracted MT5 position timestamp into `open_time` with UTC fallback and captured `pos.swap`.
  - Added unit test in `strategy_engine/tests/test_strategy.py` verifying multi-symbol position retrieval, magic 0 handling, and symbol-specific filtering.

### Added
- **Interactive TUI Asset Explorer Modal**:
  - Implemented `AssetExplorerModal` in `tui/screens/asset_explorer_modal.py` enabling full-screen catalog discovery, real-time substring search across tickers and descriptions, category switching (`stocks`, `etfs`, `forex`, `all`), and live contract specification inspection (`lot_min`, `lot_max`, `bid`, `ask`).
  - Exported `AssetExplorerModal` in `tui/screens/__init__.py`.
  - Added dual keybindings `A` and `F3` to `DarwinTraderApp.BINDINGS` in `tui/app.py` with action handler `action_open_asset_explorer` and Footer visibility.
  - Added comprehensive Textual pilot and unit test suite in `tui/tests/test_tui.py` covering modal invocation, catalog display, real-time search filtering, category switching, offline error fallback banner, and dismissal via `Escape` or `Close` button.

- **FastAPI Asset Router, Gateway Mounting, Client SDK & Integration Tests (Issue #69)**:
  - Created dedicated FastAPI asset router in `api_gateway/routes_assets.py` mounted at `/api/v1/assets` with category and substring search query parameters.
  - Implemented strict error handling contracts: HTTP 400 Bad Request for unsupported categories, HTTP 404 Not Found for missing asset tickers, and HTTP 503 Service Unavailable when MetaTrader 5 gateway is disconnected.
  - Mounted asset router onto main FastAPI application in `api_gateway/main.py`.
  - Added asynchronous client SDK methods `get_assets(category, search)` and `get_asset_info(symbol)` to `DarwinApiClient` in `tui/api_client.py` with safe offline fallback handling.
  - Added comprehensive integration test suite in `api_gateway/tests/test_assets.py` covering Gherkin BDD scenarios 1 through 6, live MT5 catalog retrieval, mock mode isolation, and client SDK offline resilience.

- **Strategy Engine Models, Thread-Safe Connector & Unit Tests (Issue #68)**:
  - Defined `AssetCategory` enum (`all`, `stocks`, `etfs`, `forex`) and `AssetInfo` model in `strategy_engine/models.py` capturing full contract specifications (`lot_min`, `lot_max`, `lot_step`, `digits`, `point`, `filling_mode`, `trade_mode`) with optional `bid` and `ask` live quotes.
  - Implemented thread-safe `MT5Connector.get_available_assets()` using double-checked locking with shallow snapshots (`list(self._symbols_cache.values())`) under `self._lock`, preventing `RuntimeError: dictionary changed size during iteration` during concurrent reads and cache invalidations.
  - Added category prefix filtering, case-insensitive substring search across tickers and company names, and error contracts for unsupported categories.
  - Implemented single-asset contract specifications lookup `MT5Connector.get_asset_info()` with graceful degradation of `bid` and `ask` to `None` during closed market conditions or weekends.
  - Implemented immediate in-memory cache invalidation on account switching in `MT5Connector.initialize()` and `disconnect()`.
  - Added deterministic 8-symbol mock fixture (`AMZN`, `NVDA`, `MSFT`, `PM`, `AAPL`, `SPY`, `QQQ`, `EURUSD`) for headless CI test environments.
  - Added comprehensive unit and concurrency test suite in `strategy_engine/tests/test_assets_connector.py` covering Gherkin scenarios 1 through 7.

- **DarwinX Zero Drawdown Monitoring & Comprehensive Test Suite (Issue #63)**:
  - Rendered DarwinX Zero 3.0% maximum daily drawdown limit alongside active floating drawdown percentage in `StrategyPanel` (`tui/widgets/strategy_panel.py`).
  - Implemented real-time status badging in `StrategyPanel`: green `[● SAFE]` badge for drawdown below 2.0%, amber `[⚠ WARNING]` badge for drawdown reaching or exceeding the 2.5% buffer threshold (`drawdown_warning_pct`), and `[⛔ BREACH]` badge for drawdown reaching or exceeding the 3.0% hard limit.
  - Implemented unit and Textual pilot tests in `tui/tests/test_tui.py` providing complete BDD acceptance test coverage across all 6 Gherkin scenarios defined in parent Issue #60:
    - Scenario 1: Automatic Detection of Darwinex MT5 Installation (`test_connect_modal_autodetection_and_account_pinning_terminal_exists`).
    - Scenario 2: Live MT5 IPC Connection for Account 4000073238 on Darwinex-Live (`test_live_mt5_ipc_connection_account_4000073238_scenario_2`).
    - Scenario 3: Attach to Already-Running MT5 Terminal Instance Without Password (`test_mt5_attach_to_running_terminal_without_password_scenario_3`).
    - Scenario 4: Terminal Error Diagnostic Mapping (`test_terminal_error_diagnostic_mapping_scenario_4`).
    - Scenario 5: Darwinex Zero Risk Limits Visibility & Buffer Warning (`test_darwinex_zero_risk_limits_and_buffer_warning_scenario_5`).
    - Scenario 6: Graceful Mock Fallback on Non-Windows or Missing Dependency (`test_graceful_mock_fallback_non_windows_or_missing_dep_scenario_6`).

- **TUI Connect Modal Auto-Detection & Account Pinning (Issue #62)**:
  - Pre-populated default terminal path in `ConnectModal` to `C:\Program Files\Darwinex MetaTrader 5\terminal64.exe`.
  - Pre-filled default login to `4000073238` and default server to `Darwinex-Live`.
  - Added auto-detection for MetaTrader 5 terminal executable binary: unchecks `Mock Mode` by default when the terminal binary exists on the host workstation, and defaults to checked when missing.
  - Added unit and Textual pilot tests in `tui/tests/test_tui.py` validating pre-population, auto-detection toggle behavior, and submission with pinned defaults.

- **MetaTrader5 Dependency & Live IPC Connector Hardening (Issue #61)**:
  - Installed `MetaTrader5` on Windows environment and verified live terminal connectivity.
  - Implemented `MT5_ERROR_MESSAGES` dictionary and `format_mt5_error()` in `strategy_engine/mt5_connector.py` for comprehensive human-readable error diagnostics across IPC, authentication, and timeout failure modes.
  - Hardened `MT5Connector.initialize()` to support seamless attach-to-running-instance without requiring password re-entry when an active MT5 terminal session is running.
  - Added configurable `drawdown_warning_pct = 2.5` to `StrategyConfig` to establish a 0.5% safety buffer before the hard 3.0% DarwinX Zero daily limit.
  - Added comprehensive unit tests in `strategy_engine/tests/test_strategy.py` covering error message mapping, attach-to-running-instance IPC path, and drawdown warning threshold.

### Changed
- **Default AccountConnectRequest.path to None with StrategyConfig Fallback**:
  - Changed `AccountConnectRequest.path` in `strategy_engine/models.py` (and Android `Models.kt`) to default to `None` instead of a hardcoded path.
  - Verified route fallback preserves configured `StrategyConfig.mt5_path` when `path` is omitted or `None`, while allowing explicit override.
  - Added unit and API tests in `strategy_engine/tests/test_strategy.py`, `api_gateway/tests/test_api.py`, and `ModelsTest.kt`.
- **ConnectionState Enum Typing on Account Connection Models**:
  - Typed `AccountConnectResponse.status` and `ConnectionStatus.status` as `ConnectionState` enum in `strategy_engine/models.py` to enforce strict validation against allowed states (`CONNECTED`, `DISCONNECTED`, `ERROR`).
  - Added unit test `test_connection_state_validation` in `strategy_engine/tests/test_strategy.py` verifying serialization and asserting `ValidationError` is raised for invalid status strings.

### Added
- **Test Suite & Offline Resilience Verification (Issue #55)**:
  - Added end-to-end BDD acceptance tests in `tui/tests/test_tui.py` completing full automated coverage for all 9 Gherkin scenarios defined in parent Issue #51:
    - Scenario 1: Live Telemetry & Financial Metric Synchronization (`test_live_telemetry_synchronization_scenario_1`).
    - Scenario 2: Active Positions Display and Dynamic Cell Updates (`test_positions_table_rendering_and_in_place_updates`).
    - Scenario 3: Account Switching via Connection Modal with Dual Keybindings (`test_connect_modal_success_and_account_switching_scenario_3`, `test_app_keybindings_f2_and_c`).
    - Scenario 4: Safeguarded Emergency Kill Switch with Open Positions (`test_kill_switch_with_open_positions_scenario_4`).
    - Scenario 5: Backend Offline at Launch & Resilient Reconnect Loop (`test_backend_offline_at_launch_and_reconnect_loop_scenario_5`, `test_api_client_offline_fallback_status`).
    - Scenario 6: Invalid Credentials Handling in Connect Modal (`test_connect_modal_error_banner_scenario_6`).
    - Scenario 7: Responsive Terminal Layout Below 80 Columns (`test_responsive_layout_collapse_below_80_columns`).
    - Scenario 8: Kill-Switch Invocation with Zero Open Positions (`test_kill_switch_with_zero_positions_scenario_8`).
    - Scenario 9: Simulation Mode Telemetry & Badge (`test_simulation_mode_telemetry_and_badge_scenario_9`, `test_header_bar_badge_modes`).
  - Validated offline resilience, reconnect timer tick callbacks, and automated recovery when backend comes online.

- **Strategy Control Panel & Action Confirmation Modals (Issue #54)**:
  - Implemented `StrategyPanel` widget (`tui/widgets/strategy_panel.py`) displaying strategy execution state badges (`[● RUNNING]`, `[⏸ PAUSED]`, `[■ STOPPED]`, `[● IDLE]`), strategy and symbol identifier, daily drawdown percentage with warning highlight (>= 3.0%), and total exposure lots calculated across open positions.
  - Implemented `ConfirmModal` screen (`tui/screens/confirm_modal.py`) with support for high-contrast emergency danger styling and informational prompts.
  - Integrated safeguarded Emergency Kill Switch hotkey `K` in `DarwinTraderApp`:
    - When open positions > 0: displays red confirmation modal requiring user approval to invoke `POST /api/v1/strategy/kill-switch`, close open positions, pause strategy, and clear positions table.
    - When 0 open positions: displays informational prompt ("No active positions to liquidate; strategy paused") and pauses strategy via `POST /api/v1/strategy/pause` without triggering order liquidation requests.
  - Implemented `ConnectModal` screen (`tui/screens/connect_modal.py`) supporting Login, Password, Server dropdown, Path, Mock Mode toggle, animated connection spinner, and inline error banner (`#error-banner`) preserving form inputs upon failure.
  - Added `start_strategy` and `pause_strategy` methods to `DarwinApiClient` (`tui/api_client.py`).
  - Added comprehensive automated test coverage in `tui/tests/test_tui.py` covering state badge transitions, drawdown warning triggers, hotkey `K` liquidation & pause branches, and connect modal error handling.

- **Summary Cards & Positions Table Widgets (Issue #53)**:
  - Implemented `SummaryCards` widget (`tui/widgets/summary_cards.py`) displaying financial metrics overview: Balance, Equity, Margin, and Floating P&L with dual-glyph `▲/▼` indicators and USD currency formatting.
  - Implemented `PositionsTable` widget (`tui/widgets/positions_table.py`) wrapping `DataTable` with keyed row differential reconciliation and `DataTable.update_cell` in-place mutations (preserving row selection identity without table remounting).
  - Added stale cache retention for open positions when gateway is unreachable or offline (`ACTIVE POSITIONS [STALE / OFFLINE CACHE]`).
  - Added responsive viewport collapse in `DarwinTraderApp`: automatically transforms `SummaryCards` from a horizontal row into a compact 2x2 grid below 80 columns or 24 rows.
  - Added `swap` field to `Position` model in `strategy_engine/models.py`.
  - Added comprehensive automated test coverage in `tui/tests/test_tui.py` covering dual-glyph formatting, in-place cell updates, offline cache preservation, and terminal resize responsiveness.
- **TUI API Client & Base Application Shell (Issue #52)**:
  - Added `tui` module featuring asynchronous HTTP client `DarwinApiClient` built on `httpx.AsyncClient` with connection pooling and resilient offline fallbacks.
  - Implemented `DarwinTraderApp` shell layout with top `HeaderBar` displaying live connection telemetry badges (`[● CONNECTED (LIVE)]`, `[● CONNECTED (DEMO)]`, `[● SIMULATION]`, `[○ GATEWAY UNREACHABLE (Xs)]`), broker server, account login ID, and reconnect countdown timer.
  - Added dual keybindings `F2` and `C` (and Connect button trigger) invoking `ConnectModal` account connection dialog.
  - Added CLI execution entrypoint `python -m tui` (`tui/__main__.py`).
  - Added automated unit and integration tests (`tui/tests/test_tui.py`) covering offline fallback behavior, badge formatting, background telemetry polling, and keybinding interactions.
  - Added `textual>=0.70.0` dependency to `api_gateway/requirements.txt`, updated `pytest.ini` and CI `build.yml`.
- **Explicit MT5 Path Teardown Fixture for Connect Tests**:
  - Added `preserve_mt5_path` fixture in `api_gateway/tests/conftest.py` that snapshots `global_config.mt5_path` and restores it in a teardown `finally` block.
  - Updated `test_account_connect_path_fallback_preserves_config` and `test_account_connect_explicit_path_overrides_config` in `api_gateway/tests/test_api.py` to use `preserve_mt5_path` explicitly.
- **StrategyConfig.reset_from Helper & Test Isolation Fixture Refactoring**:
  - Added `StrategyConfig.reset_from(other, **overrides)` in `strategy_engine/config.py` enabling bulk resets of live configuration singleton instances without manipulating private Pydantic internals (`__dict__`, `__pydantic_fields_set__`).
  - Refactored `api_gateway/tests/conftest.py` autouse isolation fixture to use `global_config.reset_from()` rather than private Pydantic internals.
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
