"""
SQLite Storage Layer for Historical Market Data (OHLCV).
Operates in SQLite WAL mode with composite primary key (symbol, timeframe, time DESC) WITHOUT ROWID.
Provides upsert semantics (INSERT OR REPLACE) and paginated queries.
"""
import os
import sqlite3
from typing import List, Optional, Tuple, Union, Dict, Any
from .models import HistoricalBar


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

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=self.busy_timeout / 1000.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout};")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
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

        with self._get_connection() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO rates (
                    symbol, timeframe, time, open, high, low, close, tick_volume, spread
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                rows,
            )
        return len(rows)

    def get_latest_timestamp(self, symbol: str, timeframe: str = "D1") -> Optional[int]:
        """
        Returns the latest recorded timestamp (UNIX seconds) for a given symbol and timeframe,
        or None if no records exist.
        """
        with self._get_connection() as conn:
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
        with self._get_connection() as conn:
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
        with self._get_connection() as conn:
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

    def clear_rates(self, symbol: Optional[str] = None, timeframe: Optional[str] = None) -> int:
        """
        Deletes cached rates for a given symbol (and optional timeframe).
        If symbol is None, clears all rates in the database.
        Returns number of deleted rows.
        """
        with self._get_connection() as conn:
            if symbol is None:
                cursor = conn.execute("DELETE FROM rates;")
            elif timeframe is None:
                cursor = conn.execute("DELETE FROM rates WHERE symbol = ?;", (symbol,))
            else:
                cursor = conn.execute(
                    "DELETE FROM rates WHERE symbol = ? AND timeframe = ?;",
                    (symbol, timeframe),
                )
            return cursor.rowcount
