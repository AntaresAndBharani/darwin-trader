"""
CLI Ingestion, Purge, and Analysis Tools for Historical Market Data (OHLCV).
Provides non-interactive commands 'sync-history', 'purge-history', and 'committee'.
"""
import argparse
import asyncio
import logging
import sys
import time
from typing import List, Optional, Union

try:
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )
    from rich.console import Console
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from strategy_engine.config import StrategyConfig
from strategy_engine.committee_calculator import calculate_committee_context
from strategy_engine.historical_db import HistoricalRatesDB
from strategy_engine.models import (
    TIMEFRAME_TO_MT5,
    HistoricalDataNotFoundError,
    CommitteeContext,
)
from strategy_engine.mt5_connector import MT5Connector

logger = logging.getLogger("strategy_engine")


def setup_cli_logging(level: int = logging.INFO, stream=None) -> logging.Logger:
    """Configures the strategy_engine logger idempotently on stderr."""
    eng_logger = logging.getLogger("strategy_engine")
    eng_logger.setLevel(level)
    eng_logger.propagate = False

    for h in list(eng_logger.handlers):
        eng_logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    target_stream = stream if stream is not None else sys.stderr
    handler = logging.StreamHandler(target_stream)
    handler.setLevel(level)
    logging.addLevelName(logging.WARNING, "WARN")
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    eng_logger.addHandler(handler)
    return eng_logger


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

    logger.debug("Computing committee context for symbol '%s' (benchmark: %s, mode: %s, direction: %s)", symbol, benchmark_sym, mode, direction)
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

    logger.debug("Successfully computed committee context for %s (D1 bars: %d, H1 bars: %d)", symbol, context.d1_bars_count, context.h1_bars_count)

    if out_format == "json":
        print(context.model_dump_json(indent=2))
        return 0

    print(format_committee_markdown(context, mode=mode, direction=direction, entry_price=entry_price))
    return 0


def parse_symbols(raw: Union[None, str, List[str]]) -> List[str]:
    """Normalizes symbol argument (string, comma-separated, whitespace, or list) into a list of uppercase symbols."""
    if not raw:
        return []
    if isinstance(raw, str):
        items = [raw]
    else:
        items = raw
    result = []
    for item in items:
        parts = [p.strip().upper() for part in item.split(",") for p in part.split() if p.strip()]
        result.extend(parts)
    seen = set()
    deduped = []
    for s in result:
        if s and s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


