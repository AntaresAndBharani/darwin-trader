# Phase 0 Research: Yahoo Finance Market Data Integration, Legacy Data Migration & Web Explorer Workspace

## Decision 1: Storage Engine & Multi-Provider Isolation
- **Decision**: Use a dedicated SQLite WAL database (`data/yahoo_finance.db`) managed by `YahooFinanceDB` in `strategy_engine/yahoo_db.py`, separate from `data/historical_rates.db` (`HistoricalRatesDB`).
- **Rationale**:
  - `data/historical_rates.db` holds 3.5 GB (~19.8M rows) of Darwinex MT5 intraday and daily bars. Isolating the 1.31M Yahoo Finance rows and fundamental/valuation tables in `data/yahoo_finance.db` eliminates SQLite write-lock contention between MT5 tick/bar syncs and Yahoo Finance batch syncs.
  - Preserves Darwin Trader's zero-server operational model (Constitution Principle VI) so no Docker or PostgreSQL daemon is required at runtime.
- **Alternatives Considered**:
  - *Single `historical_rates.db`*: Rejected due to schema divergence (Yahoo Finance includes `market`, `sector`, `industry`, `quarterly_eps`, `quarterly_revenue`, and `valuation_history`) and file lock contention on a 3.5 GB file.
  - *Runtime PostgreSQL (`fractanomicsdb`)*: Rejected because requiring a live PostgreSQL container violates zero-click standalone portability.

## Decision 2: Legacy PostgreSQL (`fractanomicsdb`) Migration Strategy
- **Decision**: Implement `migrate_postgres_to_sqlite()` in `strategy_engine/yahoo_fetcher.py` (and `python -m strategy_engine.cli yahoo-migrate`) using chunked server-side/streaming cursor reads (`fetchmany(10000)`) from `localhost:5433/fractanomicsdb` and batched `executemany` transactions into `YahooFinanceDB`.
- **Rationale**:
  - `stock_prices` has 1,313,580 rows. Fetching in chunks of 25,000 rows and inserting inside single `BEGIN IMMEDIATE ... COMMIT` transactions migrates all 1.31M rows in ~10–15 seconds with minimal memory overhead (<100 MB RAM).
  - Using `INSERT OR REPLACE` makes the migration 100% idempotent and safe to re-run.
- **Alternatives Considered**:
  - *Full-table `pd.read_sql` in memory*: Rejected because loading 1.31M rows into a single DataFrame before SQLite conversion consumes unnecessary memory.

## Decision 3: Multi-Timeframe (`D1`, `W1`, `MN1`) Resampling
- **Decision**: Store canonical daily bars (`YYYY-MM-DD`) in `stock_prices` and resample `W1` (ISO week `W-FRI` / calendar week) and `MN1` (calendar month) deterministically on read in `YahooFinanceDB.get_price_history()`, returning UNIX UTC seconds (`time: int`) matching Lightweight Charts' `UTCTimestamp` contract.
- **Rationale**:
  - Yahoo Finance daily history is already complete in `stock_prices`. Computing `W1` and `MN1` aggregation (`open = first`, `high = max`, `low = min`, `close = last`, `volume = sum`) over a single ticker's ~3,000–5,000 daily rows takes `<5 ms` and avoids storing redundant weekly/monthly tables.
- **Alternatives Considered**:
  - *Separate Yahoo API calls for `1wk` and `1mo`*: Rejected because it triples network requests and isn't needed when daily bars are already stored locally.

## Decision 4: Yahoo Finance (`yahooquery`) Provider & Testability
- **Decision**: Port `format_yahoo_ticker` (mapping `LSE`→`.L`, `BME`→`.MC`, `XETR`/`GETTEX`→`.DE`, `MIL`→`.MI`, `SIX`→`.SW`, `TSX`→`.TO`, `OMXSTO`→`.ST`, `EURONEXT`→`.PA`, `LSIN`→`.IL`, `TSE`→`.T`, `HKEX`→`.HK`, `NSE`→`.NS`, `BSE`→`.BO`, `SSE`→`.SS`, `SZSE`→`.SZ`), OHLCV + `earning_history` / `financial_data`, `asset_profile` (`sector`, `industry`), and `valuation_measures` into `strategy_engine/yahoo_fetcher.py` with an injectable `ticker_factory` parameter.
- **Rationale**:
  - Injectable `ticker_factory` satisfies Constitution Principle IV (100% offline deterministic CI tests without hitting live Yahoo servers during `pytest`).
  - Lazy/optional import of `yahooquery` and `psycopg2` ensures the test suite and API gateway never fail if optional packages are mocked.
