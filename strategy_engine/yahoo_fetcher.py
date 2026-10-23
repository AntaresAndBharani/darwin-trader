"""
Yahoo Finance Market Data, Metadata, Valuation Fetcher & PostgreSQL Migrator.

Provides:
- Market suffix resolution (`format_yahoo_ticker`)
- Daily OHLCV + quarterly earnings extraction (`fetch_ticker_ohlcv_and_earnings`)
- Company profile metadata extraction (`fetch_ticker_metadata`)
- Historical quarterly valuation measures extraction (`fetch_ticker_valuation`)
- Multi-threaded incremental synchronization (`sync_yahoo_tickers`)
- Chunked PostgreSQL-to-SQLite migration (`migrate_postgres_to_sqlite`)
"""
from __future__ import annotations

import concurrent.futures
import datetime
import logging
import time
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from strategy_engine.yahoo_db import (
    YahooFinanceDB,
    parse_market_symbol,
    sanitize_float,
    sanitize_int,
)

logger = logging.getLogger("strategy_engine")

MARKET_SUFFIX_MAP: Dict[str, str] = {
    "LSE": ".L",
    "BME": ".MC",
    "XETR": ".DE",
    "GETTEX": ".DE",
    "MIL": ".MI",
    "SIX": ".SW",
    "TSX": ".TO",
    "OMXSTO": ".ST",
    "EURONEXT": ".PA",
    "LSIN": ".IL",
    "TSE": ".T",
    "HKEX": ".HK",
    "NSE": ".NS",
    "BSE": ".BO",
    "SSE": ".SS",
    "SZSE": ".SZ",
}

_EV_EBITDA_COLS = ("EnterprisesValueEBITDARatio", "EnterpriseValueEBITDARatio")
_EV_REVENUE_COLS = ("EnterprisesValueRevenueRatio", "EnterpriseValueRevenueRatio")


def format_yahoo_ticker(symbol: str, market: Optional[str] = None) -> str:
    """Format a canonical symbol + market into a Yahoo Finance query symbol."""
    clean_sym, parsed_market = parse_market_symbol(symbol, market or "")
    if not clean_sym:
        return ""
    if not parsed_market:
        return clean_sym
    suffix = MARKET_SUFFIX_MAP.get(parsed_market.upper(), "")
    if suffix and not clean_sym.endswith(suffix):
        return f"{clean_sym}{suffix}"
    return clean_sym


def _default_ticker_factory(yahoo_ticker: str) -> Any:
    """Default factory creating a yahooquery.Ticker instance."""
    import yahooquery as yq

    return yq.Ticker(yahoo_ticker)


def _pick_float(row: pd.Series, *names: str) -> Optional[float]:
    """Return the first present, finite numeric value among `names` on `row`."""
    for name in names:
        if name in row.index:
            val = sanitize_float(row.get(name))
            if val is not None:
                return val
    return None


def parse_valuation_measures(symbol: str, data: Any) -> List[Dict[str, Any]]:
    """Map a yahooquery `valuation_measures` DataFrame to `valuation_history` row dicts."""
    clean_sym, _ = parse_market_symbol(symbol)
    if not clean_sym or not isinstance(data, pd.DataFrame) or data.empty:
        return []
    if "asOfDate" not in data.columns:
        return []

    df = data.copy()
    df["asOfDate"] = pd.to_datetime(df["asOfDate"], errors="coerce")
    df = df[df["asOfDate"].notna()].sort_values("asOfDate")

    records: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        period_type = row.get("periodType")
        as_of_dt = row["asOfDate"]
        as_of_str = (
            as_of_dt.strftime("%Y-%m-%d")
            if hasattr(as_of_dt, "strftime")
            else str(as_of_dt)[:10]
        )
        records.append(
            {
                "symbol": clean_sym,
                "as_of_date": as_of_str,
                "period_type": str(period_type).strip() if pd.notna(period_type) else "",
                "trailing_pe": _pick_float(row, "PeRatio"),
                "forward_pe": _pick_float(row, "ForwardPeRatio"),
                "pb": _pick_float(row, "PbRatio"),
                "ps": _pick_float(row, "PsRatio"),
                "peg": _pick_float(row, "PegRatio"),
                "ev_ebitda": _pick_float(row, *_EV_EBITDA_COLS),
                "ev_revenue": _pick_float(row, *_EV_REVENUE_COLS),
                "market_cap": _pick_float(row, "MarketCap"),
                "enterprise_value": _pick_float(row, "EnterpriseValue"),
                "dividend_yield": None,
            }
        )
    return records


