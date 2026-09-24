"""
Unit and integration tests for CLI sync-history command and parallel multi-symbol worker pool.
Covers Gherkin scenarios for Issue #93 (Slice 1 of Parent #92).
"""
import asyncio
import pytest
from unittest.mock import patch

from strategy_engine.cli import main as cli_main, parse_symbols
from strategy_engine.config import StrategyConfig
from strategy_engine.historical_db import HistoricalRatesDB
from strategy_engine.models import HistoricalSyncStatus
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
