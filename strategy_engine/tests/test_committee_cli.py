"""
Unit and integration tests for the CLI 'committee' subcommand.
Validates CLI arguments, markdown/json output formatting, cold-start handling,
degraded regimes, and the strict CLI Technical Context Briefing boundary.
"""
import time
import pytest
import numpy as np

from strategy_engine.cli import main
from strategy_engine.historical_db import HistoricalRatesDB
from strategy_engine.models import HistoricalBar, CommitteeContext


@pytest.fixture
def temp_db(tmp_path):
    """Provides a fresh isolated HistoricalRatesDB for testing."""
    db_file = tmp_path / "data" / "cli_test_rates.db"
    return HistoricalRatesDB(db_path=str(db_file))


def _generate_bars(symbol: str, count: int, timeframe: str = "D1", start_time: int = 1700000000, base_price: float = 100.0):
    """Helper to generate sequential synthetic bars."""
    bars = []
    step = 86400 if timeframe == "D1" else 3600
    for i in range(count):
        t = start_time + i * step
        price = base_price + 10.0 * np.sin(i / 10.0) + (i * 0.05)
        bars.append(HistoricalBar(
            symbol=symbol,
            timeframe=timeframe,
            time=t,
            open=round(price - 0.2, 2),
            high=round(price + 1.5, 2),
            low=round(price - 1.2, 2),
            close=round(price + 0.3, 2),
            tick_volume=1000 + (i % 10) * 100,
            spread=1,
        ))
    return bars


def test_cli_committee_help(capsys):
    """Verifies committee subcommand displays helpful CLI documentation."""
    code = main(["committee", "--help"])
    assert code == 0
    out, _ = capsys.readouterr()
    assert "committee" in out.lower()
    assert "--mode" in out
    assert "--direction" in out
    assert "--entry-price" in out
    assert "--format" in out


def test_cli_committee_missing_symbol(capsys):
    """Verifies that invoking committee without symbol fails gracefully with code 1."""
    code = main(["committee"])
    assert code == 1
    out, _ = capsys.readouterr()
    assert "Error: Target symbol is required." in out


def test_cli_committee_cold_start_error(temp_db, capsys):
    """
    Scenario 6: Pure Calculator Fail-Closed on Zero Cached Bars (Cold Start).
    Catches HistoricalDataNotFoundError and advises operator to sync history.
    """
    code = main(["committee", "UNKNOWN_TICKER", "--db-path", temp_db.db_path])
    assert code == 1
    out, _ = capsys.readouterr()
    assert "Error: No historical rates found for symbol 'UNKNOWN_TICKER'" in out
    assert "python -m strategy_engine.cli sync-history --symbol UNKNOWN_TICKER" in out


def test_cli_committee_json_format(temp_db, capsys):
    """Verifies --format json outputs validated CommitteeContext JSON."""
    now = int(time.time())
    start_d1 = now - (250 * 86400)
    bars_nvda = _generate_bars("NVDA", 250, "D1", start_time=start_d1, base_price=120.0)
    bars_spy = _generate_bars("SPY", 250, "D1", start_time=start_d1, base_price=450.0)
    temp_db.insert_rates(bars_nvda)
    temp_db.insert_rates(bars_spy)

    code = main(["committee", "NVDA", "--format", "json", "--db-path", temp_db.db_path])
    assert code == 0
    out, _ = capsys.readouterr()

    # Parse and validate against Pydantic schema
    context = CommitteeContext.model_validate_json(out.strip())
    assert context.symbol == "NVDA"
    assert context.current_price > 0
    assert context.d1_bars_count == 250
    assert context.ema_20 is not None
    assert context.ema_50 is not None
    assert context.ema_200 is not None
    assert context.rsi_14 is not None
    assert context.atr_14 is not None
    assert context.swing_ceiling is not None
    assert context.swing_floor is not None
    assert "0.618" in context.fibonacci_grid
    assert context.vpoc is not None
    assert context.benchmark_beta is not None


def test_cli_committee_markdown_format_and_boundary(temp_db, capsys):
    """
    Scenario 9: CLI Briefing Boundary Verification.
    CLI output must contain pure technical data briefing and NO LLM-generated narrative or consensus score.
    """
    now = int(time.time())
    start_d1 = now - (250 * 86400)
    bars_nvda = _generate_bars("NVDA", 250, "D1", start_time=start_d1, base_price=120.0)
    temp_db.insert_rates(bars_nvda)

    code = main(["committee", "NVDA", "--format", "markdown", "--db-path", temp_db.db_path])
    assert code == 0
    out, _ = capsys.readouterr()

    # Must contain deterministic technical sections
    assert "# Technical Context Briefing: NVDA" in out
    assert "Current Price:" in out
    assert "EMA 20:" in out
    assert "EMA 50:" in out
    assert "RSI (14):" in out
    assert "Dominant Fibonacci Grid" in out
    assert "Volume Profile" in out
    assert "Benchmark Comparison" in out

    # Strict boundary assertion: must NOT contain LLM-generated wave narrative or consensus score
    lower_out = out.lower()
    assert "consensus score" not in lower_out
    assert "confluence" not in lower_out
    assert "wave 3" not in lower_out
    assert "wave 4" not in lower_out
    assert "wave analyst" not in lower_out
    assert "chief risk officer" not in lower_out
    assert "trading card" not in lower_out


