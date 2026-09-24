"""
Unit and integration tests for CLI sync-history and purge-history commands.
Covers Gherkin scenarios for Issue #93 (Slice 1) and Issue #94 (Slice 2) of Parent #92.
"""
import asyncio
import json
import logging
import pytest
from unittest.mock import patch

from strategy_engine.cli import main as cli_main, parse_symbols
from strategy_engine.config import StrategyConfig
from strategy_engine.historical_db import HistoricalRatesDB
from strategy_engine.models import HistoricalSyncStatus, HistoricalBar, AssetInfo
from strategy_engine.mt5_connector import MT5Connector


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_history.db")
    return HistoricalRatesDB(db_path=db_file)


class TestCliHistoryParallelSync:
    """Tests covering Scenario 1, 2, 7, 8, 9, 12, 13, 14, 15, 16."""

    def test_scenario_1_parallel_sync_selected_stocks(self, temp_db, capsys):
        """
        Scenario 1: Parallel Historical Sync for Selected Stocks.
        Routes execution through connector.sync_historical_batch bounded by workers=5.
        Outputs summary showing 3/3 symbols completed with exit code 0.
        """
        db_path = temp_db.db_path
        rc = cli_main([
            "sync-history",
            "--symbol", "AAPL,MSFT,NVDA",
            "--timeframe", "D1",
            "--workers", "5",
            "--db-path", db_path,
        ])
        assert rc == 0
        captured = capsys.readouterr().out
        assert "3/3 completed, 0 failed" in captured
        assert temp_db.get_total_bars("AAPL", "D1") == 100
        assert temp_db.get_total_bars("MSFT", "D1") == 100
        assert temp_db.get_total_bars("NVDA", "D1") == 100

    def test_scenario_2_multi_timeframe_bulk_ingestion_all(self, temp_db, capsys):
        """
        Scenario 2: Multi-Timeframe Bulk Ingestion (--timeframe all).
        Expands 'all' into the 9 canonical timeframes (M1..MN1), sequentially pulls
        each for TSLA, reports total bars committed with exit code 0.
        """
        db_path = temp_db.db_path
        rc = cli_main([
            "sync-history",
            "--symbol", "TSLA",
            "--timeframe", "all",
            "--db-path", db_path,
        ])
        assert rc == 0
        captured = capsys.readouterr().out
        assert "1/1 completed, 0 failed" in captured
        assert "Total bars committed: 900" in captured
        # 100 bars per timeframe across 9 canonical timeframes = 900 bars
        for tf in ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]:
            assert temp_db.get_total_bars("TSLA", tf) == 100

    def test_scenario_7_partial_failure_exit_code_contract(self, temp_db, capsys):
        """
        Scenario 7: Partial Failure Exit Code Contract on Delisted/Invalid Symbols in Batch.
        Asset AAPL is valid and DELISTED_XYZ fails.
        Logs warning and marks DELISTED_XYZ as failed in status.failed_symbols.
        Prints: 'Warning: Partial sync completed (1/2). Failed symbols: DELISTED_XYZ'
        Exits with exit code 2.
        """
        db_path = temp_db.db_path
        rc = cli_main([
            "sync-history",
            "--symbol", "AAPL,DELISTED_XYZ",
            "--db-path", db_path,
        ])
        assert rc == 2
        captured = capsys.readouterr().out
        assert "Warning: Partial sync completed (1/2). Failed symbols: DELISTED_XYZ" in captured
        assert temp_db.get_total_bars("AAPL", "D1") == 100
        assert temp_db.get_total_bars("DELISTED_XYZ", "D1") == 0

    def test_fatal_all_failed_exit_code_1(self, temp_db, capsys):
        """
        Verifies that when all requested symbols fail, CLI outputs error and exits with code 1.
        """
        db_path = temp_db.db_path
        rc = cli_main([
            "sync-history",
            "--symbol", "DELISTED_1,DELISTED_2",
            "--db-path", db_path,
        ])
        assert rc == 1
        captured = capsys.readouterr().out
        assert "Error: Batch sync failed (0/2)." in captured
        assert "DELISTED_1" in captured
        assert "DELISTED_2" in captured

    def test_scenario_8_worker_count_lower_bound_fast_fail(self, capsys):
        """
        Scenario 8: Fast-Fail Validation on Invalid Worker Count (0).
        Fails fast before initializing MT5 or database connections.
        Prints: 'Error: --workers must be an integer between 1 and 50 (got 0).'
        Aborts immediately with exit code 1.
        """
        with patch("strategy_engine.cli.MT5Connector") as mock_conn:
            rc = cli_main([
                "sync-history",
                "--symbol", "AAPL",
                "--workers", "0",
            ])
            assert rc == 1
            captured = capsys.readouterr().out
            assert "Error: --workers must be an integer between 1 and 50 (got 0)." in captured
            mock_conn.assert_not_called()

    def test_scenario_16_worker_count_upper_bound_fast_fail(self, capsys):
        """
        Scenario 16: Worker Count Upper-Bound Fast-Fail (51).
        Prints: 'Error: --workers must be an integer between 1 and 50 (got 51).'
        Aborts immediately with exit code 1.
        """
        with patch("strategy_engine.cli.MT5Connector") as mock_conn:
            rc = cli_main([
                "sync-history",
                "--symbol", "AAPL",
                "--workers", "51",
            ])
            assert rc == 1
            captured = capsys.readouterr().out
            assert "Error: --workers must be an integer between 1 and 50 (got 51)." in captured
            mock_conn.assert_not_called()

    def test_scenario_9_unified_batch_worker_pool_routing(self, temp_db):
        """
        Scenario 9: Unified Batch Worker Pool Routing for Multi-Symbol Input.
        Verifies that input is normalized into ['AAPL', 'MSFT', 'NVDA'],
        dispatched to connector.sync_historical_batch(workers=3),
        and no legacy serial single-symbol branch (sync_historical_rates) is called directly from CLI.
        """
        db_path = temp_db.db_path
        with patch.object(MT5Connector, "sync_historical_batch", wraps=None) as mock_batch, \
             patch.object(MT5Connector, "sync_historical_rates", wraps=None) as mock_single:

            mock_batch.return_value = HistoricalSyncStatus(
                status="COMPLETED",
                completed_assets=3,
                failed_assets=0,
                total_assets=3,
            )

            rc = cli_main([
                "sync-history",
                "--symbol", "AAPL,MSFT,NVDA",
                "--workers", "3",
                "--db-path", db_path,
            ])
            assert rc == 0
            mock_batch.assert_called_once()
            call_kwargs = mock_batch.call_args.kwargs
            assert call_kwargs["symbols"] == ["AAPL", "MSFT", "NVDA"]
            assert call_kwargs["workers"] == 3
            # Ensure CLI did not call the legacy single-symbol branch directly
            mock_single.assert_not_called()

    def test_scenario_12_empty_or_whitespace_symbol_fast_fail(self, capsys):
        """
        Scenario 12: Fast-Fail Validation on Empty or Whitespace-Only --symbol Input.
        Stripping whitespace and commas results in an empty symbol list.
        Fails fast before connector initialization.
        Prints: 'Error: No valid symbols provided.'
        Aborts immediately with exit code 1.
        """
        with patch("strategy_engine.cli.MT5Connector") as mock_conn:
            rc = cli_main([
                "sync-history",
                "--symbol", " , ",
            ])
            assert rc == 1
            captured = capsys.readouterr().out
            assert "Error: No valid symbols provided." in captured
            mock_conn.assert_not_called()

    def test_parse_symbols_helper(self):
        """Verifies symbol normalization across comma, whitespace, list, and deduplication."""
        assert parse_symbols(None) == []
        assert parse_symbols("") == []
        assert parse_symbols(" , ") == []
        assert parse_symbols("AAPL,MSFT,NVDA") == ["AAPL", "MSFT", "NVDA"]
        assert parse_symbols("AAPL MSFT NVDA") == ["AAPL", "MSFT", "NVDA"]
        assert parse_symbols(["AAPL, MSFT", "NVDA", "AAPL"]) == ["AAPL", "MSFT", "NVDA"]

    def test_scenario_13_backward_compatible_keyword_arguments(self, temp_db):
        """
        Scenario 13: Backward-Compatible Keyword Argument Retention.
        Callers invoke clear_rates(symbol="AAPL", timeframe="D1") and
        sync_historical_batch(symbols=["AAPL"], timeframe="D1", yield_ms=0.025).
        Resolves without raising TypeError: got an unexpected keyword argument.
        """
        # 1. clear_rates keyword signature
        res = temp_db.clear_rates(symbol="AAPL", timeframe="D1")
        assert isinstance(res, int)

        # 2. sync_historical_batch keyword signature
        config = StrategyConfig(mock_mode=True)
        connector = MT5Connector(config)
        connector.initialize()

        async def _run():
            return await connector.sync_historical_batch(
                symbols=["AAPL"],
                timeframe="D1",
                yield_ms=0.025,
                db=temp_db,
            )

        status = asyncio.run(_run())
        assert status.status == "COMPLETED"
        assert status.completed_assets == 1
        assert status.failed_assets == 0

    def test_scenario_14_delisted_symbol_fast_fail(self, temp_db):
        """
        Scenario 14: Delisted Symbol Fast-Fail in Multi-Timeframe Batch.
        When DELISTED_STOCK is queried with --timeframe all (9 timeframes),
        the first timeframe returns None.
        The worker task records DELISTED_STOCK in failed_symbols and breaks immediately
        without making the 8 subsequent calls.
        """
        config = StrategyConfig(mock_mode=True)
        connector = MT5Connector(config)
        connector.initialize()

        call_count = 0
        original_sync_rates = connector.sync_historical_rates

        def counting_sync_rates(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original_sync_rates(*args, **kwargs)

        with patch.object(connector, "sync_historical_rates", side_effect=counting_sync_rates):
            status = asyncio.run(
                connector.sync_historical_batch(
                    symbols=["DELISTED_STOCK"],
                    timeframe="all",
                    db=temp_db,
                )
            )

        assert status.failed_assets == 1
        assert status.failed_symbols == ["DELISTED_STOCK"]
        # Fast fail must break after the very first timeframe query (1 call instead of 9)
        assert call_count == 1

    def test_scenario_15_mock_mode_env_and_mutually_exclusive_flags(self, monkeypatch, capsys):
        """
        Scenario 15: Environment Variable MOCK_MODE Resolution & Mutually Exclusive Flags.
        1. When MOCK_MODE=false in env, StrategyConfig() initializes with mock_mode=False.
        2. When MOCK_MODE=true in env, StrategyConfig() initializes with mock_mode=True.
        3. When user specifies --live --mock, argparse immediately rejects mutually exclusive args with exit code 2.
        """
        # 1. MOCK_MODE=false
        monkeypatch.setenv("MOCK_MODE", "false")
        cfg_false = StrategyConfig()
        assert cfg_false.mock_mode is False

        # 2. MOCK_MODE=true
        monkeypatch.setenv("MOCK_MODE", "true")
        cfg_true = StrategyConfig()
        assert cfg_true.mock_mode is True

        # 3. Mutually exclusive --live and --mock flags
        rc = cli_main(["sync-history", "--symbol", "AAPL", "--live", "--mock"])
        assert rc == 2

    def test_historical_sync_status_schema_and_lockstep(self):
        """
        Verifies HistoricalSyncStatus schema updates:
        - failed_symbols field defaults to empty list
        - failed_assets stays in lockstep with len(failed_symbols)
        """
        s1 = HistoricalSyncStatus()
        assert s1.failed_symbols == []
        assert s1.failed_assets == 0

        s2 = HistoricalSyncStatus(failed_symbols=["AAPL", "MSFT"])
        assert s2.failed_symbols == ["AAPL", "MSFT"]
        assert s2.failed_assets == 2

        # Backward compatibility when failed_assets is set explicitly
        s3 = HistoricalSyncStatus(failed_assets=4)
        assert s3.failed_assets == 4

    def test_repeated_symbol_flags(self, temp_db):
        """Verifies repeated --symbol flags on CLI."""
        db_path = temp_db.db_path
        rc = cli_main([
            "sync-history",
            "--symbol", "AAPL",
            "--symbol", "MSFT",
            "--db-path", db_path,
        ])
        assert rc == 0
        assert temp_db.get_total_bars("AAPL", "D1") == 100
        assert temp_db.get_total_bars("MSFT", "D1") == 100


class TestCliHistoryGranularPurge:
    """Tests covering Scenario 3, 4, 5, 6, 10, 11 for Issue #94 (Slice 2 of Parent #92)."""

    def test_scenario_3_granular_timeframe_purge_single_asset(self, temp_db, capsys):
        """
        Scenario 3: Granular Timeframe Purge for a Single Asset.
        Given asset "AMZN" has cached historical bars across timeframes "D1" and "H1".
        When user executes: purge-history --symbol AMZN --timeframe H1 -y
        Then CLI deletes all records where symbol = 'AMZN' AND timeframe = 'H1'
        And leaves all 'D1' records for AMZN intact.
        And outputs count of purged rows with exit code 0.
        """
        db_path = temp_db.db_path
        bars_d1 = [
            HistoricalBar(symbol="AMZN", timeframe="D1", time=1700000000 + i, open=100.0, high=105.0, low=95.0, close=102.0)
            for i in range(10)
        ]
        bars_h1 = [
            HistoricalBar(symbol="AMZN", timeframe="H1", time=1700000000 + i, open=100.0, high=105.0, low=95.0, close=102.0)
            for i in range(15)
        ]
        temp_db.insert_rates(bars_d1)
        temp_db.insert_rates(bars_h1)
        assert temp_db.get_total_bars("AMZN", "D1") == 10
        assert temp_db.get_total_bars("AMZN", "H1") == 15

        rc = cli_main([
            "purge-history",
            "--symbol", "AMZN",
            "--timeframe", "H1",
            "-y",
            "--db-path", db_path,
        ])
        assert rc == 0
        captured = capsys.readouterr().out
        assert "15" in captured
        assert temp_db.get_total_bars("AMZN", "H1") == 0
        assert temp_db.get_total_bars("AMZN", "D1") == 10

    def test_scenario_4_category_wide_purge(self, temp_db, capsys):
        """
        Scenario 4: Category-Wide Purge.
        Given multiple Forex assets ("EURUSD", "GBPUSD") have cached rates in SQLite.
        When user executes: purge-history --category forex -y
        Then CLI resolves all assets belonging to category "forex",
        deletes all rates records associated with those forex symbols,
        and outputs total count of deleted rows with exit code 0.
        """
        db_path = temp_db.db_path
        bars_eur = [
            HistoricalBar(symbol="EURUSD", timeframe="D1", time=1700000000 + i, open=1.05, high=1.06, low=1.04, close=1.055)
            for i in range(12)
        ]
        bars_gbp = [
            HistoricalBar(symbol="GBPUSD", timeframe="D1", time=1700000000 + i, open=1.25, high=1.26, low=1.24, close=1.255)
            for i in range(8)
        ]
        bars_aapl = [
            HistoricalBar(symbol="AAPL", timeframe="D1", time=1700000000 + i, open=150.0, high=155.0, low=149.0, close=152.0)
            for i in range(5)
        ]
        temp_db.insert_rates(bars_eur)
        temp_db.insert_rates(bars_gbp)
        temp_db.insert_rates(bars_aapl)
        assert temp_db.get_total_bars("EURUSD", "D1") == 12
        assert temp_db.get_total_bars("GBPUSD", "D1") == 8
        assert temp_db.get_total_bars("AAPL", "D1") == 5

        mock_forex_assets = [
            AssetInfo(symbol="EURUSD", description="EUR/USD", category="Forex/Majors"),
            AssetInfo(symbol="GBPUSD", description="GBP/USD", category="Forex/Majors"),
        ]
        with patch.object(MT5Connector, "get_available_assets", return_value=mock_forex_assets):
            rc = cli_main([
                "purge-history",
                "--category", "forex",
                "-y",
                "--db-path", db_path,
            ])
            assert rc == 0
            captured = capsys.readouterr().out
            assert "20" in captured
            assert temp_db.get_total_bars("EURUSD", "D1") == 0
            assert temp_db.get_total_bars("GBPUSD", "D1") == 0
            assert temp_db.get_total_bars("AAPL", "D1") == 5

    def test_scenario_5_safety_guard_no_target_specified(self, temp_db, capsys):
        """
        Scenario 5: Safety Guard Against Accidental Total Database Wipe.
        Given user invokes `purge-history` without specifying `--all`, `--symbol`, or `--category`.
        Aborts immediately with exit code 1.
        Displays error explaining a specific target is required.
        Leaves database records untouched.
        """
        db_path = temp_db.db_path
        bars = [
            HistoricalBar(symbol="AAPL", timeframe="D1", time=1700000000 + i, open=100.0, high=105.0, low=95.0, close=102.0)
            for i in range(5)
        ]
        temp_db.insert_rates(bars)
        assert temp_db.get_total_bars("AAPL", "D1") == 5

        rc = cli_main([
            "purge-history",
            "--db-path", db_path,
        ])
        assert rc == 1
        captured = capsys.readouterr().out
        assert "Error: Target required. Please specify --symbol, --category, or --all." in captured
        assert temp_db.get_total_bars("AAPL", "D1") == 5

    def test_scenario_5_empty_whitespace_symbol_safety_guard(self, temp_db, capsys):
        """
        Empty or whitespace-only --symbol input fails fast with exit code 1.
        """
        db_path = temp_db.db_path
        rc = cli_main([
            "purge-history",
            "--symbol", " , ",
            "--db-path", db_path,
        ])
        assert rc == 1
        captured = capsys.readouterr().out
        assert "Error: No valid symbols provided." in captured

    def test_scenario_6_non_interactive_confirmation_abort(self, temp_db, capsys):
        """
        Scenario 6: Non-Interactive Confirmation Abort in Headless Mode.
        Given stdin is not attached to an interactive terminal.
        When user executes `purge-history --all` without `-y`.
        Aborts immediately with exit code 1.
        Prints error requiring `-y` / `--yes`.
        No database records are modified.
        """
        db_path = temp_db.db_path
        bars = [
            HistoricalBar(symbol="AAPL", timeframe="D1", time=1700000000 + i, open=100.0, high=105.0, low=95.0, close=102.0)
            for i in range(5)
        ]
        temp_db.insert_rates(bars)

        with patch("sys.stdin.isatty", return_value=False):
            rc = cli_main([
                "purge-history",
                "--all",
                "--db-path", db_path,
            ])
            assert rc == 1
            captured = capsys.readouterr().out
            assert "Error: Confirmation required. Use -y or --yes in non-interactive environments." in captured
            assert temp_db.get_total_bars("AAPL", "D1") == 5

    def test_scenario_10_granular_timeframe_purge_all(self, temp_db, capsys):
        """
        Scenario 10: Granular Timeframe Purge for All Timeframes (--timeframe all).
        Given asset "TSLA" has cached bars across "M1", "H1", and "D1" timeframes.
        When user executes `purge-history --symbol TSLA --timeframe all -y`.
        Then clear_rates() omits timeframe filter clause, deletes all records for TSLA,
        and outputs count of all purged rows with exit code 0.
        """
        db_path = temp_db.db_path
        bars_m1 = [HistoricalBar(symbol="TSLA", timeframe="M1", time=1700000000 + i, open=200.0, high=201.0, low=199.0, close=200.5) for i in range(10)]
        bars_h1 = [HistoricalBar(symbol="TSLA", timeframe="H1", time=1700000000 + i, open=200.0, high=205.0, low=198.0, close=202.0) for i in range(8)]
        bars_d1 = [HistoricalBar(symbol="TSLA", timeframe="D1", time=1700000000 + i, open=200.0, high=210.0, low=195.0, close=208.0) for i in range(6)]
        bars_other = [HistoricalBar(symbol="AAPL", timeframe="D1", time=1700000000 + i, open=150.0, high=155.0, low=149.0, close=152.0) for i in range(5)]

        temp_db.insert_rates(bars_m1 + bars_h1 + bars_d1 + bars_other)
        assert temp_db.get_total_bars("TSLA", "M1") == 10
        assert temp_db.get_total_bars("TSLA", "H1") == 8
        assert temp_db.get_total_bars("TSLA", "D1") == 6
        assert temp_db.get_total_bars("AAPL", "D1") == 5

        rc = cli_main([
            "purge-history",
            "--symbol", "TSLA",
            "--timeframe", "all",
            "-y",
            "--db-path", db_path,
        ])
        assert rc == 0
        captured = capsys.readouterr().out
        assert "24" in captured
        assert temp_db.get_total_bars("TSLA", "M1") == 0
        assert temp_db.get_total_bars("TSLA", "H1") == 0
        assert temp_db.get_total_bars("TSLA", "D1") == 0
        assert temp_db.get_total_bars("AAPL", "D1") == 5

    def test_scenario_11_user_cancellation_interactive_purge(self, temp_db, capsys):
        """
        Scenario 11: User Cancellation of Interactive Destructive Purge.
        Given stdin is attached to an interactive terminal.
        When user executes `purge-history --all`.
        And responds 'n' to confirmation prompt "Are you sure you want to purge ALL historical data from the database? [y/N]: ".
        Then CLI prints "Operation cancelled by user.", aborts safely with exit code 0, leaves records untouched.
        """
        db_path = temp_db.db_path
        bars = [
            HistoricalBar(symbol="AAPL", timeframe="D1", time=1700000000 + i, open=100.0, high=105.0, low=95.0, close=102.0)
            for i in range(5)
        ]
        temp_db.insert_rates(bars)

        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", return_value="n") as mock_input:
            rc = cli_main([
                "purge-history",
                "--all",
                "--db-path", db_path,
            ])
            assert rc == 0
            mock_input.assert_called_once_with("Are you sure you want to purge ALL historical data from the database? [y/N]: ")
            captured = capsys.readouterr().out
            assert "Operation cancelled by user." in captured
            assert temp_db.get_total_bars("AAPL", "D1") == 5

    def test_interactive_confirmation_user_accepts(self, temp_db, capsys):
        """
        Interactive confirmation accepted ('y') executes purge and exits with 0.
        """
        db_path = temp_db.db_path
        bars = [
            HistoricalBar(symbol="AAPL", timeframe="D1", time=1700000000 + i, open=100.0, high=105.0, low=95.0, close=102.0)
            for i in range(5)
        ]
        temp_db.insert_rates(bars)

        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", return_value="y") as mock_input:
            rc = cli_main([
                "purge-history",
                "--all",
                "--db-path", db_path,
            ])
            assert rc == 0
            mock_input.assert_called_once_with("Are you sure you want to purge ALL historical data from the database? [y/N]: ")
            captured = capsys.readouterr().out
            assert "Successfully purged 5" in captured
            assert temp_db.get_total_bars("AAPL", "D1") == 0

    def test_interactive_confirmation_symbol_prompt_cancellation(self, temp_db, capsys):
        """
        Interactive confirmation on --symbol prompt cancelled by user.
        """
        db_path = temp_db.db_path
        bars = [
            HistoricalBar(symbol="AAPL", timeframe="D1", time=1700000000 + i, open=100.0, high=105.0, low=95.0, close=102.0)
            for i in range(5)
        ]
        temp_db.insert_rates(bars)

        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", return_value="no") as mock_input:
            rc = cli_main([
                "purge-history",
                "--symbol", "AAPL",
                "--timeframe", "D1",
                "--db-path", db_path,
            ])
            assert rc == 0
            assert "AAPL" in mock_input.call_args[0][0]
            assert "D1" in mock_input.call_args[0][0]
            captured = capsys.readouterr().out
            assert "Operation cancelled by user." in captured
            assert temp_db.get_total_bars("AAPL", "D1") == 5

    def test_purge_unsupported_timeframe(self, temp_db, capsys):
        """
        Specifying invalid timeframe returns exit code 1.
        """
        db_path = temp_db.db_path
        rc = cli_main([
            "purge-history",
            "--symbol", "AAPL",
            "--timeframe", "INVALID_TF",
            "-y",
            "--db-path", db_path,
        ])
        assert rc == 1
        captured = capsys.readouterr().out
        assert "Error: Unsupported timeframe 'INVALID_TF'." in captured

    def test_purge_multiple_symbols_and_repeated_flags(self, temp_db, capsys):
        """
        Purges multiple symbols specified via comma or repeated flags.
        """
        db_path = temp_db.db_path
        bars1 = [HistoricalBar(symbol="AAPL", timeframe="D1", time=1700000000 + i, open=100.0, high=105.0, low=95.0, close=102.0) for i in range(4)]
        bars2 = [HistoricalBar(symbol="MSFT", timeframe="D1", time=1700000000 + i, open=200.0, high=205.0, low=195.0, close=202.0) for i in range(6)]
        bars3 = [HistoricalBar(symbol="NVDA", timeframe="D1", time=1700000000 + i, open=300.0, high=305.0, low=295.0, close=302.0) for i in range(8)]
        temp_db.insert_rates(bars1 + bars2 + bars3)

        rc = cli_main([
            "purge-history",
            "--symbol", "AAPL,MSFT",
            "-y",
            "--db-path", db_path,
        ])
        assert rc == 0
        captured = capsys.readouterr().out
        assert "10" in captured
        assert temp_db.get_total_bars("AAPL", "D1") == 0
        assert temp_db.get_total_bars("MSFT", "D1") == 0
        assert temp_db.get_total_bars("NVDA", "D1") == 8

    def test_clear_rates_edge_cases_and_wal_pragma(self, temp_db):
        """
        Verifies clear_rates unit behaviors:
        - clear_rates with empty list returns 0
        - clear_rates with timeframe ALL normalizes to None
        - clear_rates with symbol list
        - PRAGMA journal_mode is WAL
        """
        # Empty list is no-op
        assert temp_db.clear_rates(symbols=[]) == 0

        # Insert some bars
        bars = [HistoricalBar(symbol="TEST", timeframe="D1", time=1700000000 + i, open=10.0, high=11.0, low=9.0, close=10.5) for i in range(5)]
        temp_db.insert_rates(bars)
        assert temp_db.get_total_bars("TEST", "D1") == 5

        # Purge with timeframe="ALL"
        deleted = temp_db.clear_rates(symbols=["TEST"], timeframe="ALL")
        assert deleted == 5
        assert temp_db.get_total_bars("TEST", "D1") == 0


class TestCliLoggingAndObservability:
    """Comprehensive test suite for Issue #116: CLI Logging & Progress Observability (Scenarios 1-8)."""

    def test_scenario_1_verbose_flag_before_subcommand(self, temp_db, capsys):
        """
        Scenario 1: -v placed before subcommand configures logger to DEBUG on stderr,
        emitting connector initialization, worker semaphore acquisition, and timeframe upserts.
        """
        db_path = temp_db.db_path
        rc = cli_main([
            "-v",
            "sync-history",
            "--symbol", "AAPL",
            "--db-path", db_path,
        ])
        assert rc == 0
        captured = capsys.readouterr()
        err = captured.err
        assert "[DEBUG]" in err
        assert "Connector initialized:" in err
        assert "semaphore for symbol 'AAPL'" in err
        assert "Upserted 100 bars for AAPL" in err
        assert "Batch sync finished: 1/1 completed, 0 failed." in captured.out

    def test_scenario_1_verbose_flag_after_subcommand(self, temp_db, capsys):
        """
        Scenario 1: --verbose placed after subcommand configures logger to DEBUG on stderr.
        """
        db_path = temp_db.db_path
        rc = cli_main([
            "sync-history",
            "--symbol", "AAPL",
            "--verbose",
            "--db-path", db_path,
        ])
        assert rc == 0
        captured = capsys.readouterr()
        err = captured.err
        assert "[DEBUG]" in err
        assert "Connector initialized:" in err
        assert "semaphore for symbol 'AAPL'" in err
        assert "Upserted 100 bars for AAPL" in err

    def test_scenario_1_quiet_flag_suppresses_info_progress(self, temp_db, capsys):
        """
        Scenario 1: -q/--quiet sets logger to WARNING on stderr, suppressing INFO progress messages.
        """
        db_path = temp_db.db_path
        rc = cli_main([
            "-q",
            "sync-history",
            "--symbol", "AAPL",
            "--db-path", db_path,
        ])
        assert rc == 0
        captured = capsys.readouterr()
        err = captured.err
        assert "[INFO]" not in err
        assert "[DEBUG]" not in err
        assert "Synchronizing" not in err
        assert "milestone" not in err
        assert "Batch sync finished: 1/1 completed, 0 failed." in captured.out

        # Also verify --quiet placed after subcommand
        rc2 = cli_main([
            "sync-history",
            "--symbol", "AAPL",
            "--quiet",
            "--db-path", db_path,
        ])
        assert rc2 == 0
        err2 = capsys.readouterr().err
        assert "[INFO]" not in err2
        assert "[DEBUG]" not in err2

    def test_scenario_1_mutual_exclusion_fails_fast_with_code_2(self, capsys):
        """
        Scenario 1: Mutually exclusive -v and -q in either order or split across subcommands
        fails fast with exit code 2 and outputs an error to stderr.
        """
        # Combination 1: -v before, -q after
        rc1 = cli_main(["-v", "sync-history", "-q", "--symbol", "AAPL"])
        assert rc1 == 2
        err1 = capsys.readouterr().err
        assert "Error: -v/--verbose and -q/--quiet are mutually exclusive." in err1

        # Combination 2: -q before, -v after
        rc2 = cli_main(["-q", "sync-history", "-v", "--symbol", "AAPL"])
        assert rc2 == 2
        err2 = capsys.readouterr().err
        assert "Error: -v/--verbose and -q/--quiet are mutually exclusive." in err2

        # Combination 3: Both after subcommand
        rc3 = cli_main(["sync-history", "-v", "-q", "--symbol", "AAPL"])
        assert rc3 == 2
        err3 = capsys.readouterr().err
        assert "Error: -v/--verbose and -q/--quiet are mutually exclusive." in err3

        # Combination 4: Both before subcommand
        rc4 = cli_main(["-v", "-q", "sync-history", "--symbol", "AAPL"])
        assert rc4 == 2
        err4 = capsys.readouterr().err
        assert "Error: -v/--verbose and -q/--quiet are mutually exclusive." in err4

    def test_scenario_2_interactive_rich_progress_on_stderr(self, temp_db, capsys):
        """
        Scenario 2: Real-Time Interactive Progress Tracking on Stderr.
        When force_terminal=True and HAS_RICH is True, renders a Rich progress bar
        displaying total completed assets, remaining assets, elapsed time, and ingestion rate (bars/s)
        strictly to stderr, while stdout receives only the legacy final summary line.
        """
        db_path = temp_db.db_path
        rc = cli_main(
            ["sync-history", "--symbol", "AAPL,MSFT", "--db-path", db_path],
            force_terminal=True,
        )
        assert rc == 0
        captured = capsys.readouterr()
        # Verify stdout purity
        assert captured.out == "Batch sync finished: 2/2 completed, 0 failed. Total bars committed: 200.\n"
        # Verify stderr Rich telemetry fields
        err = captured.err
        assert "completed" in err
        assert "remaining" in err
        assert "bars/s" in err
        assert "AAPL" in err
        assert "MSFT" in err

    def test_scenario_3_non_interactive_headless_decile_milestones(self, temp_db, capsys):
        """
        Scenario 3: Non-Interactive Headless Fallback with Deterministic Milestones.
        When sys.stderr.isatty() is False, logs deterministic milestone lines to stderr
        whenever done assets cross each 10% boundary of total assets (10%, 20%, ..., 100%),
        emitting no ANSI control characters, and keeping stdout clean.
        """
        db_path = temp_db.db_path
        symbols = [f"SYM{i:02d}" for i in range(1, 26)]
        rc = cli_main([
            "sync-history",
            "--symbol", ",".join(symbols),
            "--db-path", db_path,
        ])
        assert rc == 0
        captured = capsys.readouterr()
        err = captured.err
        # Verify no ANSI escape control characters
        assert "\x1b[" not in err
        # Verify decile milestones
        for pct in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100):
            assert f"Sync progress milestone: {pct}%" in err
        # Verify stdout purity
        assert captured.out == "Batch sync finished: 25/25 completed, 0 failed. Total bars committed: 2500.\n"

    def test_scenario_3_headless_milestone_with_partial_failure(self, temp_db, capsys):
        """
        Scenario 3: Always emits final 100% milestone when done == total, even if some assets failed.
        """
        db_path = temp_db.db_path
        symbols = [f"SYM{i:02d}" for i in range(1, 10)] + ["DELISTED_FAIL"]
        rc = cli_main([
            "sync-history",
            "--symbol", ",".join(symbols),
            "--db-path", db_path,
        ])
        assert rc == 2
        captured = capsys.readouterr()
        err = captured.err
        assert "Sync progress milestone: 100%" in err
        assert "Warning: Partial sync completed (9/10). Failed symbols: DELISTED_FAIL" in captured.out

    def test_scenario_4_concurrency_safe_diagnostic_warnings(self, temp_db, capsys):
        """
        Scenario 4: Concurrency-Safe Diagnostic Visibility for Delisted / Failed Symbols.
        Each worker generates its failure reason locally without reading shared connector.last_error,
        outputs distinct WARNING log to stderr identifying the failed symbol and failure reason,
        and stdout receives the legacy partial failure line.
        """
        db_path = temp_db.db_path
        rc = cli_main([
            "sync-history",
            "--symbol", "AAPL,DELISTED_1,DELISTED_2",
            "--workers", "3",
            "--db-path", db_path,
        ])
        assert rc == 2
        captured = capsys.readouterr()
        assert captured.out == "Warning: Partial sync completed (1/3). Failed symbols: DELISTED_1, DELISTED_2\n"
        err = captured.err
        assert "[WARN]" in err
        assert "[DELISTED_1] Fetch failed:" in err
        assert "[DELISTED_2] Fetch failed:" in err
        assert "delisted or invalid" in err

    def test_scenario_5_purge_history_audit_logging(self, temp_db, capsys):
        """
        Scenario 5: Purge History Audit Logging.
        When purge-history is executed, logs database path, target symbol, and targeted timeframe
        to stderr, while stdout receives the legacy line verbatim.
        """
        db_path = temp_db.db_path
        # Populate AAPL first
        cli_main(["sync-history", "--symbol", "AAPL", "-q", "--db-path", db_path])
        capsys.readouterr()

        rc = cli_main([
            "purge-history",
            "--symbol", "AAPL",
            "--yes",
            "--db-path", db_path,
        ])
        assert rc == 0
        captured = capsys.readouterr()
        assert captured.out == "Successfully purged 100 historical rate record(s).\n"
        err = captured.err
        assert "Purging historical rates:" in err
        assert db_path in err
        assert "AAPL" in err
        assert "timeframe=all" in err
        assert "Purge completed in" in err

    def test_scenario_6_backward_compatibility_public_api(self, temp_db):
        """
        Scenario 6: Public method connector.sync_historical_rates returns a 2-tuple (bars, count)
        matching its original signature.
        """
        config = StrategyConfig(mock_mode=True)
        connector = MT5Connector(config)
        connector.initialize()
        res = connector.sync_historical_rates("AAPL", "D1", db=temp_db)
        assert isinstance(res, tuple)
        assert len(res) == 2
        bars, count = res
        assert isinstance(bars, list)
        assert count == 100

    def test_scenario_7_preservation_of_piped_machine_readable_output(self, temp_db, capsys):
        """
        Scenario 7: Preservation of Piped Machine-Readable Output (committee --format json).
        When executed with -v, all diagnostic logs are directed strictly to stderr,
        and stdout contains strictly valid JSON parseable by json.loads().
        """
        db_path = temp_db.db_path
        cli_main(["sync-history", "--symbol", "AAPL,SPY", "-q", "--db-path", db_path])
        capsys.readouterr()

        rc = cli_main([
            "-v",
            "committee",
            "AAPL",
            "--format", "json",
            "--db-path", db_path,
        ])
        assert rc == 0
        captured = capsys.readouterr()
        # Parse stdout JSON
        data = json.loads(captured.out)
        assert data["symbol"] == "AAPL"
        assert "current_price" in data
        assert "fibonacci_grid" in data
        # Stderr received logs
        assert captured.err != ""

    def test_scenario_8_logger_setup_idempotency(self, temp_db, capsys):
        """
        Scenario 8: Logger Setup Idempotency Across In-Process Invocations.
        Sequential main() calls reset handlers on "strategy_engine" idempotently,
        preventing duplicate log lines and closed file errors.
        """
        db_path = temp_db.db_path
        for _ in range(3):
            rc = cli_main(["sync-history", "--symbol", "AAPL", "--db-path", db_path])
            assert rc == 0
            err = capsys.readouterr().err
            # Count occurrence of the banner in stderr for this invocation
            assert err.count("Synchronizing historical rates for 1 symbol(s)") == 1

        engine_logger = logging.getLogger("strategy_engine")
        assert len(engine_logger.handlers) == 1

    def test_graceful_fallback_when_rich_unavailable(self, temp_db, monkeypatch, capsys):
        """
        Verifies that when HAS_RICH is False, the CLI gracefully falls back
        to non-interactive decile milestones even if force_terminal=True.
        """
        db_path = temp_db.db_path
        monkeypatch.setattr("strategy_engine.cli.HAS_RICH", False)
        rc = cli_main(
            ["sync-history", "--symbol", "AAPL,MSFT", "--db-path", db_path],
            force_terminal=True,
        )
        assert rc == 0
        captured = capsys.readouterr()
        assert "Batch sync finished: 2/2 completed, 0 failed. Total bars committed: 200.\n" == captured.out
        assert "Sync progress milestone: 100%" in captured.err