def _extract_dividend_yield(ticker_obj: Any, yahoo_ticker: str) -> Optional[float]:
    """Pull current dividend yield from yahooquery `summary_detail`."""
    try:
        summary = ticker_obj.summary_detail
    except Exception:
        return None
    if isinstance(summary, dict):
        info = summary.get(yahoo_ticker)
        if isinstance(info, dict):
            return sanitize_float(info.get("dividendYield"))
    return None


def fetch_ticker_valuation(
    symbol: str,
    market: Optional[str] = None,
    ticker_factory: Optional[Callable[[str], Any]] = None,
) -> List[Dict[str, Any]]:
    """Fetch quarterly valuation history for a symbol from Yahoo Finance."""
    clean_sym, parsed_market = parse_market_symbol(symbol, market or "")
    if not clean_sym:
        return []
    factory = ticker_factory or _default_ticker_factory
    yahoo_ticker = format_yahoo_ticker(clean_sym, parsed_market)
    try:
        stock = factory(yahoo_ticker)
        records = parse_valuation_measures(clean_sym, stock.valuation_measures)
        if records:
            div_yield = _extract_dividend_yield(stock, yahoo_ticker)
            if div_yield is not None:
                records[-1]["dividend_yield"] = div_yield
        return records
    except Exception as exc:
        logger.warning("Failed to fetch valuation measures for %s: %s", clean_sym, exc)
        return []


def fetch_ticker_metadata(
    symbol: str,
    market: Optional[str] = None,
    ticker_factory: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Optional[str]]:
    """Fetch company name, sector, and industry metadata from Yahoo Finance."""
    clean_sym, parsed_market = parse_market_symbol(symbol, market or "")
    factory = ticker_factory or _default_ticker_factory
    yahoo_ticker = format_yahoo_ticker(clean_sym, parsed_market)
    result: Dict[str, Optional[str]] = {
        "symbol": clean_sym,
        "name": None,
        "market": parsed_market or None,
        "sector": None,
        "industry": None,
    }
    if not clean_sym:
        return result

    try:
        stock = factory(yahoo_ticker)
        profile = getattr(stock, "asset_profile", None)
        if isinstance(profile, dict):
            prof_data = profile.get(yahoo_ticker)
            if isinstance(prof_data, dict):
                sector = prof_data.get("sector")
                industry = prof_data.get("industry")
                if sector and isinstance(sector, str):
                    result["sector"] = sector.strip()
                if industry and isinstance(industry, str):
                    result["industry"] = industry.strip()

        quote_type = getattr(stock, "quote_type", None)
        if isinstance(quote_type, dict):
            qt_data = quote_type.get(yahoo_ticker)
            if isinstance(qt_data, dict):
                long_name = qt_data.get("longName") or qt_data.get("shortName")
                if long_name and isinstance(long_name, str):
                    result["name"] = long_name.strip()
                if not result["market"]:
                    exchange = qt_data.get("exchange")
                    if exchange and isinstance(exchange, str):
                        result["market"] = exchange.strip().upper()
    except Exception as exc:
        logger.warning("Failed to fetch metadata for %s: %s", clean_sym, exc)

    return result


