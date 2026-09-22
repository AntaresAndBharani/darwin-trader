"""
CLI Ingestion Tool for Historical Market Data (OHLCV).
Provides non-interactive command 'sync-history' supporting --category, --symbol, --timeframe, and --fresh flags.
"""
import argparse
import asyncio
import sys
from typing import List, Optional

from strategy_engine.config import StrategyConfig
from strategy_engine.committee_calculator import calculate_committee_context
from strategy_engine.historical_db import HistoricalRatesDB
from strategy_engine.models import (
    TIMEFRAME_TO_MT5,
    HistoricalDataNotFoundError,
    CommitteeContext,
)
from strategy_engine.mt5_connector import MT5Connector


def format_committee_markdown(
    context: CommitteeContext,
    mode: str = "entry",
    direction: str = "long",
    entry_price: Optional[float] = None,
) -> str:
    """Formats CommitteeContext into a deterministic Technical Context Briefing markdown document."""
    lines = [
        f"# Technical Context Briefing: {context.symbol}",
        f"- **Current Price:** ${context.current_price:.2f} (Timestamp: {context.as_of_time})",
        f"- **Evaluated Bars:** D1: {context.d1_bars_count} bars, H1: {context.h1_bars_count} bars",
        f"- **Data Health:** {', '.join(context.data_flags) if context.data_flags else 'PRISTINE'}",
        "",
        "## Moving Averages & Trend",
        f"- **EMA 20:** ${context.ema_20:.2f}" if context.ema_20 is not None else "- **EMA 20:** N/A",
        f"- **EMA 50:** ${context.ema_50:.2f}" if context.ema_50 is not None else "- **EMA 50:** N/A",
        f"- **EMA 200:** ${context.ema_200:.2f}" if context.ema_200 is not None else "- **EMA 200:** None (Degraded)",
        "",
        "## Momentum & Volatility",
        f"- **RSI (14):** {context.rsi_14:.2f}" if context.rsi_14 is not None else "- **RSI (14):** N/A",
        f"- **ATR (14):** ${context.atr_14:.2f}" if context.atr_14 is not None else "- **ATR (14):** N/A",
        "",
        "## Key Structural Levels",
        f"- **Swing Ceiling:** ${context.swing_ceiling:.2f}" if context.swing_ceiling is not None else "- **Swing Ceiling:** N/A",
        f"- **Swing Floor:** ${context.swing_floor:.2f}" if context.swing_floor is not None else "- **Swing Floor:** N/A",
        f"- **Recent Swing Highs:** {', '.join(f'${x:.2f}' for x in context.swing_highs[-5:]) if context.swing_highs else 'None'}",
        f"- **Recent Swing Lows:** {', '.join(f'${x:.2f}' for x in context.swing_lows[-5:]) if context.swing_lows else 'None'}",
        "",
        "## Dominant Fibonacci Grid (60-bar Anchor)",
    ]
    grid = context.fibonacci_grid
    if grid:
        lines.extend([
            f"- **Anchor High:** ${grid.get('anchor_high', 0.0):.2f}",
            f"- **Anchor Low:** ${grid.get('anchor_low', 0.0):.2f}",
            f"- **Fib 0.236:** ${grid.get('0.236', 0.0):.2f}",
            f"- **Fib 0.382:** ${grid.get('0.382', 0.0):.2f}",
            f"- **Fib 0.500:** ${grid.get('0.5', grid.get('0.500', 0.0)):.2f}",
            f"- **Fib 0.618:** ${grid.get('0.618', 0.0):.2f}",
            f"- **Fib 0.786:** ${grid.get('0.786', 0.0):.2f}",
            f"- **Ext 1.272:** ${grid.get('1.272', 0.0):.2f}",
            f"- **Ext 1.618:** ${grid.get('1.618', 0.0):.2f}",
        ])
    else:
        lines.append("- N/A")

    lines.extend([
        "",
        "## Volume Profile (50-bin Typical Price)",
        f"- **VPOC (Point of Control):** ${context.vpoc:.2f}" if context.vpoc is not None else "- **VPOC:** N/A",
        f"- **High Volume Nodes (HVN):** {', '.join(f'${x:.2f}' for x in context.hvn[:5]) if context.hvn else 'None'}",
        f"- **Low Volume Nodes (LVN):** {', '.join(f'${x:.2f}' for x in context.lvn[:5]) if context.lvn else 'None'}",
        "",
        f"## Benchmark Comparison ({context.benchmark_symbol})",
        f"- **Beta:** {context.benchmark_beta:.2f}" if context.benchmark_beta is not None else "- **Beta:** None (Insufficient overlap or uncached)",
        f"- **Relative Strength:** {context.relative_strength:.4f}" if context.relative_strength is not None else "- **Relative Strength:** None",
        "",
        "## Execution Request Context",
        f"- **Mode:** {mode.upper()}",
        f"- **Direction:** {direction.upper()}",
        f"- **Target Entry Price:** ${entry_price:.2f}" if entry_price is not None else "- **Target Entry Price:** Market / Unspecified",
    ])
    return "\n".join(lines)