def test_cli_committee_named_symbol_and_optional_arguments(temp_db, capsys):
    """Verifies named --symbol flag, --mode, --direction, and --entry-price."""
    now = int(time.time())
    bars_msft = _generate_bars("MSFT", 220, "D1", start_time=now - (220 * 86400), base_price=400.0)
    temp_db.insert_rates(bars_msft)

    code = main([
        "committee",
        "--symbol", "MSFT",
        "--mode", "exit",
        "--direction", "short",
        "--entry-price", "420.50",
        "--format", "markdown",
        "--db-path", temp_db.db_path,
    ])
    assert code == 0
    out, _ = capsys.readouterr()

    assert "# Technical Context Briefing: MSFT" in out
    assert "- **Mode:** EXIT" in out
    assert "- **Direction:** SHORT" in out
    assert "- **Target Entry Price:** $420.50" in out


def test_cli_committee_positional_symbol_and_defaults(temp_db, capsys):
    """Verifies positional symbol with default mode=entry, direction=long, and unspecified entry price."""
    now = int(time.time())
    bars_aapl = _generate_bars("AAPL", 210, "D1", start_time=now - (210 * 86400), base_price=180.0)
    temp_db.insert_rates(bars_aapl)

    code = main(["committee", "AAPL", "--db-path", temp_db.db_path])
    assert code == 0
    out, _ = capsys.readouterr()

    assert "# Technical Context Briefing: AAPL" in out
    assert "- **Mode:** ENTRY" in out
    assert "- **Direction:** LONG" in out
    assert "- **Target Entry Price:** Market / Unspecified" in out


def test_cli_committee_with_h1_bars(temp_db, capsys):
    """Verifies evaluation correctly counts and incorporates H1 bars for volume profile."""
    now = int(time.time())
    bars_d1 = _generate_bars("TSLA", 210, "D1", start_time=now - (210 * 86400), base_price=220.0)
    bars_h1 = _generate_bars("TSLA", 100, "H1", start_time=now - (100 * 3600), base_price=220.0)
    temp_db.insert_rates(bars_d1)
    temp_db.insert_rates(bars_h1)

    code = main(["committee", "TSLA", "--format", "json", "--db-path", temp_db.db_path])
    assert code == 0
    out, _ = capsys.readouterr()

    context = CommitteeContext.model_validate_json(out.strip())
    assert context.d1_bars_count == 210
    assert context.h1_bars_count == 100


def test_cli_committee_custom_benchmark(temp_db, capsys):
    """Verifies --benchmark flag specifies benchmark symbol."""
    now = int(time.time())
    bars_qqq = _generate_bars("QQQ", 210, "D1", start_time=now - (210 * 86400), base_price=380.0)
    bars_spy = _generate_bars("AMZN", 210, "D1", start_time=now - (210 * 86400), base_price=175.0)
    temp_db.insert_rates(bars_qqq)
    temp_db.insert_rates(bars_spy)

    code = main(["committee", "AMZN", "--benchmark", "QQQ", "--format", "json", "--db-path", temp_db.db_path])
    assert code == 0
    out, _ = capsys.readouterr()

    context = CommitteeContext.model_validate_json(out.strip())
    assert context.benchmark_symbol == "QQQ"
    assert context.benchmark_beta is not None


def test_cli_committee_short_history_degraded(temp_db, capsys):
    """
    Scenario 7: Degraded Regime for Short-History Assets (< 200 Bars).
    Verifies that asset with 95 bars executes successfully with ema_200 = None and degraded flag.
    """
    now = int(time.time())
    bars_arm = _generate_bars("ARM", 95, "D1", start_time=now - (95 * 86400), base_price=130.0)
    temp_db.insert_rates(bars_arm)

    code = main(["committee", "ARM", "--format", "json", "--db-path", temp_db.db_path])
    assert code == 0
    out, _ = capsys.readouterr()

    context = CommitteeContext.model_validate_json(out.strip())
    assert context.symbol == "ARM"
    assert context.d1_bars_count == 95
    assert context.ema_20 is not None
    assert context.ema_50 is not None
    assert context.ema_200 is None
    assert "[REGIME: SHORT_HISTORY_DEGRADED]" in context.data_flags


def test_cli_committee_stale_data_flag(temp_db, capsys):
    """
    Scenario 8: Staleness Detection.
    Verifies that bars older than 5 trading days trigger [DATA_STALE].
    """
    old_time = 1600000000  # Year 2020
    bars_xyz = _generate_bars("XYZ", 210, "D1", start_time=old_time, base_price=50.0)
    temp_db.insert_rates(bars_xyz)

    code = main(["committee", "XYZ", "--format", "markdown", "--db-path", temp_db.db_path])
    assert code == 0
    out, _ = capsys.readouterr()

    assert "[DATA_STALE]" in out