def handle_sync_history(args: argparse.Namespace) -> int:
    """Executes historical rates synchronization based on CLI arguments via unified batch worker pool."""
    # 1. Fast-fail validation on worker count (range: 1 - 50)
    workers = getattr(args, "workers", 10)
    if workers is None:
        workers = 10
    if not isinstance(workers, int) or workers < 1 or workers > 50:
        print(f"Error: --workers must be an integer between 1 and 50 (got {workers}).")
        return 1

    # 2. Fast-fail validation on empty or whitespace-only --symbol input
    raw_symbol = getattr(args, "symbol", None)
    symbols: Optional[List[str]] = None
    if raw_symbol is not None:
        symbols = parse_symbols(raw_symbol)
        if not symbols:
            print("Error: No valid symbols provided.")
            return 1

    # 3. Timeframe validation and canonical expansion
    raw_tf = (getattr(args, "timeframe", None) or "D1").strip().upper()
    canonical_timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]
    if raw_tf == "ALL":
        target_timeframes = list(canonical_timeframes)
    elif raw_tf in TIMEFRAME_TO_MT5:
        target_timeframes = [raw_tf]
    else:
        supported = list(TIMEFRAME_TO_MT5.keys()) + ["ALL"]
        print(f"Error: Unsupported timeframe '{raw_tf}'. Supported: {', '.join(supported)}")
        return 1

    # 4. Mode resolution (--live / --mock mutually exclusive group)
    live_flag = getattr(args, "live", False)
    mock_flag = getattr(args, "mock", False)
    if live_flag and mock_flag:
        print("Error: --live and --mock are mutually exclusive.")
        return 2

    if live_flag:
        config = StrategyConfig(mock_mode=False)
    elif mock_flag:
        config = StrategyConfig(mock_mode=True)
    else:
        config = StrategyConfig()

    # 5. Initialize connector and database
    db = HistoricalRatesDB(db_path=args.db_path) if getattr(args, "db_path", None) else HistoricalRatesDB()
    connector = MT5Connector(config)
    ok, err = connector.initialize()
    if not ok:
        print(f"Error: Connector initialization failed: {err}")
        return 1

    # 6. Resolve symbols if not specified via --symbol
    if symbols is None:
        cat = (getattr(args, "category", None) or "stocks").lower()
        try:
            assets = connector.get_available_assets(category=cat)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1
        symbols = [a.symbol for a in assets]
        if not symbols:
            print(f"Error: No assets found for category '{cat}'.")
            return 1

    fresh = bool(getattr(args, "fresh", False))
    tf_str = "all" if raw_tf == "ALL" else ", ".join(target_timeframes)
    logger.info(
        "Synchronizing historical rates for %d symbol(s) [timeframes=%s, workers=%d, fresh=%s]...",
        len(symbols),
        tf_str,
        workers,
        fresh,
    )

    is_verbose = getattr(args, "verbose", False)
    is_quiet = getattr(args, "quiet", False)
    force_term = getattr(args, "force_terminal", False)
    is_tty = force_term or (hasattr(sys.stderr, "isatty") and sys.stderr.isatty())
    use_rich = HAS_RICH and is_tty and not is_quiet

    progress = None
    progress_task = None
    overall_start = time.perf_counter()
    last_decile = 0

    if use_rich:
        console = Console(file=sys.stderr, force_terminal=True)
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("• {task.completed}/{task.total} completed"),
            TextColumn("({task.fields[remaining]} remaining)"),
            TimeElapsedColumn(),
            TextColumn("• {task.fields[rate]:.1f} bars/s"),
            console=console,
            transient=False,
        )
        progress_task = progress.add_task(
            "Syncing",
            total=len(symbols),
            remaining=len(symbols),
            rate=0.0,
        )
        progress.start()

    def progress_callback(**kwargs):
        nonlocal last_decile
        sym = kwargs.get("symbol", "")
        success = kwargs.get("success", True)
        bars = kwargs.get("bars", 0)
        elapsed = kwargs.get("elapsed", 0.0)
        completed = kwargs.get("completed_assets", 0)
        failed = kwargs.get("failed_assets", 0)
        total = kwargs.get("total_assets", len(symbols))
        total_b = kwargs.get("total_bars", 0)

        done = completed + failed
        rem = max(0, total - done)
        now_elapsed = time.perf_counter() - overall_start
        rate = total_b / now_elapsed if now_elapsed > 0 else 0.0

        if use_rich and progress is not None and progress_task is not None:
            progress.update(
                progress_task,
                completed=completed,
                remaining=rem,
                rate=rate,
            )
            if success:
                progress.console.print(f"• {sym}: {bars} bars [{tf_str}] ({elapsed:.2f}s)")
        else:
            if is_verbose and success:
                logger.debug("• %s: %d bars [%s] (%.2fs)", sym, bars, tf_str, elapsed)

            if not is_quiet and total > 0:
                current_decile = (done * 10) // total
                if current_decile > last_decile:
                    for d in range(last_decile + 1, min(current_decile, 10) + 1):
                        pct = d * 10
                        logger.info("Sync progress milestone: %d%% (%d/%d assets)", pct, done, total)
                    last_decile = current_decile

    # 7. Unconditionally dispatch to batch worker pool
    try:
        status = asyncio.run(
            connector.sync_historical_batch(
                symbols=symbols,
                timeframes=target_timeframes,
                fresh=fresh,
                workers=workers,
                db=db,
                progress_callback=progress_callback,
            )
        )
    finally:
        if use_rich and progress is not None:
            progress.stop()

    if not use_rich and not is_quiet and len(symbols) > 0:
        if last_decile < 10:
            logger.info("Sync progress milestone: 100% (%d/%d assets)", len(symbols), len(symbols))
            last_decile = 10

    # 8. Deterministic Exit Codes Contract: 0 = All OK, 1 = Fatal/All Failed, 2 = Partial Failure
    if status.failed_assets > 0 and status.completed_assets == 0:
        print(f"Error: Batch sync failed (0/{status.total_assets}). Failed symbols: {', '.join(status.failed_symbols)}")
        return 1
    elif status.failed_assets > 0:
        print(f"Warning: Partial sync completed ({status.completed_assets}/{status.total_assets}). Failed symbols: {', '.join(status.failed_symbols)}")
        return 2
    else:
        print(f"Batch sync finished: {status.completed_assets}/{status.total_assets} completed, 0 failed. Total bars committed: {status.total_bars}.")
        return 0


