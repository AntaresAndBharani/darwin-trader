---
description: "Task list for Yahoo Finance Market Data Integration, Legacy Data Migration & Web Explorer Workspace"
---

# Tasks: Yahoo Finance Market Data Integration, Legacy Data Migration & Web Explorer Workspace

**Input**: Design documents from `/specs/002-yahoo-finance-workspace/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/yahoo-api.md`

**Tests**: Automated unit and integration tests are REQUIRED per Constitution Principle IV (`pytest` and `vitest`).

**Organization**: Tasks are grouped by user story (`US1`..`US4`) to enable independent implementation and verification of each increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (`US1`, `US2`, `US3`, `US4`)
- Exact file paths are included in every task description.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Ensure Python dependencies and feature branch environment are configured.

- [X] T001 Create and switch to feature branch `feat/002-yahoo-finance-workspace` from `main`
- [X] T002 Add `yahooquery>=2.3.7` and `psycopg2-binary>=2.9.9` to `strategy_engine/requirements.txt` and verify availability in active Python environment

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core SQLite WAL storage engine (`YahooFinanceDB`) required by all CLI, API, and Web user stories.

- [X] T003 Implement `YahooFinanceDB` in `strategy_engine/yahoo_db.py` with SQLite `WAL` mode (`PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, `PRAGMA busy_timeout=60000;`), `BEGIN IMMEDIATE` exponential-backoff write retry, non-finite float (`NaN`/`Inf` -> `None`) sanitization, and schema initialization for `tickers` (`symbol TEXT PRIMARY KEY`, `name`, `market`, `sector`, `industry`, `active`, `created_at`), `stock_prices` (`PRIMARY KEY (symbol, date DESC) WITHOUT ROWID`), and `valuation_history` (`PRIMARY KEY (symbol, as_of_date DESC, period_type) WITHOUT ROWID`)
- [X] T004 Implement ticker CRUD/filter methods (`upsert_tickers`, `get_tickers`, `get_ticker`, `get_filter_facets`, `update_ticker`, `delete_ticker`), OHLCV upsert & `D1`/`W1`/`MN1` resampling (`upsert_stock_prices`, `get_price_history`, `get_data_ranges`), and fundamental/valuation queries (`upsert_valuation_history`, `get_fundamentals_summary`) in `strategy_engine/yahoo_db.py`
- [X] T005 [P] Create comprehensive unit test suite in `strategy_engine/tests/test_yahoo_db.py` verifying `YahooFinanceDB` WAL initialization, `MARKET:SYMBOL` normalization, filter facets, `D1`/`W1`/`MN1` resampling math, `NaN`/`Inf` sanitization, and valuation/earnings queries

---

## Phase 3: User Story 1 - Isolated Yahoo Finance Local Storage, Legacy Migration & CLI Sync (Priority: P1) 🎯 MVP

**Goal**: Port the Yahoo Finance (`yahooquery`) fetcher and PostgreSQL (`fractanomicsdb`) migrator into `strategy_engine/`, wire `yahoo-migrate` and `yahoo-sync` into `strategy_engine/cli.py`, and migrate the 1,011 tickers, 1.31M price rows, and 12.3k valuation rows into `data/yahoo_finance.db`.

**Independent Test**: Run `pytest strategy_engine/tests/test_yahoo_fetcher.py -v` and execute `python -m strategy_engine.cli yahoo-migrate` to verify `data/yahoo_finance.db` contains all migrated rows.

### Tests for User Story 1

- [X] T006 [P] [US1] Create unit tests in `strategy_engine/tests/test_yahoo_fetcher.py` covering `format_yahoo_ticker`, `fetch_ticker_ohlcv_and_earnings`, `fetch_ticker_metadata`, `fetch_ticker_valuation`, `sync_yahoo_tickers` (with mock `ticker_factory`), `migrate_postgres_to_sqlite` (with mock PG cursor), and CLI `yahoo-migrate` / `yahoo-sync` subcommands

### Implementation for User Story 1

- [X] T007 [US1] Implement `strategy_engine/yahoo_fetcher.py` with `format_yahoo_ticker`, injectable `ticker_factory`, `fetch_ticker_ohlcv_and_earnings`, `fetch_ticker_metadata`, `fetch_ticker_valuation`, incremental `sync_yahoo_tickers`, and chunked `migrate_postgres_to_sqlite`
- [X] T008 [US1] Extend `strategy_engine/cli.py` with `yahoo-migrate` and `yahoo-sync` subcommands and handlers (`handle_yahoo_migrate`, `handle_yahoo_sync`) adhering to stderr logging and exit code contracts
- [X] T009 [US1] Execute `python -m strategy_engine.cli yahoo-migrate` against `localhost:5433/fractanomicsdb` to populate `data/yahoo_finance.db` with the 1,011 tickers, 1,313,580 price rows, and 12,374 valuation rows and verify counts

**Checkpoint**: `data/yahoo_finance.db` is populated and `pytest strategy_engine/tests` passes 100%.

---

## Phase 4: User Story 2 - FastAPI Yahoo Finance Data & Synchronization Gateway (Priority: P2)

**Goal**: Expose `/api/v1/yahoo/*` REST endpoints for ticker filtering/CRUD, `D1`/`W1`/`MN1` history, fundamentals & valuation history, and single/batch synchronization.

**Independent Test**: Run `pytest api_gateway/tests/test_routes_yahoo.py -v` to verify all `/api/v1/yahoo/*` contracts and status codes.

### Tests for User Story 2

- [X] T010 [P] [US2] Create FastAPI integration test suite in `api_gateway/tests/test_routes_yahoo.py` testing `GET /api/v1/yahoo/tickers` (with filters and facets), `POST /api/v1/yahoo/tickers`, `PATCH /api/v1/yahoo/tickers/{symbol}`, `DELETE /api/v1/yahoo/tickers/{symbol}`, `GET /api/v1/yahoo/tickers/{symbol}/history` (`D1`/`W1`/`MN1` + `400` invalid timeframe), `GET /api/v1/yahoo/tickers/{symbol}/fundamentals`, `POST /api/v1/yahoo/sync` (including `409 Conflict` when busy), and `GET /api/v1/yahoo/sync/status`

### Implementation for User Story 2

- [X] T011 [US2] Implement `api_gateway/routes_yahoo.py` with thread-safe `_yahoo_lock` synchronization, Pydantic request/response models, ticker CRUD/filter routes, `D1`/`W1`/`MN1` history route, fundamentals route, and single/background sync routes
- [X] T012 [US2] Register `yahoo_router` in `api_gateway/main.py`

**Checkpoint**: All `/api/v1/yahoo/*` endpoints are live and `pytest api_gateway/tests` passes 100%.

---

## Phase 5: User Story 3 - Web Dashboard Top-Level Navigation Tabs & Darwinex MT5 Layout Cleanup (Priority: P3)

**Goal**: Add top-level `Darwinex MT5` and `Yahoo Finance` tabs in `web/src/App.tsx` and remove the placeholder `StrategySidebar` from the `Darwinex MT5` tab so `PositionsGrid` spans full width.

**Independent Test**: Run `npm test` in `web/` to verify `App.test.tsx` renders both tabs, defaults to `Darwinex MT5` with full-width `PositionsGrid` (and no `StrategySidebar`), and switches to `YahooWorkspace` when clicking `Yahoo Finance`.

### Implementation & Tests for User Story 3

- [X] T013 [P] [US3] Create typed Axios API client `web/src/api/yahoo.ts` and unit tests in `web/src/api/yahoo.test.ts` covering all `/api/v1/yahoo/*` methods
- [X] T014 [US3] Update `web/src/App.tsx` to render top-level navigation tabs (`data-testid="tab-darwinex-mt5"` and `data-testid="tab-yahoo-finance"`), remove `StrategySidebar` from the `Darwinex MT5` tab so `PositionsGrid` spans full width, and render `YahooWorkspace` when the `Yahoo Finance` tab is active

---

## Phase 6: User Story 4 - Yahoo Finance Master-Detail Explorer Workspace (Priority: P4)

**Goal**: Build the interactive `YahooWorkspace` component in `web/src/components/YahooWorkspace.tsx` featuring a filterable ticker explorer (`Market`, `Sector`, `Industry`, `Active`, search), ticker management (add, toggle active, delete), TradingView Lightweight Charts canvas (`D1`/`W1`/`MN1` + Heikin-Ashi toggle), Fundamentals & Quarterly Valuation panel, and sync/catch-up controls.

**Independent Test**: Run `npm test`, `npm run lint`, and `npm run build` in `web/` to verify `YahooWorkspace.test.tsx` and `App.test.tsx` pass 100%.

### Tests & Implementation for User Story 4

- [X] T015 [US4] Implement `web/src/components/YahooWorkspace.tsx` with filter bar (`Market`, `Sector`, `Industry`, `Active`, search), virtualized/scrollable ticker list, Add/Toggle/Delete ticker controls, TradingView candlestick/Heikin-Ashi chart (`D1`/`W1`/`MN1`), Fundamentals & Quarterly Valuation panel, and Sync Ticker / Catch-Up All controls
- [X] T016 [US4] Create comprehensive component tests in `web/src/components/YahooWorkspace.test.tsx` and update `web/src/App.test.tsx` covering tab navigation, ticker filtering, timeframe/Heikin-Ashi toggling, fundamentals rendering, ticker creation/toggle/deletion, and sync triggering

**Checkpoint**: All 4 user stories are complete and independently verified across Python and Web test suites.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, Changelog, full test/lint/build verification, and PR creation.

- [X] T017 Remove temporary HTML `Sync Impact Report` comment from `.specify/memory/constitution.md` before committing (per `speckit-constitution` rule) and update `.graph/architecture.md` & `CHANGELOG.md` under `## [Unreleased]`
- [X] T018 Execute full Python test suite (`pytest api_gateway/tests strategy_engine/tests tui/tests`) and Web checks (`npm test`, `npm run lint`, `npm run build` in `web/`) and confirm 100% green pass

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → **Phase 2 (Foundational `YahooFinanceDB`)** → **Phase 3 (US1: Fetcher, Migrator & CLI)** → **Phase 4 (US2: FastAPI `/api/v1/yahoo`)** → **Phase 5 & 6 (US3 & US4: Web Tabs & `YahooWorkspace`)** → **Phase 7 (Polish, Verification & PR)**.
