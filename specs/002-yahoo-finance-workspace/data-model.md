# Phase 1 Data Model: Yahoo Finance Storage & Domain Entities

## 1. SQLite Schema (`data/yahoo_finance.db`)

Managed by `YahooFinanceDB` (`strategy_engine/yahoo_db.py`) in `WAL` mode (`PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, `PRAGMA busy_timeout=60000;`).

### Table: `tickers`
Stores tracked instruments and their classification metadata.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `symbol` | `TEXT` | `PRIMARY KEY NOT NULL` | Normalized uppercase ticker symbol (e.g., `AAPL`, `SAN`, `BMW`) |
| `name` | `TEXT` | `NOT NULL DEFAULT ''` | Company or instrument display name |
| `market` | `TEXT` | `NOT NULL DEFAULT ''` | Exchange/market code (e.g., `NASDAQ`, `NYSE`, `BME`, `LSE`, `XETR`) |
| `sector` | `TEXT` | `NOT NULL DEFAULT ''` | GICS/Yahoo sector classification (e.g., `Technology`, `Financial Services`) |
| `industry` | `TEXT` | `NOT NULL DEFAULT ''` | Industry classification (e.g., `Semiconductors`, `Banks - Diversified`) |
| `active` | `INTEGER` | `NOT NULL DEFAULT 1` | `1` = active for batch syncs, `0` = inactive |
| `created_at` | `TEXT` | `DEFAULT CURRENT_TIMESTAMP` | ISO timestamp of creation |

Indexes:
- `idx_tickers_market ON tickers(market)`
- `idx_tickers_sector_industry ON tickers(sector, industry)`

### Table: `stock_prices` (`WITHOUT ROWID`)
Stores daily OHLCV bars and aligned quarterly earnings metrics.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `symbol` | `TEXT` | `NOT NULL` | Foreign key to `tickers(symbol)` |
| `date` | `TEXT` | `NOT NULL` | Trading date in `YYYY-MM-DD` format |
| `open` | `REAL` | `NOT NULL` | Daily open price |
| `high` | `REAL` | `NOT NULL` | Daily high price |
| `low` | `REAL` | `NOT NULL` | Daily low price |
| `close` | `REAL` | `NOT NULL` | Daily close price |
| `volume` | `INTEGER` | `NOT NULL DEFAULT 0` | Daily traded share/contract volume |
| `quarterly_eps` | `REAL` | `NULL` | Most recent quarterly EPS aligned as-of `date` |
| `quarterly_revenue` | `REAL` | `NULL` | Most recent quarterly revenue aligned as-of `date` |
| `updated_at` | `TEXT` | `DEFAULT CURRENT_TIMESTAMP` | Last upsert timestamp |

Primary Key: `PRIMARY KEY (symbol, date DESC) WITHOUT ROWID`

### Table: `valuation_history` (`WITHOUT ROWID`)
Stores quarterly valuation multiples from Yahoo Finance `valuation_measures`.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `symbol` | `TEXT` | `NOT NULL` | Foreign key to `tickers(symbol)` |
| `as_of_date` | `TEXT` | `NOT NULL` | Quarter end date in `YYYY-MM-DD` format |
| `period_type` | `TEXT` | `NOT NULL DEFAULT ''` | Period identifier (e.g., `3M`, `TTM`, `Current`) |
| `trailing_pe` | `REAL` | `NULL` | Trailing P/E ratio (`PeRatio`) |
| `forward_pe` | `REAL` | `NULL` | Forward P/E ratio (`ForwardPeRatio`) |
| `pb` | `REAL` | `NULL` | Price-to-Book ratio (`PbRatio`) |
| `ps` | `REAL` | `NULL` | Price-to-Sales ratio (`PsRatio`) |
| `peg` | `REAL` | `NULL` | PEG ratio (`PegRatio`) |
| `ev_ebitda` | `REAL` | `NULL` | Enterprise Value / EBITDA (`EnterprisesValueEBITDARatio`) |
| `ev_revenue` | `REAL` | `NULL` | Enterprise Value / Revenue (`EnterprisesValueRevenueRatio`) |
| `market_cap` | `REAL` | `NULL` | Market Capitalization (`MarketCap`) |
| `enterprise_value` | `REAL` | `NULL` | Enterprise Value (`EnterpriseValue`) |
| `dividend_yield` | `REAL` | `NULL` | Dividend Yield (`dividendYield` attached to latest snapshot) |
| `updated_at` | `TEXT` | `DEFAULT CURRENT_TIMESTAMP` | Last upsert timestamp |

Primary Key: `PRIMARY KEY (symbol, as_of_date DESC, period_type) WITHOUT ROWID`

---

## 2. Validation & Sanitization Rules

1. **Symbol Normalization**:
   - Input strings of form `"MARKET:SYMBOL"` (e.g., `"NASDAQ:AAPL"`) are split into `market="NASDAQ"` and `symbol="AAPL"`.
   - Symbols are stripped and uppercased (`<= 20` characters).
2. **Non-Finite Float Sanitization**:
   - Any `NaN`, `Inf`, or `-Inf` float in price, EPS, revenue, or valuation fields MUST be coerced to `None` (`NULL`) before SQLite persistence and JSON serialization.
3. **Timeframe Resampling (`D1`, `W1`, `MN1`)**:
   - `D1`: Direct daily bars ordered chronologically (`ASC`) with `time` converted to UTC midnight UNIX timestamp (`int`).
   - `W1`: Grouped by ISO year-week (`YYYY-WW`), where `time` is the first trading day's UTC timestamp (or week anchor), `open = first(open)`, `high = max(high)`, `low = min(low)`, `close = last(close)`, `volume = sum(volume)`.
   - `MN1`: Grouped by calendar month (`YYYY-MM`), with `open = first(open)`, `high = max(high)`, `low = min(low)`, `close = last(close)`, `volume = sum(volume)`.