def handle_committee(args: argparse.Namespace) -> int:
    """Executes deterministic technical context calculation for committee deliberation."""
    raw_symbol = getattr(args, "symbol", None) or getattr(args, "symbol_opt", None)
    if not raw_symbol:
        print("Error: Target symbol is required. Usage: python -m strategy_engine.cli committee <SYMBOL>")
        return 1

    symbol = raw_symbol.strip().upper()
    db_path = getattr(args, "db_path", None)
    db = HistoricalRatesDB(db_path=db_path) if db_path else HistoricalRatesDB()
    benchmark_sym = (getattr(args, "benchmark", None) or "SPY").strip().upper()
    mode = (getattr(args, "mode", None) or "entry").lower()
    direction = (getattr(args, "direction", None) or "long").lower()
    entry_price = getattr(args, "entry_price", None)
    out_format = (getattr(args, "format", None) or "markdown").lower()

    try:
        context = calculate_committee_context(
            symbol=symbol,
            db=db,
            benchmark_symbol=benchmark_sym,
        )
    except HistoricalDataNotFoundError:
        print(f"Error: No historical rates found for symbol '{symbol}' in database.")
        print(f"Please execute `python -m strategy_engine.cli sync-history --symbol {symbol}` to cache historical data first.")
        return 1
    except Exception as exc:
        print(f"Error: Failed to compute committee context for '{symbol}': {exc}")
        return 1

    if out_format == "json":
        print(context.model_dump_json(indent=2))
        return 0

    print(format_committee_markdown(context, mode=mode, direction=direction, entry_price=entry_price))
    return 0


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
        description="Darwin Trader CLI Tools",
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

    committee_parser = subparsers.add_parser(
        "committee",
        help="Deterministic technical calculation briefing for Trading Committee",
    )
    committee_parser.add_argument(
        "symbol",
        type=str,
        nargs="?",
        default=None,
        help="Target asset symbol (e.g. AAPL, NVDA, MSFT)",
    )
    committee_parser.add_argument(
        "--symbol",
        dest="symbol_opt",
        type=str,
        default=None,
        help="Target asset symbol (optional named flag)",
    )
    committee_parser.add_argument(
        "--mode",
        type=str,
        choices=["entry", "exit"],
        default="entry",
        help="Evaluation mode: 'entry' (New Entry) or 'exit' (Position Audit) (default: entry)",
    )
    committee_parser.add_argument(
        "--direction",
        type=str,
        choices=["long", "short"],
        default="long",
        help="Evaluation direction: 'long' or 'short' (default: long)",
    )
    committee_parser.add_argument(
        "--entry-price",
        type=float,
        default=None,
        help="Proposed or existing position entry price (optional)",
    )
    committee_parser.add_argument(
        "--format",
        type=str,
        choices=["markdown", "json"],
        default="markdown",
        help="Output format: 'markdown' (Technical Context Briefing) or 'json' (CommitteeContext JSON) (default: markdown)",
    )
    committee_parser.add_argument(
        "--benchmark",
        type=str,
        default="SPY",
        help="Benchmark symbol for beta and relative strength (default: SPY)",
    )
    committee_parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Custom SQLite database file path (optional)",
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 1

    if args.command == "sync-history":
        return handle_sync_history(args)
    elif args.command == "committee":
        return handle_committee(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