def fetch_ticker_ohlcv_and_earnings(
    symbol: str,
    start_date: str,
    end_date: str,
    market: Optional[str] = None,
    include_fundamentals: bool = True,
    ticker_factory: Optional[Callable[[str], Any]] = None,
    max_retries: int = 3,
) -> List[Dict[str, Any]]:
    """
    Fetch daily OHLCV bars (and optional quarterly EPS & revenue) from Yahoo Finance.
    Returns a list of dicts ready for `YahooFinanceDB.upsert_stock_prices`.
    """
    clean_sym, parsed_market = parse_market_symbol(symbol, market or "")
    if not clean_sym:
        return []

    factory = ticker_factory or _default_ticker_factory
    yahoo_ticker = format_yahoo_ticker(clean_sym, parsed_market)

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    if start_dt > end_dt:
        start_dt = end_dt

    start_str = start_dt.strftime("%Y-%m-%d")
    query_end = (end_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    for attempt in range(max(1, max_retries)):
        try:
            stock = factory(yahoo_ticker)
            data = stock.history(start=start_str, end=query_end, interval="1d")
            if isinstance(data, str) or not isinstance(data, pd.DataFrame) or data.empty:
                return []

            df = data.reset_index()
            df = df.rename(
                columns={
                    "date": "Date",
                    "open": "Open",
                    "high": "High",
                    "low": "Low",
                    "close": "Close",
                    "volume": "Volume",
                }
            )
            if "Date" not in df.columns:
                return []

            # Normalize Date to naive Timestamp for clean sorting/merging
            df["Date"] = pd.to_datetime(df["Date"], utc=True, errors="coerce").dt.tz_localize(None)
            df = df.dropna(subset=["Date"]).sort_values("Date")
            if df.empty:
                return []

            df["Quarterly_EPS"] = None
            df["Quarterly_Revenue"] = None

            if include_fundamentals:
                try:
                    quarterly_earnings = getattr(stock, "earning_history", None)
                    if (
                        isinstance(quarterly_earnings, pd.DataFrame)
                        and not quarterly_earnings.empty
                    ):
                        qe = quarterly_earnings.reset_index()
                        if "quarter" in qe.columns and "epsActual" in qe.columns:
                            qe = qe.rename(
                                columns={
                                    "epsActual": "Quarterly_EPS",
                                    "quarter": "Quarter_Date",
                                }
                            )
                            qe["Quarter_Date"] = pd.to_datetime(
                                qe["Quarter_Date"], utc=True, errors="coerce"
                            ).dt.tz_localize(None)
                            qe = qe[["Quarter_Date", "Quarterly_EPS"]].dropna(
                                subset=["Quarter_Date"]
                            )
                            if not qe.empty:
                                df = df.drop(columns=["Quarterly_EPS"])
                                df = pd.merge_asof(
                                    df.sort_values("Date"),
                                    qe.sort_values("Quarter_Date"),
                                    left_on="Date",
                                    right_on="Quarter_Date",
                                    direction="backward",
                                )
                                if "Quarter_Date" in df.columns:
                                    df = df.drop(columns=["Quarter_Date"])

                    financials = getattr(stock, "financial_data", None)
                    if isinstance(financials, dict):
                        fin_data = financials.get(yahoo_ticker) or financials.get(clean_sym)
                        if isinstance(fin_data, dict):
                            df["Quarterly_Revenue"] = sanitize_float(
                                fin_data.get("totalRevenue")
                            )
                except Exception as exc:
                    logger.debug(
                        "Non-fatal error extracting earnings/financials for %s: %s",
                        clean_sym,
                        exc,
                    )

            records: List[Dict[str, Any]] = []
            for _, row in df.iterrows():
                dt_val = row["Date"]
                date_str = (
                    dt_val.strftime("%Y-%m-%d")
                    if hasattr(dt_val, "strftime")
                    else str(dt_val)[:10]
                )
                records.append(
                    {
                        "symbol": clean_sym,
                        "date": date_str,
                        "open": sanitize_float(row.get("Open")),
                        "high": sanitize_float(row.get("High")),
                        "low": sanitize_float(row.get("Low")),
                        "close": sanitize_float(row.get("Close")),
                        "volume": sanitize_int(row.get("Volume")),
                        "quarterly_eps": sanitize_float(row.get("Quarterly_EPS")),
                        "quarterly_revenue": sanitize_float(row.get("Quarterly_Revenue")),
                    }
                )
            return records
        except Exception as exc:
            if attempt < max_retries - 1:
                time.sleep(0.5 * (2**attempt))
            else:
                logger.warning(
                    "Failed to fetch OHLCV for %s after %d attempts: %s",
                    clean_sym,
                    max_retries,
                    exc,
                )
                return []
    return []


def sync_yahoo_tickers(
    db: YahooFinanceDB,
    symbols: Optional[List[str]] = None,
    include_fundamentals: bool = True,
    include_valuation: bool = True,
    include_metadata: bool = True,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    workers: int = 5,
    ticker_factory: Optional[Callable[[str], Any]] = None,
    progress_callback: Optional[Callable[..., None]] = None,
) -> Dict[str, Any]:
    """
    Incrementally synchronize one or more tickers from Yahoo Finance into `YahooFinanceDB`.
    If `symbols` is None, synchronizes all active tickers in `db`.
    """
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    target_end = end_date or today_str

    target_entries: List[Dict[str, Optional[str]]] = []
    if symbols:
        seen = set()
        for raw in symbols:
            clean_sym, parsed_market = parse_market_symbol(raw)
            if not clean_sym or clean_sym in seen:
                continue
            seen.add(clean_sym)
            existing = db.get_ticker(clean_sym)
            if existing is None:
                db.upsert_tickers(
                    [
                        {
                            "symbol": clean_sym,
                            "name": clean_sym,
                            "market": parsed_market,
                            "active": True,
                        }
                    ]
                )
                existing = db.get_ticker(clean_sym)
            elif parsed_market and not existing.get("market"):
                db.update_ticker(clean_sym, market=parsed_market)
                existing = db.get_ticker(clean_sym)
            target_entries.append(
                {
                    "symbol": clean_sym,
                    "market": (existing or {}).get("market") or parsed_market,
                    "sector": (existing or {}).get("sector"),
                    "industry": (existing or {}).get("industry"),
                    "name": (existing or {}).get("name"),
                }
            )
    else:
        active_rows = db.get_tickers(active=True)
        for r in active_rows:
            target_entries.append(
                {
                    "symbol": r["symbol"],
                    "market": r.get("market"),
                    "sector": r.get("sector"),
                    "industry": r.get("industry"),
                    "name": r.get("name"),
                }
            )

    total_symbols = len(target_entries)
    if total_symbols == 0:
        return {
            "total_symbols": 0,
            "completed_symbols": 0,
            "failed_symbols": [],
            "upserted_prices": 0,
            "upserted_valuations": 0,
            "updated_metadata": 0,
        }

    sym_list = [e["symbol"] for e in target_entries if e["symbol"]]
    existing_ranges = db.get_data_ranges(sym_list)

    def _fetch_worker(entry: Dict[str, Optional[str]]) -> Dict[str, Any]:
        sym = entry["symbol"] or ""
        mkt = entry.get("market")
        if start_date:
            sym_start = start_date
        else:
            rng = existing_ranges.get(sym)
            if rng and rng[1]:
                # Overlap by 5 days to catch late adjustments
                max_dt = pd.to_datetime(rng[1]) - pd.Timedelta(days=5)
                sym_start = max_dt.strftime("%Y-%m-%d")
            else:
                sym_start = "2000-01-01"

        prices = fetch_ticker_ohlcv_and_earnings(
            symbol=sym,
            start_date=sym_start,
            end_date=target_end,
            market=mkt,
            include_fundamentals=include_fundamentals,
            ticker_factory=ticker_factory,
        )
        valuations: List[Dict[str, Any]] = []
        if include_valuation:
            valuations = fetch_ticker_valuation(
                symbol=sym,
                market=mkt,
                ticker_factory=ticker_factory,
            )

        meta: Optional[Dict[str, Optional[str]]] = None
        needs_meta = include_metadata and (
            not entry.get("sector")
            or entry.get("sector") == "Unknown"
            or not entry.get("industry")
            or entry.get("industry") == "Unknown"
            or not entry.get("name")
            or entry.get("name") == sym
        )
        if needs_meta:
            meta = fetch_ticker_metadata(
                symbol=sym,
                market=mkt,
                ticker_factory=ticker_factory,
            )

        return {
            "symbol": sym,
            "prices": prices,
            "valuations": valuations,
            "meta": meta,
        }

    completed_symbols = 0
    failed_symbols: List[str] = []
    upserted_prices = 0
    upserted_valuations = 0
    updated_metadata = 0

    max_workers = max(1, min(int(workers or 5), 32))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_fetch_worker, entry): entry["symbol"] or ""
            for entry in target_entries
        }
        for future in concurrent.futures.as_completed(future_map):
            sym = future_map[future]
            try:
                res = future.result()
                prices = res["prices"]
                valuations = res["valuations"]
                meta = res["meta"]

                if meta and (meta.get("sector") or meta.get("industry") or meta.get("name")):
                    db.update_ticker(
                        sym,
                        name=meta.get("name"),
                        market=meta.get("market"),
                        sector=meta.get("sector"),
                        industry=meta.get("industry"),
                    )
                    updated_metadata += 1

                if prices:
                    upserted_prices += db.upsert_stock_prices(prices)
                if valuations:
                    upserted_valuations += db.upsert_valuation_history(valuations)

                if not prices and not valuations and sym not in existing_ranges:
                    failed_symbols.append(sym)
                else:
                    completed_symbols += 1
            except Exception as exc:
                logger.warning("Worker failed for %s: %s", sym, exc)
                failed_symbols.append(sym)

            if progress_callback:
                progress_callback(
                    symbol=sym,
                    completed=completed_symbols,
                    failed=len(failed_symbols),
                    total=total_symbols,
                )

    return {
        "total_symbols": total_symbols,
        "completed_symbols": completed_symbols,
        "failed_symbols": sorted(failed_symbols),
        "upserted_prices": upserted_prices,
        "upserted_valuations": upserted_valuations,
        "updated_metadata": updated_metadata,
    }