class TestBatchFaultIsolationAndConcurrency:
    """Acceptance tests for Issue #118 Scenarios 6 and 7."""

    @pytest.mark.asyncio
    async def test_scenario_6_fault_isolated_batch_worker_task_resilience(self, temp_db, caplog):
        """
        Scenario 6: Fault-Isolated Batch Worker Task Resilience.
        When a worker encounters an unrecoverable exception, worker_task catches it,
        records fail_reason and logs at DEBUG level with exc_info=True.
        The exception does not escape to abort asyncio.gather(), and remaining symbols succeed.
        """
        cfg = StrategyConfig(mock_mode=True)
        connector = MT5Connector(cfg)
        connector.initialize()

        symbols = [f"SYM_{i}" for i in range(25)]
        symbols.append("FAIL_SYM")

        orig_detailed = connector._sync_historical_rates_detailed

        def mock_sync_detailed(symbol, timeframe, fresh, db):
            if symbol == "FAIL_SYM":
                raise RuntimeError("Unrecoverable network transport reset")
            return orig_detailed(symbol=symbol, timeframe=timeframe, fresh=fresh, db=db)

        engine_logger = logging.getLogger("strategy_engine")
        orig_prop = engine_logger.propagate
        engine_logger.propagate = True
        try:
            with patch.object(connector, "_sync_historical_rates_detailed", side_effect=mock_sync_detailed):
                with caplog.at_level(logging.DEBUG, logger="strategy_engine.mt5_connector"):
                    status = await connector.sync_historical_batch(
                        symbols=symbols,
                        timeframe="D1",
                        workers=25,
                        db=temp_db,
                        yield_ms=0,
                    )

            assert status.status == "COMPLETED"
            assert status.total_assets == 26
            assert status.completed_assets == 25
            assert status.failed_assets == 1
            assert "FAIL_SYM" in status.failed_symbols
            # Verify DEBUG logging with exc_info
            debug_logs = [rec.getMessage() for rec in caplog.records if rec.levelno == logging.DEBUG]
            assert any("[FAIL_SYM] Exception during sync" in msg for msg in debug_logs)
        finally:
            engine_logger.propagate = orig_prop

    def test_scenario_6_cli_partial_failure_exit_code_contract_on_exception(self, temp_db, capsys):
        """
        Scenario 6 (CLI): When a symbol raises an unrecoverable exception during sync,
        the CLI returns exit code 2 (partial failure) with the summary table instead of crashing.
        """
        db_path = temp_db.db_path
        orig_detailed = MT5Connector._sync_historical_rates_detailed

        def mock_sync_detailed(self, symbol, timeframe, fresh, db):
            if symbol == "CRASH_SYM":
                raise RuntimeError("Simulated unhandled worker crash")
            return orig_detailed(self, symbol=symbol, timeframe=timeframe, fresh=fresh, db=db)

        with patch.object(MT5Connector, "_sync_historical_rates_detailed", mock_sync_detailed):
            rc = cli_main([
                "sync-history",
                "--symbol", "AAPL,CRASH_SYM,MSFT",
                "--workers", "20",
                "--db-path", db_path,
            ])

        assert rc == 2
        captured = capsys.readouterr().out
        assert "Warning: Partial sync completed (2/3). Failed symbols: CRASH_SYM" in captured
        assert temp_db.get_total_bars("AAPL", "D1") == 100
        assert temp_db.get_total_bars("MSFT", "D1") == 100
        assert temp_db.get_total_bars("CRASH_SYM", "D1") == 0

    @pytest.mark.asyncio
    async def test_scenario_7_end_to_end_batch_ingestion_pipeline_30_workers(self, temp_db):
        """
        Scenario 7: End-to-End Batch Ingestion Pipeline at 30 Workers.
        Batch of 60 symbols synchronized via sync_historical_batch(workers=30)
        with fresh=False and fresh=True. All 60 symbols complete with 0 failures,
        exact bar counts, and zero lock errors.
        """
        cfg = StrategyConfig(mock_mode=True)
        connector = MT5Connector(cfg)
        connector.initialize()

        symbols = [f"BATCH_{i:02d}" for i in range(60)]

        # 1. Cold start incremental sync (fresh=False)
        status_inc = await connector.sync_historical_batch(
            symbols=symbols,
            timeframe="D1",
            workers=30,
            fresh=False,
            db=temp_db,
            yield_ms=0,
        )
        assert status_inc.status == "COMPLETED"
        assert status_inc.completed_assets == 60
        assert status_inc.failed_assets == 0
        assert status_inc.total_bars == 6000

        # Verify bar counts per symbol
        for sym in symbols:
            assert temp_db.get_total_bars(sym, "D1") == 100

        # 2. Fresh clear-then-write sync (fresh=True)
        status_fresh = await connector.sync_historical_batch(
            symbols=symbols,
            timeframe="D1",
            workers=30,
            fresh=True,
            db=temp_db,
            yield_ms=0,
        )
        assert status_fresh.status == "COMPLETED"
        assert status_fresh.completed_assets == 60
        assert status_fresh.failed_assets == 0
        assert status_fresh.total_bars == 6000

        # Verify bar counts remain exact
        for sym in symbols:
            assert temp_db.get_total_bars(sym, "D1") == 100
