"""
SQLite WAL Storage Layer for Yahoo Finance Market Data, Ticker Metadata, and Valuation History.
Isolated from Darwinex MT5 historical_rates.db in compliance with Constitution Principle VI.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import logging
import math
import os
import random
import sqlite3
import time
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

DEFAULT_YAHOO_DB_PATH = os.path.join("data", "yahoo_finance.db")
SUPPORTED_YAHOO_TIMEFRAMES = ("D1", "W1", "MN1")


def sanitize_float(val: Any) -> Optional[float]:
    """Coerces scalar to finite float or None if None/NaN/Inf/invalid."""
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def sanitize_int(val: Any, default: int = 0) -> int:
    """Coerces scalar to int or returns default if None/NaN/Inf/invalid."""
    f = sanitize_float(val)
    if f is None:
        return default
    return int(f)


def parse_market_symbol(raw_symbol: str, default_market: str = "") -> Tuple[str, str]:
    """
    Splits 'MARKET:SYMBOL' into normalized (symbol, market) uppercase strings.
    Example: 'NASDAQ:AAPL' -> ('AAPL', 'NASDAQ'), 'aapl' -> ('AAPL', default_market).
    """
    if not isinstance(raw_symbol, str):
        return "", (default_market or "").strip().upper()
    cleaned = raw_symbol.strip().upper()
    market_clean = (default_market or "").strip().upper()
    if ":" in cleaned:
        parts = cleaned.split(":", 1)
        mkt = parts[0].strip()
        sym = parts[1].strip()
        return sym, mkt or market_clean
    return cleaned, market_clean


def _date_to_utc_timestamp(date_str: str) -> int:
    """Converts YYYY-MM-DD date string into UTC midnight UNIX seconds."""
    dt = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


class YahooFinanceDB:
    def __init__(self, db_path: str = DEFAULT_YAHOO_DB_PATH, busy_timeout: int = 60000):
        self.db_path = db_path
        self.busy_timeout = busy_timeout
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.busy_timeout / 1000.0,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute(f"PRAGMA busy_timeout = {self.busy_timeout};")
            conn.execute("PRAGMA wal_autocheckpoint=10000;")
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tickers (
                    symbol TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    market TEXT NOT NULL DEFAULT '',
                    sector TEXT NOT NULL DEFAULT '',
                    industry TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_prices (
                    symbol TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL DEFAULT 0,
                    quarterly_eps REAL,
                    quarterly_revenue REAL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, date DESC)
                ) WITHOUT ROWID;
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS valuation_history (
                    symbol TEXT NOT NULL,
                    as_of_date TEXT NOT NULL,
                    period_type TEXT NOT NULL DEFAULT '',
                    trailing_pe REAL,
                    forward_pe REAL,
                    pb REAL,
                    ps REAL,
                    peg REAL,
                    ev_ebitda REAL,
                    ev_revenue REAL,
                    market_cap REAL,
                    enterprise_value REAL,
                    dividend_yield REAL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, as_of_date DESC, period_type)
                ) WITHOUT ROWID;
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tickers_sector_industry ON tickers(sector, industry);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tickers_market ON tickers(market);"
            )

    def _execute_write(self, write_op: Any) -> Any:
        max_retries = 5
        base_delay = 0.025
        for attempt in range(max_retries):
            try:
                with self._connection() as conn:
                    conn.execute("BEGIN IMMEDIATE;")
                    try:
                        res = write_op(conn)
                        conn.execute("COMMIT;")
                        return res
                    except Exception:
                        try:
                            conn.execute("ROLLBACK;")
                        except Exception:
                            pass
                        raise
            except sqlite3.OperationalError as exc:
                err_name = getattr(exc, "sqlite_errorname", "") or ""
                is_lock_err = (
                    err_name.startswith(("SQLITE_BUSY", "SQLITE_LOCKED"))
                    or "locked" in str(exc).lower()
                    or "busy" in str(exc).lower()
                )
                if is_lock_err and attempt < max_retries - 1:
                    jitter = random.uniform(0.005, 0.025)
                    time.sleep((base_delay * (2 ** attempt)) + jitter)
                    continue
                raise

    @staticmethod
    def _row_to_ticker(row: sqlite3.Row) -> Dict[str, Any]:
        keys = row.keys()
        return {
            "symbol": row["symbol"],
            "name": row["name"] or "",
            "market": row["market"] or "",
            "sector": row["sector"] or "",
            "industry": row["industry"] or "",
            "active": bool(row["active"]),
            "created_at": str(row["created_at"]) if row["created_at"] is not None else "",
            "price_bars_count": int(row["price_bars_count"] or 0) if "price_bars_count" in keys else 0,
            "min_date": row["min_date"] if "min_date" in keys else None,
            "max_date": row["max_date"] if "max_date" in keys else None,
        }

    def upsert_tickers(self, tickers: List[Union[Dict[str, Any], Tuple]]) -> int:
        """Upserts ticker metadata rows while preserving existing non-empty attributes."""
        if not tickers:
            return 0
        rows = []
        for item in tickers:
            if isinstance(item, dict):
                sym, mkt = parse_market_symbol(
                    str(item.get("symbol", "")),
                    str(item.get("market") or ""),
                )
                if not sym:
                    continue
                name = str(item.get("name") or "").strip()
                sector = str(item.get("sector") or "").strip()
                industry = str(item.get("industry") or "").strip()
                active = 1 if item.get("active", True) else 0
                created_at = str(item.get("created_at") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
                rows.append((sym, name, mkt, sector, industry, active, created_at))
            elif isinstance(item, (tuple, list)) and len(item) >= 1:
                sym, mkt = parse_market_symbol(
                    str(item[0]),
                    str(item[2] if len(item) > 2 and item[2] else ""),
                )
                if not sym:
                    continue
                name = str(item[1] or "").strip() if len(item) > 1 else ""
                sector = str(item[3] or "").strip() if len(item) > 3 else ""
                industry = str(item[4] or "").strip() if len(item) > 4 else ""
                active = 1 if (item[5] if len(item) > 5 else True) else 0
                created_at = (
                    str(item[6])
                    if len(item) > 6 and item[6] is not None
                    else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                )
                rows.append((sym, name, mkt, sector, industry, active, created_at))

        if not rows:
            return 0

        def _write(conn: sqlite3.Connection) -> int:
            conn.executemany(
                """
                INSERT INTO tickers (symbol, name, market, sector, industry, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name = COALESCE(NULLIF(excluded.name, ''), tickers.name),
                    market = COALESCE(NULLIF(excluded.market, ''), tickers.market),
                    sector = COALESCE(NULLIF(excluded.sector, ''), tickers.sector),
                    industry = COALESCE(NULLIF(excluded.industry, ''), tickers.industry),
                    active = excluded.active;
                """,
                rows,
            )
            return len(rows)

        return self._execute_write(_write)

    def get_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        sym, _ = parse_market_symbol(symbol)
        if not sym:
            return None
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT
                    t.symbol, t.name, t.market, t.sector, t.industry, t.active, t.created_at,
                    (SELECT COUNT(*) FROM stock_prices sp WHERE sp.symbol = t.symbol) AS price_bars_count,
                    (SELECT MIN(sp.date) FROM stock_prices sp WHERE sp.symbol = t.symbol) AS min_date,
                    (SELECT MAX(sp.date) FROM stock_prices sp WHERE sp.symbol = t.symbol) AS max_date
                FROM tickers t
                WHERE t.symbol = ?;
                """,
                (sym,),
            ).fetchone()
            return self._row_to_ticker(row) if row else None

    def get_tickers(
        self,
        market: Optional[str] = None,
        sector: Optional[str] = None,
        industry: Optional[str] = None,
        active: Optional[bool] = None,
        active_only: bool = False,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        if market and market.strip():
            clauses.append("UPPER(t.market) = ?")
            params.append(market.strip().upper())
        if sector and sector.strip():
            clauses.append("LOWER(t.sector) = ?")
            params.append(sector.strip().lower())
        if industry and industry.strip():
            clauses.append("LOWER(t.industry) = ?")
            params.append(industry.strip().lower())
        if active is not None:
            clauses.append("t.active = ?")
            params.append(1 if active else 0)
        elif active_only:
            clauses.append("t.active = 1")
        if search and search.strip():
            q = f"%{search.strip().lower()}%"
            clauses.append("(LOWER(t.symbol) LIKE ? OR LOWER(t.name) LIKE ?)")
            params.extend([q, q])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    t.symbol, t.name, t.market, t.sector, t.industry, t.active, t.created_at,
                    COALESCE(sp.price_bars_count, 0) AS price_bars_count,
                    sp.min_date,
                    sp.max_date
                FROM tickers t
                LEFT JOIN (
                    SELECT symbol, COUNT(*) AS price_bars_count, MIN(date) AS min_date, MAX(date) AS max_date
                    FROM stock_prices
                    GROUP BY symbol
                ) sp ON sp.symbol = t.symbol
                {where_sql}
                ORDER BY t.symbol ASC;
                """,
                tuple(params),
            ).fetchall()
            return [self._row_to_ticker(r) for r in rows]

    def get_filter_facets(self) -> Dict[str, List[str]]:
        with self._connection() as conn:
            markets = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT market FROM tickers WHERE market != '' ORDER BY market ASC;"
                ).fetchall()
            ]
            sectors = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT sector FROM tickers WHERE sector != '' ORDER BY sector ASC;"
                ).fetchall()
            ]
            industries = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT industry FROM tickers WHERE industry != '' ORDER BY industry ASC;"
                ).fetchall()
            ]
        return {
            "markets": markets,
            "sectors": sectors,
            "industries": industries,
        }

    def update_ticker(
        self,
        symbol: str,
        active: Optional[bool] = None,
        name: Optional[str] = None,
        market: Optional[str] = None,
        sector: Optional[str] = None,
        industry: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        sym, _ = parse_market_symbol(symbol)
        existing = self.get_ticker(sym)
        if not existing:
            return None

        updates: List[str] = []
        params: List[Any] = []
        if active is not None:
            updates.append("active = ?")
            params.append(1 if active else 0)
        if name is not None:
            updates.append("name = ?")
            params.append(name.strip())
        if market is not None:
            updates.append("market = ?")
            params.append(market.strip().upper())
        if sector is not None:
            updates.append("sector = ?")
            params.append(sector.strip())
        if industry is not None:
            updates.append("industry = ?")
            params.append(industry.strip())

        if updates:
            params.append(sym)
            sql = f"UPDATE tickers SET {', '.join(updates)} WHERE symbol = ?;"
            self._execute_write(lambda conn: conn.execute(sql, tuple(params)))

        return self.get_ticker(sym)

    def delete_ticker(self, symbol: str) -> Dict[str, Any]:
        sym, _ = parse_market_symbol(symbol)
        if not sym:
            return {"symbol": "", "deleted": False, "deleted_prices": 0, "deleted_valuations": 0}

        def _delete(conn: sqlite3.Connection) -> Dict[str, Any]:
            p_cur = conn.execute("DELETE FROM stock_prices WHERE symbol = ?;", (sym,))
            v_cur = conn.execute("DELETE FROM valuation_history WHERE symbol = ?;", (sym,))
            t_cur = conn.execute("DELETE FROM tickers WHERE symbol = ?;", (sym,))
            return {
                "symbol": sym,
                "deleted": t_cur.rowcount > 0,
                "deleted_prices": p_cur.rowcount,
                "deleted_valuations": v_cur.rowcount,
            }

        return self._execute_write(_delete)

    def upsert_stock_prices(self, rows: List[Union[Dict[str, Any], Tuple]]) -> int:
        """Batch upserts daily OHLCV and optional quarterly_eps/quarterly_revenue rows."""
        if not rows:
            return 0
        normalized: List[Tuple[Any, ...]] = []
        seen_symbols = set()

        for r in rows:
            if isinstance(r, dict):
                sym, _ = parse_market_symbol(str(r.get("symbol") or r.get("Ticker") or ""))
                date_val = r.get("date") or r.get("Date")
                date_str = str(date_val)[:10] if date_val is not None else ""
                o = sanitize_float(r.get("open", r.get("Open")))
                h = sanitize_float(r.get("high", r.get("High")))
                l_val = sanitize_float(r.get("low", r.get("Low")))
                c = sanitize_float(r.get("close", r.get("Close")))
                vol = sanitize_int(r.get("volume", r.get("Volume")), default=0)
                q_eps = sanitize_float(r.get("quarterly_eps", r.get("Quarterly_EPS")))
                q_rev = sanitize_float(r.get("quarterly_revenue", r.get("Quarterly_Revenue")))
            else:
                # Tuple order: (symbol, date, open, high, low, close, volume, quarterly_eps, quarterly_revenue)
                sym, _ = parse_market_symbol(str(r[0]))
                date_str = str(r[1])[:10] if r[1] is not None else ""
                o = sanitize_float(r[2])
                h = sanitize_float(r[3])
                l_val = sanitize_float(r[4])
                c = sanitize_float(r[5])
                vol = sanitize_int(r[6], default=0) if len(r) > 6 else 0
                q_eps = sanitize_float(r[7]) if len(r) > 7 else None
                q_rev = sanitize_float(r[8]) if len(r) > 8 else None

            if not sym or not date_str or o is None or h is None or l_val is None or c is None:
                continue
            seen_symbols.add(sym)
            normalized.append((sym, date_str, o, h, l_val, c, vol, q_eps, q_rev))

        if not normalized:
            return 0

        def _write(conn: sqlite3.Connection) -> int:
            conn.executemany(
                "INSERT OR IGNORE INTO tickers (symbol, active) VALUES (?, 1);",
                [(s,) for s in seen_symbols],
            )
            conn.executemany(
                """
                INSERT INTO stock_prices (
                    symbol, date, open, high, low, close, volume, quarterly_eps, quarterly_revenue, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(symbol, date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    quarterly_eps = COALESCE(excluded.quarterly_eps, stock_prices.quarterly_eps),
                    quarterly_revenue = COALESCE(excluded.quarterly_revenue, stock_prices.quarterly_revenue),
                    updated_at = CURRENT_TIMESTAMP;
                """,
                normalized,
            )
            return len(normalized)

        return self._execute_write(_write)

    def get_data_ranges(
        self, symbols: Optional[List[str]] = None
    ) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
        with self._connection() as conn:
            if symbols:
                clean_syms = [parse_market_symbol(s)[0] for s in symbols if s]
                if not clean_syms:
                    return {}
                placeholders = ", ".join("?" for _ in clean_syms)
                rows = conn.execute(
                    f"""
                    SELECT symbol, MIN(date) AS min_d, MAX(date) AS max_d
                    FROM stock_prices
                    WHERE symbol IN ({placeholders})
                    GROUP BY symbol;
                    """,
                    tuple(clean_syms),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT symbol, MIN(date) AS min_d, MAX(date) AS max_d FROM stock_prices GROUP BY symbol;"
                ).fetchall()
            return {r["symbol"]: (r["min_d"], r["max_d"]) for r in rows}

    def get_global_max_date(self) -> Optional[str]:
        with self._connection() as conn:
            row = conn.execute("SELECT MAX(date) AS max_d FROM stock_prices;").fetchone()
            return str(row["max_d"]) if row and row["max_d"] else None

    def get_price_history(
        self, symbol: str, timeframe: str = "D1", limit: int = 1500
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Returns chronologically ascending OHLCV bars for D1, W1, or MN1 and total bar count.
        """
        tf_norm = (timeframe or "D1").strip().upper()
        if tf_norm not in SUPPORTED_YAHOO_TIMEFRAMES:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. Supported: {', '.join(SUPPORTED_YAHOO_TIMEFRAMES)}"
            )
        sym, _ = parse_market_symbol(symbol)
        if not sym or limit <= 0:
            return [], 0

        with self._connection() as conn:
            if tf_norm == "D1":
                total_row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM stock_prices WHERE symbol = ?;", (sym,)
                ).fetchone()
                total_bars = int(total_row["cnt"]) if total_row else 0
                if total_bars == 0:
                    return [], 0
                # Fetch latest `limit` rows in DESC order (fast index scan) and reverse to ASC
                rows = conn.execute(
                    """
                    SELECT date, open, high, low, close, volume
                    FROM stock_prices
                    WHERE symbol = ?
                    ORDER BY date DESC
                    LIMIT ?;
                    """,
                    (sym, limit),
                ).fetchall()
                bars = [
                    {
                        "time": _date_to_utc_timestamp(r["date"]),
                        "date": r["date"],
                        "open": float(r["open"]),
                        "high": float(r["high"]),
                        "low": float(r["low"]),
                        "close": float(r["close"]),
                        "volume": int(r["volume"] or 0),
                    }
                    for r in reversed(rows)
                ]
                return bars, total_bars

            # For W1 or MN1, read chronological daily bars for the symbol and aggregate deterministically
            rows = conn.execute(
                """
                SELECT date, open, high, low, close, volume
                FROM stock_prices
                WHERE symbol = ?
                ORDER BY date ASC;
                """,
                (sym,),
            ).fetchall()

        if not rows:
            return [], 0

        buckets: List[Dict[str, Any]] = []
        current_key: Optional[Tuple[int, int]] = None
        current_bar: Optional[Dict[str, Any]] = None

        for r in rows:
            d_str = r["date"]
            dt = datetime.strptime(d_str[:10], "%Y-%m-%d")
            if tf_norm == "W1":
                iso_yr, iso_wk, _ = dt.isocalendar()
                key = (iso_yr, iso_wk)
            else:
                key = (dt.year, dt.month)

            o = float(r["open"])
            h = float(r["high"])
            l_val = float(r["low"])
            c = float(r["close"])
            vol = int(r["volume"] or 0)

            if key != current_key or current_bar is None:
                if current_bar is not None:
                    buckets.append(current_bar)
                current_key = key
                current_bar = {
                    "time": _date_to_utc_timestamp(d_str),
                    "date": d_str,
                    "open": o,
                    "high": h,
                    "low": l_val,
                    "close": c,
                    "volume": vol,
                }
            else:
                if h > current_bar["high"]:
                    current_bar["high"] = h
                if l_val < current_bar["low"]:
                    current_bar["low"] = l_val
                current_bar["close"] = c
                current_bar["volume"] += vol
                current_bar["date"] = d_str
                current_bar["time"] = _date_to_utc_timestamp(d_str)

        if current_bar is not None:
            buckets.append(current_bar)

        total_resampled = len(buckets)
        return buckets[-limit:], total_resampled

    def upsert_valuation_history(self, rows: List[Union[Dict[str, Any], Tuple]]) -> int:
        """Batch upserts quarterly valuation multiples into valuation_history."""
        if not rows:
            return 0
        normalized: List[Tuple[Any, ...]] = []
        seen_symbols = set()

        for r in rows:
            if isinstance(r, dict):
                sym, _ = parse_market_symbol(str(r.get("symbol", "")))
                as_of = r.get("as_of_date")
                as_of_str = str(as_of)[:10] if as_of is not None else ""
                p_type = str(r.get("period_type") or "").strip()
                t_pe = sanitize_float(r.get("trailing_pe"))
                f_pe = sanitize_float(r.get("forward_pe"))
                pb = sanitize_float(r.get("pb"))
                ps = sanitize_float(r.get("ps"))
                peg = sanitize_float(r.get("peg"))
                ev_ebitda = sanitize_float(r.get("ev_ebitda"))
                ev_rev = sanitize_float(r.get("ev_revenue"))
                mcap = sanitize_float(r.get("market_cap"))
                ev = sanitize_float(r.get("enterprise_value"))
                div_y = sanitize_float(r.get("dividend_yield"))
            else:
                sym, _ = parse_market_symbol(str(r[0]))
                as_of_str = str(r[1])[:10] if r[1] is not None else ""
                p_type = str(r[2] or "").strip()
                t_pe = sanitize_float(r[3]) if len(r) > 3 else None
                f_pe = sanitize_float(r[4]) if len(r) > 4 else None
                pb = sanitize_float(r[5]) if len(r) > 5 else None
                ps = sanitize_float(r[6]) if len(r) > 6 else None
                peg = sanitize_float(r[7]) if len(r) > 7 else None
                ev_ebitda = sanitize_float(r[8]) if len(r) > 8 else None
                ev_rev = sanitize_float(r[9]) if len(r) > 9 else None
                mcap = sanitize_float(r[10]) if len(r) > 10 else None
                ev = sanitize_float(r[11]) if len(r) > 11 else None
                div_y = sanitize_float(r[12]) if len(r) > 12 else None

            if not sym or not as_of_str:
                continue
            seen_symbols.add(sym)
            normalized.append(
                (sym, as_of_str, p_type, t_pe, f_pe, pb, ps, peg, ev_ebitda, ev_rev, mcap, ev, div_y)
            )

        if not normalized:
            return 0

        def _write(conn: sqlite3.Connection) -> int:
            conn.executemany(
                "INSERT OR IGNORE INTO tickers (symbol, active) VALUES (?, 1);",
                [(s,) for s in seen_symbols],
            )
            conn.executemany(
                """
                INSERT INTO valuation_history (
                    symbol, as_of_date, period_type, trailing_pe, forward_pe, pb, ps, peg,
                    ev_ebitda, ev_revenue, market_cap, enterprise_value, dividend_yield, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(symbol, as_of_date, period_type) DO UPDATE SET
                    trailing_pe = excluded.trailing_pe,
                    forward_pe = excluded.forward_pe,
                    pb = excluded.pb,
                    ps = excluded.ps,
                    peg = excluded.peg,
                    ev_ebitda = excluded.ev_ebitda,
                    ev_revenue = excluded.ev_revenue,
                    market_cap = excluded.market_cap,
                    enterprise_value = excluded.enterprise_value,
                    dividend_yield = COALESCE(excluded.dividend_yield, valuation_history.dividend_yield),
                    updated_at = CURRENT_TIMESTAMP;
                """,
                normalized,
            )
            return len(normalized)

        return self._execute_write(_write)

    def get_fundamentals_summary(self, symbol: str) -> Dict[str, Any]:
        """
        Returns ticker metadata, latest valuation snapshot, historical valuation records,
        and distinct quarterly EPS/revenue records for the symbol.
        """
        sym, _ = parse_market_symbol(symbol)
        ticker_info = self.get_ticker(sym)
        with self._connection() as conn:
            val_rows = conn.execute(
                """
                SELECT as_of_date, period_type, trailing_pe, forward_pe, pb, ps, peg,
                       ev_ebitda, ev_revenue, market_cap, enterprise_value, dividend_yield
                FROM valuation_history
                WHERE symbol = ?
                ORDER BY as_of_date DESC, period_type ASC;
                """,
                (sym,),
            ).fetchall()

            valuation_history = [
                {
                    "as_of_date": r["as_of_date"],
                    "period_type": r["period_type"],
                    "trailing_pe": sanitize_float(r["trailing_pe"]),
                    "forward_pe": sanitize_float(r["forward_pe"]),
                    "pb": sanitize_float(r["pb"]),
                    "ps": sanitize_float(r["ps"]),
                    "peg": sanitize_float(r["peg"]),
                    "ev_ebitda": sanitize_float(r["ev_ebitda"]),
                    "ev_revenue": sanitize_float(r["ev_revenue"]),
                    "market_cap": sanitize_float(r["market_cap"]),
                    "enterprise_value": sanitize_float(r["enterprise_value"]),
                    "dividend_yield": sanitize_float(r["dividend_yield"]),
                }
                for r in val_rows
            ]

            earn_rows = conn.execute(
                """
                SELECT MIN(date) AS date, quarterly_eps, quarterly_revenue
                FROM stock_prices
                WHERE symbol = ? AND (quarterly_eps IS NOT NULL OR quarterly_revenue IS NOT NULL)
                GROUP BY quarterly_eps, quarterly_revenue
                ORDER BY date DESC
                LIMIT 40;
                """,
                (sym,),
            ).fetchall()

            quarterly_earnings = [
                {
                    "date": r["date"],
                    "quarterly_eps": sanitize_float(r["quarterly_eps"]),
                    "quarterly_revenue": sanitize_float(r["quarterly_revenue"]),
                }
                for r in earn_rows
            ]

        latest_valuation: Optional[Dict[str, Any]] = None
        if valuation_history:
            # Merge latest available non-null fields from the top valuation records
            base = dict(valuation_history[0])
            for prev in valuation_history[1:4]:
                for k, v in prev.items():
                    if base.get(k) is None and v is not None:
                        base[k] = v
            latest_valuation = base

        return {
            "symbol": sym,
            "ticker": ticker_info,
            "latest_valuation": latest_valuation,
            "valuation_history": valuation_history,
            "quarterly_earnings": quarterly_earnings,
        }

    def get_table_counts(self) -> Dict[str, int]:
        with self._connection() as conn:
            t_cnt = conn.execute("SELECT COUNT(*) FROM tickers;").fetchone()[0]
            p_cnt = conn.execute("SELECT COUNT(*) FROM stock_prices;").fetchone()[0]
            v_cnt = conn.execute("SELECT COUNT(*) FROM valuation_history;").fetchone()[0]
        return {
            "tickers": int(t_cnt),
            "stock_prices": int(p_cnt),
            "valuation_history": int(v_cnt),
        }