def handle_purge_history(args: argparse.Namespace) -> int:
    """Executes historical rates purge based on CLI arguments with confirmation and safety guards."""
    raw_symbol = getattr(args, "symbol", None)
    all_flag = bool(getattr(args, "all", False))
    raw_category = getattr(args, "category", None)

    # 1. Fast-fail guard: Must specify at least one target (--symbol, --category, or --all)
    if not all_flag and raw_symbol is None and raw_category is None:
        print("Error: Target required. Please specify --symbol, --category, or --all.")
        return 1

    # 2. Fast-fail validation on empty or whitespace-only --symbol input
    symbols: Optional[List[str]] = None
    if raw_symbol is not None:
        symbols = parse_symbols(raw_symbol)
        if not symbols:
            print("Error: No valid symbols provided.")
            return 1

    if not all_flag and not symbols and raw_category is None:
        print("Error: Target required. Please specify --symbol, --category, or --all.")
        return 1

    # 3. Category resolution
    if not all_flag and symbols is None and raw_category is not None:
        cat = raw_category.strip().lower()
        config = StrategyConfig()
        connector = MT5Connector(config)
        ok, err = connector.initialize()
        if not ok:
            print(f"Error: Connector initialization failed: {err}")
            return 1
        try:
            assets = connector.get_available_assets(category=cat)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1
        symbols = [a.symbol for a in assets]
        if not symbols:
            print(f"Error: No assets found for category '{cat}'.")
            return 1

    # 4. Timeframe validation and normalization
    raw_tf = (getattr(args, "timeframe", None) or "all").strip().upper()
    if raw_tf == "ALL":
        target_tf = None
    elif raw_tf in TIMEFRAME_TO_MT5:
        target_tf = raw_tf
    else:
        supported = list(TIMEFRAME_TO_MT5.keys()) + ["ALL"]
        print(f"Error: Unsupported timeframe '{raw_tf}'. Supported: {', '.join(supported)}")
        return 1

    # 5. Interactive confirmation & non-interactive safety guards
    yes_flag = bool(getattr(args, "yes", False))
    if not yes_flag:
        is_interactive = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
        if not is_interactive:
            print("Error: Confirmation required. Use -y or --yes in non-interactive environments.")
            return 1

        # Interactive confirmation prompt
        if all_flag:
            prompt_msg = "Are you sure you want to purge ALL historical data from the database? [y/N]: "
        elif symbols:
            sym_desc = ", ".join(symbols)
            tf_desc = f" [{raw_tf}]" if target_tf else " [all timeframes]"
            prompt_msg = f"Are you sure you want to purge historical data for {sym_desc}{tf_desc}? [y/N]: "
        else:
            prompt_msg = "Are you sure you want to proceed with database purge? [y/N]: "

        try:
            user_input = input(prompt_msg).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nOperation cancelled by user.")
            return 0

        if user_input not in ("y", "yes"):
            print("Operation cancelled by user.")
            return 0

    # 6. Database purge execution
    db_path = getattr(args, "db_path", None)
    db = HistoricalRatesDB(db_path=db_path) if db_path else HistoricalRatesDB()

    target_desc = "ALL symbols" if all_flag else (", ".join(symbols) if symbols else "None")
    tf_desc = target_tf if target_tf else "all"
    logger.info("Purging historical rates: db=%s, target=%s, timeframe=%s", db.db_path, target_desc, tf_desc)
    start_t = time.perf_counter()

    if all_flag:
        deleted = db.clear_rates(timeframe=target_tf)
    else:
        deleted = db.clear_rates(symbols=symbols, timeframe=target_tf)

    purge_duration = time.perf_counter() - start_t
    logger.info("Purge completed in %.4fs (deleted %d records)", purge_duration, deleted)

    print(f"Successfully purged {deleted} historical rate record(s).")
    return 0


