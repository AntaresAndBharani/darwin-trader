# Feature Specification: Yahoo Finance Market Data Integration, Legacy Data Migration & Web Explorer Workspace

**Feature Branch**: `feat/002-yahoo-finance-workspace`

**Created**: 2026-10-23

**Status**: Approved

**Input**: User description: "Move the Yahoo Finance stock data, ticker metadata, and fundamentals from our sibling projects (bl-stock-data-service / trading-manager / stock-manager-cli) into darwin-trader alongside Darwinex Zero MT5 data, migrate the existing dataset into an isolated local store, remove the unused StrategySidebar placeholder on the Darwinex MT5 tab, and create a dedicated Yahoo Finance Master-Detail Explorer tab in the Web Dashboard."

## Clarifications

### Session 2026-10-23

- Q: What scope of Yahoo Finance data should be brought over for this first step? → A: Yahoo Finance daily OHLCV (`stock_prices`) + Ticker Metadata (`sector`, `industry`, `market`, `name`, `active`) + Fundamentals & Valuation Multiples (`quarterly_eps`, `quarterly_revenue`, and `valuation_history`: `trailing_pe`, `forward_pe`, `pb`, `ps`, `peg`, `ev_ebitda`, `ev_revenue`, `market_cap`, `enterprise_value`, `dividend_yield`).
- Q: How should Yahoo Finance data be stored so Darwinex MT5 and Yahoo Finance data coexist cleanly? → A: Dedicated embedded SQLite database (`data/yahoo_finance.db`) in WAL mode, zero external database server needed at runtime, isolated from the 3.5 GB MT5 `data/historical_rates.db`.
- Q: Should we migrate the existing 1,011 tickers, 1.31M price rows, and 12.3k valuation rows from `localhost:5433/fractanomicsdb`? → A: Yes, migrate all three core tables (`tickers`, `stock_prices`, `valuation_history`) into `data/yahoo_finance.db` AND port the Yahoo Finance catch-up/sync engine for Web UI and CLI.
- Q: How should the new view be organized in the Web Dashboard (`App.tsx`) alongside Darwinex Zero (MT5)? → A: Top-level Navigation Tabs in `App.tsx` ("Darwinex MT5" and "Yahoo Finance"), removing the placeholder `StrategySidebar` from the "Darwinex MT5" tab so `PositionsGrid` spans full width.
- Q: How should the "Yahoo Finance" tab be laid out and which clients are in scope? → A: Master-Detail Workspace (Filterable Ticker Explorer + TradingView Candlestick/Heikin-Ashi Chart for D1/W1/MN1 + Fundamentals & Quarterly Valuation Panel + Sync/Catch-Up controls) in the React Web Dashboard + FastAPI Gateway + CLI (`tui/` excluded in this step).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Isolated Yahoo Finance Local Storage, Legacy Migration & CLI Sync (Priority: P1)

As a quantitative trader, I need all accumulated Yahoo Finance stock data (1,011 tickers with market/sector/industry metadata, 1.31M daily OHLCV + quarterly EPS/revenue rows, and 12.3k quarterly valuation multiple rows) migrated into a self-contained local database and kept up to date via CLI and API synchronization so that I can analyze deep exchange history and company fundamentals without running an external database server.

**Why this priority**: Every downstream API route and Web UI visualization depends on having the Yahoo Finance schema, resampled price queries (`D1`, `W1`, `MN1`), fundamental summaries, legacy migration tool, and incremental Yahoo Finance sync engine in place.

**Independent Test**: Can be fully tested by executing the migration command against the legacy database (or test fixture), running the Yahoo Finance sync command for specific symbols, and querying tickers, resampled `D1`/`W1`/`MN1` bars, and valuation history from the local store.

**Acceptance Scenarios**:

