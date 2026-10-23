# Phase 1 Interface Contracts: Yahoo Finance REST API & CLI

## 1. FastAPI Gateway Contract (`/api/v1/yahoo`)

### 1.1 `GET /api/v1/yahoo/tickers`
Query parameters:
- `market` (optional `str`): Exact market filter (e.g., `NASDAQ`, `NYSE`, `BME`, `LSE`)
- `sector` (optional `str`): Exact sector filter (e.g., `Technology`)
- `industry` (optional `str`): Exact industry filter
- `active_only` (optional `bool`, default `false`): When `true`, returns only `active == 1` tickers
- `search` (optional `str`): Case-insensitive substring match against `symbol` or `name`

Response `200 OK`:
```json
{
  "total": 1011,
  "tickers": [
    {
      "symbol": "AAPL",
      "name": "Apple Inc.",
      "market": "NASDAQ",
      "sector": "Technology",
      "industry": "Consumer Electronics",
      "active": true
    }
  ],
  "facets": {
    "markets": ["BME", "EURONEXT", "LSE", "NASDAQ", "NYSE", "XETR"],
    "sectors": ["Communication Services", "Consumer Cyclical", "Financial Services", "Technology"],
    "industries": ["Banks - Diversified", "Consumer Electronics", "Semiconductors"]
  }
}
```

### 1.2 `POST /api/v1/yahoo/tickers`
Request body:
```json
{
  "symbol": "NASDAQ:AAPL",
  "name": "Apple Inc.",
  "market": "NASDAQ",
  "sector": "Technology",
  "industry": "Consumer Electronics",
  "active": true
}
```
- Accepts `"MARKET:SYMBOL"` in `symbol` or separate `symbol` + `market`.
- Response `200 OK`: Returns the created/updated ticker object.
- Response `400 Bad Request`: If `symbol` is empty.

### 1.3 `PATCH /api/v1/yahoo/tickers/{symbol}`
Request body:
```json
{
  "active": false,
  "name": "Apple Inc.",
  "market": "NASDAQ",
  "sector": "Technology",
  "industry": "Consumer Electronics"
}
```
- Response `200 OK`: Returns updated ticker object.
- Response `404 Not Found`: If `symbol` does not exist.

### 1.4 `DELETE /api/v1/yahoo/tickers/{symbol}`
- Deletes the ticker and all associated `stock_prices` and `valuation_history` records.
- Response `200 OK`: `{"symbol": "AAPL", "deleted": true, "deleted_prices": 2500, "deleted_valuations": 20}`.
- Response `404 Not Found`: If `symbol` does not exist.

### 1.5 `GET /api/v1/yahoo/tickers/{symbol}/history`
Query parameters:
- `timeframe` (`str`, default `"D1"`): Supported values `"D1"`, `"W1"`, `"MN1"`
- `limit` (`int`, default `1500`, range `1..10000`)

Response `200 OK`:
```json
{
  "symbol": "AAPL",
  "timeframe": "D1",
  "total_bars": 1250,
  "bars": [
    {
      "time": 1704153600,
      "date": "2024-01-02",
      "open": 187.15,
      "high": 188.44,
      "low": 183.89,
      "close": 185.64,
      "volume": 82488700
    }
  ]
}
```
- Response `400 Bad Request`: If `timeframe` is not in `{"D1", "W1", "MN1"}`.

### 1.6 `GET /api/v1/yahoo/tickers/{symbol}/fundamentals`
Response `200 OK`:
```json
{
  "symbol": "AAPL",
  "ticker": {
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "market": "NASDAQ",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "active": true
  },
  "latest_valuation": {
    "as_of_date": "2024-09-30",
    "period_type": "3M",
    "trailing_pe": 34.5,
    "forward_pe": 28.9,
    "pb": 48.2,
    "ps": 8.9,
    "peg": 2.4,
    "ev_ebitda": 26.1,
    "ev_revenue": 8.8,
    "market_cap": 3450000000000.0,
    "enterprise_value": 3510000000000.0,
    "dividend_yield": 0.0044
  },
  "valuation_history": [
    {
      "as_of_date": "2024-09-30",
      "period_type": "3M",
      "trailing_pe": 34.5,
      "forward_pe": 28.9,
      "pb": 48.2,
      "ps": 8.9,
      "peg": 2.4,
      "ev_ebitda": 26.1,
      "ev_revenue": 8.8,
      "market_cap": 3450000000000.0,
      "enterprise_value": 3510000000000.0,
      "dividend_yield": 0.0044
    }
  ],
  "quarterly_earnings": [
    {
      "date": "2024-08-01",
      "quarterly_eps": 1.40,
      "quarterly_revenue": 85777000000.0
    }
  ]
}
```

### 1.7 `POST /api/v1/yahoo/sync` & `GET /api/v1/yahoo/sync/status`
`POST /api/v1/yahoo/sync` Request body:
```json
{
  "symbol": "AAPL",
  "include_fundamentals": true,
  "include_valuation": true,
  "include_metadata": true,
  "start_date": null,
  "end_date": null
}
```
- When `symbol` is omitted or `null`, initiates a background catch-up sync across all active tickers (`202 Accepted`), or returns `409 Conflict` if a sync is already `IN_PROGRESS`.
- When `symbol` is provided, syncs that ticker and updates `sync_status`.

`GET /api/v1/yahoo/sync/status` Response `200 OK`:
```json
{
  "status": "COMPLETED",
  "total_tickers": 1,
  "completed_tickers": 1,
  "failed_tickers": 0,
  "rows_upserted": 252,
  "valuations_upserted": 5,
  "message": "Synced 1/1 ticker(s)"
}
```

---

## 2. CLI Contract (`python -m strategy_engine.cli`)

### 2.1 `yahoo-migrate`
```powershell
python -m strategy_engine.cli yahoo-migrate `
  [--pg-host localhost] [--pg-port 5433] [--pg-db fractanomicsdb] `
  [--pg-user postgres] [--pg-pass postgres] [--db-path data/yahoo_finance.db]
```
- Copies all `tickers`, `stock_prices`, and `valuation_history` rows from PostgreSQL into `data/yahoo_finance.db`.
- Exit code `0` on success, `1` on connection or migration error.

### 2.2 `yahoo-sync`
```powershell
python -m strategy_engine.cli yahoo-sync `
  [--symbol AAPL] [--start-date 2024-01-01] [--end-date 2026-10-23] `
  [--include-fundamentals] [--include-valuation] [--include-metadata] `
  [--workers 5] [--db-path data/yahoo_finance.db]
```
- Syncs specified `--symbol` (or all active tickers in `data/yahoo_finance.db` if omitted) from Yahoo Finance (`yahooquery`).
- Exit code `0` on success, `1` on fatal error, `2` on partial failure.