def main(argv: Optional[List[str]] = None, force_terminal: Optional[bool] = None) -> int:
    """CLI main entry point for Strategy Engine commands."""
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Enable verbose debug logging",
    )
    parent_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Suppress informational progress logs",
    )

    parser = argparse.ArgumentParser(
        prog="python -m strategy_engine.cli",
        description="Darwin Trader CLI Tools",
        parents=[parent_parser],
    )
    subparsers = parser.add_subparsers(dest="command")

    sync_parser = subparsers.add_parser(
        "sync-history",
        parents=[parent_parser],
        help="Synchronize historical OHLCV market data into local SQLite storage",
    )
    sync_parser.add_argument(
        "--symbol",
        type=str,
        action="append",
        default=None,
        help="Target asset symbol (e.g. AMZN, NVDA, MSFT or comma-separated AAPL,MSFT)",
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
        help="Historical bar timeframe (default: D1, or 'all')",
    )
    sync_parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Concurrency limit (default: 10, range: 1-50)",
    )
    sync_parser.add_argument(
        "--fresh",
        action="store_true",
        help="Perform fresh sync by wiping cached history and re-downloading from origin",
    )
    mode_group = sync_parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Execute against live MT5 terminal",
    )
    mode_group.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Execute against mock MT5 simulation",
    )
    sync_parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Custom SQLite database file path (optional)",
    )
    sync_parser.add_argument(
        "--force-terminal",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS,
    )

    purge_parser = subparsers.add_parser(
        "purge-history",
        parents=[parent_parser],
        help="Purge historical OHLCV market data from local SQLite storage",
    )
    purge_parser.add_argument(
        "--symbol",
        type=str,
        action="append",
        default=None,
        help="Target asset symbol(s) to purge (e.g. AMZN, NVDA or comma-separated AAPL,MSFT)",
    )
    purge_parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Asset category filter (all, stocks, etfs, forex)",
    )
    purge_parser.add_argument(
        "--timeframe",
        type=str,
        default="all",
        help="Target timeframe to purge (default: all)",
    )
    purge_parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Purge entire database across all symbols and timeframes",
    )
    purge_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=False,
        help="Bypass confirmation prompt",
    )
    purge_parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Custom SQLite database file path (optional)",
    )

    committee_parser = subparsers.add_parser(
        "committee",
        parents=[parent_parser],
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
        if exc.code == 0:
            return 0
        if argv and len(argv) > 0 and argv[0] not in subparsers.choices and not argv[0].startswith("-"):
            return 1
        return exc.code if isinstance(exc.code, int) else 1

    is_verbose = getattr(args, "verbose", False)
    is_quiet = getattr(args, "quiet", False)
    if is_verbose and is_quiet:
        sys.stderr.write("Error: -v/--verbose and -q/--quiet are mutually exclusive.\n")
        return 2

    if is_quiet:
        log_level = logging.WARNING
    elif is_verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    setup_cli_logging(level=log_level)

    if force_terminal is not None:
        setattr(args, "force_terminal", force_terminal)

    if args.command == "sync-history":
        return handle_sync_history(args)
    elif args.command == "purge-history":
        return handle_purge_history(args)
    elif args.command == "committee":
        return handle_committee(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
