"""
SQLite Storage Layer for Historical Market Data (OHLCV).
Operates in SQLite WAL mode with composite primary key (symbol, timeframe, time DESC) WITHOUT ROWID.
Provides upsert semantics (INSERT OR REPLACE) and paginated queries.
"""
from contextlib import contextmanager
import logging
import os
import random
import sqlite3
import time
from typing import List, Optional, Tuple, Union, Dict, Any, Generator
from .models import HistoricalBar

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.join("data", "historical_rates.db")


class HistoricalRatesDB:
    def __init__(self, db_path: str = DEFAULT_DB_PATH, busy_timeout: int = 60000):
        self.db_path = db_path
        self.busy_timeout = busy_timeout
        # Auto-create directory if missing
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

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.busy_timeout / 1000.0,
            isolation_level=None,
        )
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute(f"PRAGMA busy_timeout = {self.busy_timeout};")
        conn.execute("PRAGMA wal_autocheckpoint=10000;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rates (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    time INTEGER NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    tick_volume INTEGER NOT NULL,
                    spread INTEGER NOT NULL,
                    PRIMARY KEY (symbol, timeframe, time DESC)
                ) WITHOUT ROWID;
                """
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
                    sleep_time = (base_delay * (2 ** attempt)) + jitter
                    logger.debug(
                        "Write retry attempt %d/%d due to %s: retrying in %.4fs",
                        attempt + 1,
                        max_retries,
                        err_name or "SQLITE_BUSY",
                        sleep_time,
                    )
                    time.sleep(sleep_time)
                    continue
                logger.debug(
                    "Write failed (%s) on attempt %d/%d",
                    err_name or "SQLITE_BUSY",
                    attempt + 1,
                    max_retries,
                )
                raise

    def insert_rates(self, rates: List[Union[HistoricalBar, Dict[str, Any], Tuple]]) -> int:
        """
        Inserts or replaces rates records using upsert semantics (INSERT OR REPLACE).
        Supports HistoricalBar instances, dictionaries, or tuples.
        Returns count of processed records.
        """
        if not rates:
            return 0

        rows = []
        for r in rates:
            if isinstance(r, HistoricalBar):
                rows.append((
                    r.symbol,
                    r.timeframe,
                    r.time,
                    r.open,
                    r.high,
                    r.low,
                    r.close,
                    r.tick_volume,
                    r.spread,
                ))
            elif isinstance(r, dict):
                rows.append((
                    r["symbol"],
                    r.get("timeframe", "D1"),
                    int(r["time"]),
                    float(r["open"]),
                    float(r["high"]),
                    float(r["low"]),
                    float(r["close"]),
                    int(r.get("tick_volume", 0)),
                    int(r.get("spread", 0)),
                ))
            elif isinstance(r, (tuple, list)):
                rows.append(tuple(r))

        def _insert(conn: sqlite3.Connection) -> int:
            conn.executemany(
                """
                INSERT OR REPLACE INTO rates (
                    symbol, timeframe, time, open, high, low, close, tick_volume, spread
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                rows,
            )
            return len(rows)

        return self._execute_write(_insert)

    def get_latest_timestamp(self, symbol: str, timeframe: str = "D1") -> Optional[int]:
        """
        Returns the latest recorded timestamp (UNIX seconds) for a given symbol and timeframe,
        or None if no records exist.
        """
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT MAX(time) AS max_time FROM rates WHERE symbol = ? AND timeframe = ?;",
                (symbol, timeframe),
            )
            row = cursor.fetchone()
            if row and row["max_time"] is not None:
                return int(row["max_time"])
            return None

    def get_total_bars(self, symbol: str, timeframe: str = "D1") -> int:
        """
        Returns the total number of bars recorded for a given symbol and timeframe.
        """
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) AS cnt FROM rates WHERE symbol = ? AND timeframe = ?;",
                (symbol, timeframe),
            )
            row = cursor.fetchone()
            return int(row["cnt"]) if row else 0

    def get_rates(
        self,
        symbol: str,
        timeframe: str = "D1",
        limit: int = 500,
        offset: int = 0,
        descending: bool = True,
    ) -> Tuple[List[HistoricalBar], int]:
        """
        Returns a paginated list of HistoricalBar objects and the total bar count for the symbol.
        Ordered by time DESC by default (most recent bars first).
        """
        total_bars = self.get_total_bars(symbol, timeframe)
        if total_bars == 0 or limit <= 0 or offset < 0 or offset >= total_bars:
            return [], total_bars

        order_clause = "DESC" if descending else "ASC"
        with self._connection() as conn:
            cursor = conn.execute(
                f"""
                SELECT symbol, timeframe, time, open, high, low, close, tick_volume, spread
                FROM rates
                WHERE symbol = ? AND timeframe = ?
                ORDER BY time {order_clause}
                LIMIT ? OFFSET ?;
                """,
                (symbol, timeframe, limit, offset),
            )
            bars = [
                HistoricalBar(
                    symbol=row["symbol"],
                    timeframe=row["timeframe"],
                    time=row["time"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    tick_volume=row["tick_volume"],
                    spread=row["spread"],
                )
                for row in cursor.fetchall()
            ]
        return bars, total_bars

    def clear_rates(
        self,
        symbol: Optional[Union[str, List[str]]] = None,
        symbols: Optional[Union[List[str], str]] = None,
        timeframe: Optional[str] = None,
    ) -> int:
        """
        Deletes cached rates for given symbol(s) (and optional timeframe).
        Accepts both single 'symbol' and multiple 'symbols' (list or comma-separated string).
        If both symbol and symbols are None, clears rates across all symbols.
        Normalizes 'timeframe': if None or 'ALL' (case-insensitive), omits timeframe clause.
        Returns total number of deleted rows.
        """
        # Backward compatibility for positional clear_rates(sym, "D1")
        if timeframe is None and isinstance(symbols, str):
            symbols_upper = symbols.strip().upper()
            if symbols_upper in ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1", "ALL"):
                timeframe = symbols
                symbols = None

        # Normalize timeframe clause: None or 'ALL' omits timeframe filter
        norm_tf: Optional[str] = None
        if timeframe is not None:
            tf_clean = timeframe.strip().upper()
            if tf_clean != "ALL":
                norm_tf = tf_clean

        # Normalize target symbols
        collected: List[str] = []
        if symbols is not None:
            if isinstance(symbols, str):
                items = [s.strip().upper() for s in symbols.split(",") if s.strip()]
            else:
                items = [str(s).strip().upper() for s in symbols if s and str(s).strip()]
            collected.extend(items)

        if symbol is not None:
            if isinstance(symbol, str):
                sym_items = [s.strip().upper() for s in symbol.split(",") if s.strip()]
            else:
                sym_items = [str(s).strip().upper() for s in symbol if s and str(s).strip()]
            for s_clean in sym_items:
                if s_clean and s_clean not in collected:
                    collected.append(s_clean)

        target_symbols: Optional[List[str]] = None
        if symbols is not None or symbol is not None:
            target_symbols = collected
            # If target list was explicitly provided but is empty, nothing to delete
            if not target_symbols:
                return 0

        query: str
        params: Tuple[Any, ...]
        if target_symbols is None:
            if norm_tf is None:
                query = "DELETE FROM rates;"
                params = ()
            else:
                query = "DELETE FROM rates WHERE timeframe = ?;"
                params = (norm_tf,)
        elif len(target_symbols) == 1:
            if norm_tf is None:
                query = "DELETE FROM rates WHERE symbol = ?;"
                params = (target_symbols[0],)
            else:
                query = "DELETE FROM rates WHERE symbol = ? AND timeframe = ?;"
                params = (target_symbols[0], norm_tf)
        else:
            placeholders = ", ".join("?" for _ in target_symbols)
            if norm_tf is None:
                query = f"DELETE FROM rates WHERE symbol IN ({placeholders});"
                params = tuple(target_symbols)
            else:
                query = f"DELETE FROM rates WHERE symbol IN ({placeholders}) AND timeframe = ?;"
                params = (*target_symbols, norm_tf)

        def _clear(conn: sqlite3.Connection) -> int:
            cursor = conn.execute(query, params)
            return cursor.rowcount

        return self._execute_write(_clear)