1. **Given** an initialized local Yahoo Finance store, **When** tickers, daily price bars (with quarterly EPS/revenue), and quarterly valuation history records are saved, **Then** the system persists them idempotently without duplicates and supports filtering tickers by market, sector, industry, active status, and search text.
2. **Given** daily OHLCV bars for a stock in the local store, **When** price history is requested for Daily (`D1`), Weekly (`W1`), or Monthly (`MN1`) timeframes, **Then** the system returns chronologically ordered bars with accurate open, high, low, close, and summed volume for each period.
3. **Given** the existing PostgreSQL `fractanomicsdb` dataset, **When** the operator runs the migration command, **Then** all `tickers`, `stock_prices`, and `valuation_history` rows are batch-copied into `data/yahoo_finance.db` with zero data loss and reported row counts.
4. **Given** a tracked ticker with a market prefix (e.g., `NASDAQ:AAPL`, `BME:SAN`, `LSE:GAW`, `XETR:DAX`), **When** a Yahoo Finance sync is triggered, **Then** the exchange suffix is resolved automatically and daily prices, quarterly EPS/revenue, sector/industry metadata, and valuation multiples are updated.

---

### User Story 2 - FastAPI Yahoo Finance Data & Synchronization Gateway (Priority: P2)

As a web client or automation script, I need REST endpoints to list/filter/manage tracked Yahoo Finance tickers, retrieve `D1`/`W1`/`MN1` price history and company fundamentals/valuation multiples, and trigger single-ticker or batch catch-up synchronization through the gateway.

**Why this priority**: Decouples the React Web Dashboard from direct database or SDK access in strict compliance with Clean Architecture.

**Independent Test**: Can be fully tested by sending HTTP requests to `/api/v1/yahoo/*` endpoints and verifying response payloads, filter facets, ticker CRUD mutations, resampled bars, fundamental snapshots, and background sync state transitions.

**Acceptance Scenarios**:

1. **Given** tracked tickers in the local Yahoo Finance store, **When** a client requests `GET /api/v1/yahoo/tickers` with optional `market`, `sector`, `industry`, `active`, or `search` parameters, **Then** the gateway returns the matching ticker list along with available distinct filter facets (`markets`, `sectors`, `industries`).
2. **Given** the user wants to track or manage a ticker, **When** `POST /api/v1/yahoo/tickers` (e.g., `{"symbol": "NASDAQ:NVDA"}`), `PATCH /api/v1/yahoo/tickers/{symbol}` (`{"active": false}`), or `DELETE /api/v1/yahoo/tickers/{symbol}` is called, **Then** the ticker catalog updates immediately and reflects the change on subsequent queries.
3. **Given** a symbol with stored Yahoo Finance data, **When** `GET /api/v1/yahoo/tickers/{symbol}/history?timeframe=W1` and `GET /api/v1/yahoo/tickers/{symbol}/fundamentals` are called, **Then** the gateway returns chronologically ordered OHLCV bars and a consolidated payload containing ticker metadata, latest valuation ratios, historical quarterly valuation multiples, and quarterly EPS/revenue series.
4. **Given** the user triggers `POST /api/v1/yahoo/sync` for a single symbol or all active symbols, **Then** the gateway executes or dispatches the synchronization safely and reports real-time progress via `GET /api/v1/yahoo/sync/status`.

---

### User Story 3 - Web Dashboard Top-Level Navigation Tabs & Darwinex MT5 Layout Cleanup (Priority: P3)

As a trader using the Web Dashboard, I want top-level tabs to switch cleanly between my live **Darwinex MT5** workspace and the **Yahoo Finance** research workspace, and I want the non-functional `StrategySidebar` placeholder removed from the **Darwinex MT5** tab so my open positions table spans the full width.

**Why this priority**: Eliminates the confusing, unsynchronized `EURUSD` strategy lifecycle placeholder and provides the navigation shell for the Yahoo Finance workspace.

**Independent Test**: Can be tested by rendering the Web Dashboard, verifying that "Darwinex MT5" is active by default with a full-width `PositionsGrid` and no `StrategySidebar`, and clicking "Yahoo Finance" to switch workspaces.