def migrate_postgres_to_sqlite(
    db: YahooFinanceDB,
    pg_host: str = "localhost",
    pg_port: int = 5433,
    pg_db: str = "fractanomicsdb",
    pg_user: str = "postgres",
    pg_pass: str = "postgres",
    chunk_size: int = 50000,
    conn_factory: Optional[Callable[..., Any]] = None,
    progress_callback: Optional[Callable[..., None]] = None,
) -> Dict[str, int]:
    """
    Migrate `tickers`, `stock_prices`, and `valuation_history` from PostgreSQL
    (`fractanomicsdb`) into the local SQLite `YahooFinanceDB`.
    """
    if conn_factory is None:
        import psycopg2

        pg_conn = psycopg2.connect(
            host=pg_host,
            port=pg_port,
            database=pg_db,
            user=pg_user,
            password=pg_pass,
        )
    else:
        pg_conn = conn_factory(
            host=pg_host,
            port=pg_port,
            database=pg_db,
            user=pg_user,
            password=pg_pass,
        )

    migrated_tickers = 0
    migrated_prices = 0
    migrated_valuations = 0

    try:
        # 1. Migrate tickers
        with pg_conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol, name, market, sector, industry, active, created_at
                FROM tickers
                ORDER BY symbol ASC
                """
            )
            ticker_rows = cur.fetchall()
            ticker_dicts = [
                {
                    "symbol": r[0],
                    "name": r[1],
                    "market": r[2],
                    "sector": r[3],
                    "industry": r[4],
                    "active": bool(r[5]) if r[5] is not None else True,
                    "created_at": (
                        r[6].strftime("%Y-%m-%d %H:%M:%S")
                        if hasattr(r[6], "strftime")
                        else (str(r[6]) if r[6] is not None else None)
                    ),
                }
                for r in ticker_rows
            ]
            migrated_tickers = db.upsert_tickers(ticker_dicts)
            if progress_callback:
                progress_callback(stage="tickers", count=migrated_tickers)

        # 2. Migrate stock_prices in chunks
        with pg_conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol, date, open, high, low, close, volume,
                       quarterly_eps, quarterly_revenue, updated_at
                FROM stock_prices
                """
            )
            while True:
                rows = cur.fetchmany(chunk_size)
                if not rows:
                    break
                price_dicts = [
                    {
                        "symbol": r[0],
                        "date": (
                            r[1].strftime("%Y-%m-%d")
                            if hasattr(r[1], "strftime")
                            else str(r[1])[:10]
                        ),
                        "open": sanitize_float(r[2]),
                        "high": sanitize_float(r[3]),
                        "low": sanitize_float(r[4]),
                        "close": sanitize_float(r[5]),
                        "volume": sanitize_int(r[6]),
                        "quarterly_eps": sanitize_float(r[7]),
                        "quarterly_revenue": sanitize_float(r[8]),
                        "updated_at": (
                            r[9].strftime("%Y-%m-%d %H:%M:%S")
                            if hasattr(r[9], "strftime")
                            else (str(r[9]) if r[9] is not None else None)
                        ),
                    }
                    for r in rows
                ]
                migrated_prices += db.upsert_stock_prices(price_dicts)
                if progress_callback:
                    progress_callback(stage="stock_prices", count=migrated_prices)

        # 3. Migrate valuation_history in chunks
        with pg_conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol, as_of_date, period_type, trailing_pe, forward_pe,
                       pb, ps, peg, ev_ebitda, ev_revenue, market_cap,
                       enterprise_value, dividend_yield, updated_at
                FROM valuation_history
                """
            )
            while True:
                rows = cur.fetchmany(chunk_size)
                if not rows:
                    break
                val_dicts = [
                    {
                        "symbol": r[0],
                        "as_of_date": (
                            r[1].strftime("%Y-%m-%d")
                            if hasattr(r[1], "strftime")
                            else str(r[1])[:10]
                        ),
                        "period_type": str(r[2] or "").strip(),
                        "trailing_pe": sanitize_float(r[3]),
                        "forward_pe": sanitize_float(r[4]),
                        "pb": sanitize_float(r[5]),
                        "ps": sanitize_float(r[6]),
                        "peg": sanitize_float(r[7]),
                        "ev_ebitda": sanitize_float(r[8]),
                        "ev_revenue": sanitize_float(r[9]),
                        "market_cap": sanitize_float(r[10]),
                        "enterprise_value": sanitize_float(r[11]),
                        "dividend_yield": sanitize_float(r[12]),
                        "updated_at": (
                            r[13].strftime("%Y-%m-%d %H:%M:%S")
                            if hasattr(r[13], "strftime")
                            else (str(r[13]) if r[13] is not None else None)
                        ),
                    }
                    for r in rows
                ]
                migrated_valuations += db.upsert_valuation_history(val_dicts)
                if progress_callback:
                    progress_callback(
                        stage="valuation_history", count=migrated_valuations
                    )
    finally:
        try:
            pg_conn.close()
        except Exception:
            pass

    return {
        "tickers": migrated_tickers,
        "stock_prices": migrated_prices,
        "valuation_history": migrated_valuations,
    }
