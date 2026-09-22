"""
CLI Ingestion Tool for Historical Market Data (OHLCV).
Provides non-interactive command 'sync-history' supporting --category, --symbol, --timeframe, and --fresh flags.
"""
import argparse
import asyncio
import sys
from typing import List, Optional

from strategy_engine.config import StrategyConfig
from strategy_engine.historical_db import HistoricalRatesDB
from strategy_engine.models import TIMEFRAME_TO_MT5
from strategy_engine.mt5_connector import MT5Connector


def handle_sync_history(args: argparse.Namespace) -> int:
    """Executes historical rates synchronization based on CLI arguments."""
    db = HistoricalRatesDB(db_path=args.db_path) if getattr(args, "db_path", None) else HistoricalRatesDB()
    config = StrategyConfig(mock_mode=True)
    connector = MT5Connector(config)
    ok, err = connector.initialize()
    if not ok:
        print(f"Error: Connector initialization failed: {err}")
        return 1

    timeframe = (getattr(args, "timeframe", None) or "D1").upper()
    if timeframe not in TIMEFRAME_TO_MT5:
        print(f"Error: Unsupported timeframe '{timeframe}'. Supported: {', '.join(TIMEFRAME_TO_MT5.keys())}")
        return 1

    fresh = bool(getattr(args, "fresh", False))
    symbol = getattr(args, "symbol", None)
    category = getattr(args, "category", None)

    if symbol:
        sym = symbol.strip().upper()
        print(f"Synchronizing historical rates for {sym} [timeframe={timeframe}, fresh={fresh}]...")
        bars, count = connector.sync_historical_rates(symbol=sym, timeframe=timeframe, fresh=fresh, db=db)
        if bars is None:
            print(f"Error: Failed to sync rates for {sym} (delisted or unavailable).")
            return 1
        print(f"Successfully synced {len(bars)} bars ({count} committed) for {sym}.")
        return 0

    cat = category or "all"
    print(f"Synchronizing historical rates for category '{cat}' [timeframe={timeframe}, fresh={fresh}]...")
    try:
        assets = connector.get_available_assets(category=cat)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    symbols = [a.symbol for a in assets]
    print(f"Discovered {len(symbols)} assets for category '{cat}'. Starting batch sync...")
    status = asyncio.run(
        connector.sync_historical_batch(
            symbols=symbols,
            timeframe=timeframe,
            fresh=fresh,
            db=db,
        )
    )
    print(
        f"Batch sync finished: {status.completed_assets}/{status.total_assets} completed, "
        f"{status.failed_assets} failed."
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """CLI main entry point for Strategy Engine commands."""
    parser = argparse.ArgumentParser(
        prog="python -m strategy_engine.cli",
        description="Darwin Trader Historical Market Data Ingestion CLI",
    )
    subparsers = parser.add_subparsers(dest="command")

    sync_parser = subparsers.add_parser(
        "sync-history",
        help="Synchronize historical OHLCV market data into local SQLite storage",
    )
    sync_parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Target asset symbol (e.g. AMZN, NVDA, MSFT)",
    )
    sync_parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Asset category filter (all, stocks, etfs, forex)",
    )
    sync_parser.add_argument(
        "--timeframe",
        type=str,
        default="D1",
        help="Historical bar timeframe (default: D1)",
    )
    sync_parser.add_argument(
        "--fresh",
        action="store_true",
        help="Perform fresh sync by wiping cached history and re-downloading from origin",
    )
    sync_parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Custom SQLite database file path (optional)",
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 1

    if args.command == "sync-history":
        return handle_sync_history(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