**Acceptance Scenarios**:

1. **Given** the Web Dashboard loads, **When** the default **Darwinex MT5** tab is displayed, **Then** `StatusRibbon`, `ChartWorkspace`, and a full-width `PositionsGrid` are visible, and `StrategySidebar` is not rendered.
2. **Given** the Web Dashboard header/navigation bar, **When** the operator clicks the **Yahoo Finance** tab, **Then** the view switches to `YahooWorkspace` while keeping the top `StatusRibbon` and `Connect MT5...` header accessible.

---

### User Story 4 - Yahoo Finance Master-Detail Explorer Workspace (Priority: P4)

As a trader researching equities on the **Yahoo Finance** tab, I want a master-detail workspace where I can filter and manage the 1,000+ tracked tickers by Market, Sector, Industry, and search query, inspect their `D1`/`W1`/`MN1` Candlestick or Heikin-Ashi chart, review their latest valuation multiples and quarterly EPS/revenue history, and trigger on-demand data syncs.

**Why this priority**: Delivers the complete interactive visual experience for exploring the migrated and live-synced Yahoo Finance dataset.

**Independent Test**: Can be tested by opening the **Yahoo Finance** tab, filtering tickers by sector/market/search, selecting a ticker, toggling `D1`/`W1`/`MN1` and Heikin-Ashi on the chart, inspecting the fundamentals & valuation tables, adding a ticker, and triggering a sync.

**Acceptance Scenarios**:

1. **Given** the user is on the **Yahoo Finance** tab, **When** the workspace mounts, **Then** the filter bar (`Market`, `Sector`, `Industry`, `Active`, search input), ticker list, TradingView chart canvas, and Fundamentals & Valuation panel are rendered and populated with the first available ticker.
2. **Given** the user filters by `Sector`, `Industry`, `Market`, or types a search query, **When** the filter changes, **Then** the ticker list updates immediately to display matching tickers and total count.
3. **Given** a selected ticker in `YahooWorkspace`, **When** the user switches timeframe between `D1`, `W1`, and `MN1` or toggles `Heikin-Ashi`, **Then** the chart series updates to render the corresponding resampled or Heikin-Ashi transformed bars.
4. **Given** a selected ticker in `YahooWorkspace`, **When** its fundamentals load, **Then** the panel displays the latest valuation snapshot (`Trailing P/E`, `Forward P/E`, `P/B`, `P/S`, `PEG`, `EV/EBITDA`, `EV/Revenue`, `Market Cap`, `Enterprise Value`, `Dividend Yield`) alongside historical quarterly valuation and quarterly EPS/Revenue records.
5. **Given** the user adds a ticker (`MARKET:SYMBOL` or `SYMBOL`), toggles a ticker's active status, deletes a ticker, or clicks **Sync Ticker** / **Catch-Up All**, **Then** the action dispatches to `/api/v1/yahoo/*` and refreshes the workspace telemetry upon completion.

### Edge Cases

- **Ticker with no valuation or quarterly earnings data** (e.g., futures, forex pairs, or ETFs like `NASDAQ:TLT` or `FX:EURUSD` in the migrated list): The chart still renders OHLCV price history normally while the Fundamentals & Valuation panel displays graceful `"—"` / `"No fundamental data available for this instrument"` empty states without crashing.
- **Non-finite floats (`NaN` / `Inf`) in Yahoo Finance payloads**: Sanitized to `null` (`None`) at both the SQLite storage boundary and Pydantic API serialization boundary so JSON responses never fail.
- **Concurrent sync requests**: If a batch catch-up sync is already running (`IN_PROGRESS`), a second batch sync request returns HTTP `409 Conflict` while status polling continues cleanly.
- **Market prefix formatting**: Symbols stored with exchange prefixes (e.g., `BME:SAN`, `LSE:BA.`, `XETR:BMW`, `TSX:BNS`, `EURONEXT:MC`) are mapped deterministically to Yahoo Finance ticker suffixes (`.MC`, `.L`, `.DE`, `.TO`, `.PA`, etc.) during sync.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a dedicated SQLite WAL storage engine (`YahooFinanceDB`) backed by `data/yahoo_finance.db` containing `tickers`, `stock_prices`, and `valuation_history` tables.
- **FR-002**: System MUST support deterministic resampling of daily `stock_prices` into Weekly (`W1`) and Monthly (`MN1`) OHLCV bars in chronological ascending order.
- **FR-003**: System MUST provide a migration capability (`yahoo-migrate` CLI command and service function) that copies `tickers`, `stock_prices`, and `valuation_history` from PostgreSQL (`fractanomicsdb`) into `data/yahoo_finance.db` using idempotent batch upserts.
- **FR-004**: System MUST provide a Yahoo Finance synchronization engine (`yahoo_fetcher.py` and `yahoo-sync` CLI command) that resolves market prefixes to Yahoo suffixes and fetches daily OHLCV bars, quarterly EPS/revenue, ticker metadata (`name`, `sector`, `industry`), and quarterly valuation measures.
- **FR-005**: System MUST expose FastAPI REST endpoints under `/api/v1/yahoo` for listing/filtering tickers with distinct filter facets, adding/updating/deleting tickers, fetching `D1`/`W1`/`MN1` price history, fetching fundamentals & valuation history, and triggering/polling data synchronization.
- **FR-006**: Web Dashboard (`App.tsx`) MUST provide top-level navigation tabs to switch between **Darwinex MT5** and **Yahoo Finance**, and MUST remove the legacy `StrategySidebar` component from the **Darwinex MT5** tab so `PositionsGrid` occupies the full width.
- **FR-007**: Web Dashboard MUST provide a `YahooWorkspace` component featuring a filterable ticker explorer (`Market`, `Sector`, `Industry`, `Active`, search), ticker management actions (add, toggle active, delete), a TradingView Lightweight Charts canvas (`D1`, `W1`, `MN1` + Heikin-Ashi toggle), a Fundamentals & Quarterly Valuation panel, and sync controls.

### Key Entities

- **YahooTicker**: Represents a tracked instrument (`symbol`, `name`, `market`, `sector`, `industry`, `active`, `created_at`, plus optional summary fields `latest_close`, `latest_date`).
- **YahooStockPrice**: Represents a daily OHLCV bar with optional quarterly earnings alignment (`symbol`, `date`, `open`, `high`, `low`, `close`, `volume`, `quarterly_eps`, `quarterly_revenue`, `updated_at`).
- **YahooValuationRecord**: Represents a quarterly valuation snapshot (`symbol`, `as_of_date`, `period_type`, `trailing_pe`, `forward_pe`, `pb`, `ps`, `peg`, `ev_ebitda`, `ev_revenue`, `market_cap`, `enterprise_value`, `dividend_yield`, `updated_at`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the existing PostgreSQL dataset (`1,011` tickers, `1,313,580` stock price rows, and `12,374` valuation history rows) migrates into `data/yahoo_finance.db` in under 60 seconds with zero row loss.
- **SC-002**: Filtering tickers across 1,000+ instruments and loading `D1`/`W1`/`MN1` chart history and fundamentals for any selected ticker completes in under 500 milliseconds from local storage.
- **SC-003**: Users can switch between the **Darwinex MT5** and **Yahoo Finance** tabs, filter by sector/industry/market, inspect charts and valuation multiples, and manage tickers with 100% passing automated tests across Python and Web suites.

## Assumptions

- The local PostgreSQL instance at `localhost:5433/fractanomicsdb` (user `postgres`) is available during migration to seed `data/yahoo_finance.db`, after which `darwin-trader` operates 100% standalone from `data/yahoo_finance.db`.
- The Textual TUI (`tui/`) remains focused on Darwinex MT5 telemetry and is out of scope for this feature.
