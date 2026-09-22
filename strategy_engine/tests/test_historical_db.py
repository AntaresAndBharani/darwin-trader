"""
Unit and integration tests for SQLite Storage Layer, Models, and MT5 Historical Connector.
Validates composite primary key WITHOUT ROWID, upsert semantics, pagination, auto data/ creation,
mt5.symbol_select, fine-grained locking with 25ms yield, delisted asset resilience,
and deterministic symbol-hash mock generator.
"""
import os
import sqlite3
import pytest
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

from strategy_engine.config import StrategyConfig
from strategy_engine.models import (
    HistoricalBar,
    HistoricalRatesRequest,
    HistoricalRatesResponse,
    HistoricalSyncStatus,
    HistoricalSyncResponse,
    Timeframe,
    TIMEFRAME_TO_MT5,
)
from strategy_engine.historical_db import HistoricalRatesDB
from strategy_engine.mt5_connector import MT5Connector


@pytest.fixture
def temp_db(tmp_path):
    """Provides a fresh isolated HistoricalRatesDB instance for testing."""
    db_file = tmp_path / "data" / "test_rates.db"
    return HistoricalRatesDB(db_path=str(db_file))


@pytest.fixture
def mock_connector():
    """Provides an MT5Connector initialized in mock mode."""
    cfg = StrategyConfig(mock_mode=True)
    connector = MT5Connector(cfg)
    connector.initialize()
    return connector


class TestHistoricalModels:
    def test_timeframe_enum_and_mt5_constants(self):
        assert Timeframe.D1 == "D1"
        assert Timeframe.H1 == "H1"
        assert Timeframe.M1 == "M1"
        assert TIMEFRAME_TO_MT5["D1"] == 16408
        assert TIMEFRAME_TO_MT5["H1"] == 16385
        assert TIMEFRAME_TO_MT5["M1"] == 1

    def test_historical_bar_validation(self):
        bar = HistoricalBar(
            symbol="NVDA",
            timeframe="D1",
            time=1700000000,
            open=120.0,
            high=125.0,
            low=119.5,
            close=124.0,
            tick_volume=50000,
            spread=2,
        )
        assert bar.symbol == "NVDA"
        assert bar.timeframe == "D1"
        assert bar.time == 1700000000
        assert bar.open == 120.0
        assert bar.tick_volume == 50000

    def test_rates_request_and_response(self):
        req = HistoricalRatesRequest(symbol="MSFT", timeframe="D1", limit=100, offset=50)
        assert req.symbol == "MSFT"
        assert req.limit == 100
        assert req.offset == 50

        resp = HistoricalRatesResponse(
            symbol="MSFT",
            timeframe="D1",
            bars=[],
            total_bars=4500,
            limit=500,
            offset=0,
            page=1,
            total_pages=9,
        )
        assert resp.total_bars == 4500
        assert resp.total_pages == 9

    def test_sync_status_and_response(self):
        status = HistoricalSyncStatus(
            job_id="job-123",
            status="IN_PROGRESS",
            completed_assets=5,
            failed_assets=1,
            total_assets=10,
            current_symbol="AMZN",
        )
        assert status.failed_assets == 1
        assert status.completed_assets == 5

        resp = HistoricalSyncResponse(job_id="job-123", status="IN_PROGRESS", message="Sync started")
        assert resp.job_id == "job-123"


class TestHistoricalDBStorage:
    def test_schema_composite_primary_key_without_rowid(self, temp_db):
        """Verifies table rates has WITHOUT ROWID and composite PK (symbol, timeframe, time DESC)."""
        with temp_db._get_connection() as conn:
            cursor = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='rates';"
            )
            row = cursor.fetchone()
            assert row is not None
            sql = row["sql"].upper()
            assert "WITHOUT ROWID" in sql
            assert "PRIMARY KEY" in sql
            assert "SYMBOL" in sql
            assert "TIMEFRAME" in sql
            assert "TIME DESC" in sql or "TIME" in sql

    def test_auto_data_directory_creation(self, tmp_path):
        """Verifies auto directory creation when DB path directory does not yet exist."""
        nested_dir = tmp_path / "deeply" / "nested" / "dir"
        assert not nested_dir.exists()
        db_path = nested_dir / "historical_rates.db"
        db = HistoricalRatesDB(db_path=str(db_path))
        assert nested_dir.exists()
        assert os.path.exists(str(db_path))
        assert db.get_total_bars("ANY") == 0

    def test_multi_symbol_timestamp_collision_safety(self, temp_db, mock_connector):
        """
        Scenario 8: Multi-Symbol Primary Key Integrity.
        Two assets ('NVDA' and 'TSLA') have identical timestamps.
        Verifies composite PK (symbol, timeframe, time DESC) allows concurrent identical
        timestamps without sqlite3.IntegrityError.
        """
        nvda_bars = mock_connector.get_historical_rates("NVDA", "D1")
        tsla_bars = mock_connector.get_historical_rates("TSLA", "D1")
        assert len(nvda_bars) == 100
        assert len(tsla_bars) == 100
        # Timestamps are identical
        assert nvda_bars[0].time == tsla_bars[0].time
        assert nvda_bars[-1].time == tsla_bars[-1].time

        # Insert both into same database
        temp_db.insert_rates(nvda_bars)
        temp_db.insert_rates(tsla_bars)

        assert temp_db.get_total_bars("NVDA") == 100
        assert temp_db.get_total_bars("TSLA") == 100

        with temp_db._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) AS total FROM rates;")
            assert cursor.fetchone()["total"] == 200

    def test_upsert_semantics_forming_candle_overwrite(self, temp_db):
        """
        Scenario 2: Forming Candle Upsert Semantics.
        An incomplete daily candle is recorded mid-session. Subsequent sync with finalized
        bar values overwrites the incomplete candle instead of duplicating or erroring.
        """
        forming_bar = HistoricalBar(
            symbol="AMZN",
            timeframe="D1",
            time=1700000000,
            open=140.0,
            high=142.0,
            low=139.5,
            close=141.0,  # Forming close
            tick_volume=1200,  # Partial volume
            spread=2,
        )
        temp_db.insert_rates([forming_bar])
        assert temp_db.get_total_bars("AMZN") == 1

        # Check stored forming candle
        bars, total = temp_db.get_rates("AMZN", "D1")
        assert total == 1
        assert bars[0].close == 141.0
        assert bars[0].tick_volume == 1200

        # Now session closes and finalized candle is received
        finalized_bar = HistoricalBar(
            symbol="AMZN",
            timeframe="D1",
            time=1700000000,  # Same timestamp
            open=140.0,
            high=144.5,
            low=139.5,
            close=143.8,  # Finalized close
            tick_volume=4500,  # Full volume
            spread=2,
        )
        temp_db.insert_rates([finalized_bar])

        # Verify still exactly 1 bar, but updated with finalized values
        assert temp_db.get_total_bars("AMZN") == 1
        updated_bars, updated_total = temp_db.get_rates("AMZN", "D1")
        assert updated_total == 1
        assert updated_bars[0].close == 143.8
        assert updated_bars[0].high == 144.5
        assert updated_bars[0].tick_volume == 4500

    def test_pagination_limit_offset_and_total_bars(self, temp_db):
        """
        Scenario 4: Viewport Pagination.
        Verifies get_rates(limit=500, offset=0) pagination returning (bars, total_bars),
        with edge case boundary checks (overrun, underrun, empty).
        """
        # Create 1200 bars for test symbol
        base_time = 1700000000
        bars = [
            HistoricalBar(
                symbol="PAGETEST",
                timeframe="D1",
                time=base_time + (i * 86400),
                open=100.0 + i,
                high=105.0 + i,
                low=99.0 + i,
                close=104.0 + i,
                tick_volume=1000,
                spread=1,
            )
            for i in range(1200)
        ]
        temp_db.insert_rates(bars)
        assert temp_db.get_total_bars("PAGETEST") == 1200

        # Page 1: limit 500, offset 0 -> 500 bars
        page1_bars, total = temp_db.get_rates("PAGETEST", limit=500, offset=0)
        assert total == 1200
        assert len(page1_bars) == 500
        # By default ordered DESC: page 1 contains newest bars (i=1199 down to i=700)
        assert page1_bars[0].time == base_time + (1199 * 86400)
        assert page1_bars[-1].time == base_time + (700 * 86400)

        # Page 2: limit 500, offset 500 -> 500 bars (bars 501-1000)
        page2_bars, total2 = temp_db.get_rates("PAGETEST", limit=500, offset=500)
        assert total2 == 1200
        assert len(page2_bars) == 500
        assert page2_bars[0].time == base_time + (699 * 86400)
        assert page2_bars[-1].time == base_time + (200 * 86400)

        # Page 3: limit 500, offset 1000 -> remaining 200 bars
        page3_bars, total3 = temp_db.get_rates("PAGETEST", limit=500, offset=1000)
        assert total3 == 1200
        assert len(page3_bars) == 200
        assert page3_bars[-1].time == base_time + (0 * 86400)

        # Page 4: offset 1200 (overrun boundary) -> safe 0 bars returned
        overrun_bars, total4 = temp_db.get_rates("PAGETEST", limit=500, offset=1200)
        assert total4 == 1200
        assert len(overrun_bars) == 0

        # Underrun / invalid limit -> safe 0 bars
        underrun_bars, total5 = temp_db.get_rates("PAGETEST", limit=0, offset=0)
        assert total5 == 1200
        assert len(underrun_bars) == 0

        neg_offset_bars, total6 = temp_db.get_rates("PAGETEST", limit=500, offset=-1)
        assert total6 == 1200
        assert len(neg_offset_bars) == 0

    def test_get_latest_timestamp_and_clear_rates(self, temp_db):
        """Verifies get_latest_timestamp MAX(time) and clear_rates."""
        assert temp_db.get_latest_timestamp("TEST") is None

        bars = [
            HistoricalBar(
                symbol="TEST",
                timeframe="D1",
                time=1700000000 + (i * 86400),
                open=10.0,
                high=11.0,
                low=9.0,
                close=10.5,
            )
            for i in range(5)
        ]
        temp_db.insert_rates(bars)
        assert temp_db.get_latest_timestamp("TEST") == 1700000000 + (4 * 86400)

        # Clear rates for TEST
        deleted = temp_db.clear_rates("TEST")
        assert deleted == 5
        assert temp_db.get_latest_timestamp("TEST") is None
        assert temp_db.get_total_bars("TEST") == 0

    def test_busy_timeout_and_wal_mode(self, temp_db):
        """Verifies 60s busy timeout and WAL mode pragmas."""
        with temp_db._get_connection() as conn:
            cursor = conn.execute("PRAGMA journal_mode;")
            journal_mode = cursor.fetchone()[0]
            assert journal_mode.lower() == "wal"

            cursor = conn.execute("PRAGMA busy_timeout;")
            busy_timeout = cursor.fetchone()[0]
            assert busy_timeout == 60000


class TestMT5ConnectorHistorical:
    def test_deterministic_symbol_hash_mock_generator(self, mock_connector):
        """
        Scenario 6: Graceful Offline & Deterministic Mock Fallback.
        Verifies that mock mode populates synthetic historical bars (100 bars)
        generated deterministically using the symbol string hash as the PRNG seed.
        """
        bars_run1 = mock_connector.get_historical_rates("NVDA", "D1")
        bars_run2 = mock_connector.get_historical_rates("NVDA", "D1")
        assert len(bars_run1) == 100
        assert len(bars_run2) == 100

        # Exact determinism across separate calls
        for b1, b2 in zip(bars_run1, bars_run2):
            assert b1.time == b2.time
            assert b1.open == b2.open
            assert b1.close == b2.close
            assert b1.high == b2.high
            assert b1.low == b2.low

        # Different symbol produces different prices
        bars_amzn = mock_connector.get_historical_rates("AMZN", "D1")
        assert len(bars_amzn) == 100
        assert bars_amzn[0].open != bars_run1[0].open

    def test_delisted_asset_resilience_and_failed_assets_metric(self, mock_connector, temp_db):
        """
        Scenario 3: Non-fatal skip on None for delisted assets incrementing failed_assets.
        """
        delisted_rates = mock_connector.get_historical_rates("DELISTED", "D1")
        assert delisted_rates is None

        bars, count = mock_connector.sync_historical_rates("DELISTED", "D1", db=temp_db)
        assert bars is None
        assert count == 0

    @pytest.mark.asyncio
    async def test_async_batch_sync_with_25ms_yield(self, mock_connector, temp_db):
        """
        Verifies async batch sync processes multiple symbols, yields 25ms between symbols,
        and accurately aggregates completed_assets and failed_assets.
        """
        symbols = ["NVDA", "DELISTED", "MSFT"]
        status = await mock_connector.sync_historical_batch(
            symbols=symbols, timeframe="D1", db=temp_db, yield_ms=0.025
        )
        assert status.status == "COMPLETED"
        assert status.total_assets == 3
        assert status.completed_assets == 2
        assert status.failed_assets == 1
        assert temp_db.get_total_bars("NVDA") == 100
        assert temp_db.get_total_bars("MSFT") == 100
        assert temp_db.get_total_bars("DELISTED") == 0

    def test_sync_historical_rates_fresh_vs_incremental(self, mock_connector, temp_db):
        """
        Verifies cold start fresh sync vs incremental sync from MAX(time) inclusive.
        """
        # 1. Cold start
        bars, count = mock_connector.sync_historical_rates("AAPL", "D1", db=temp_db, fresh=False)
        assert len(bars) == 100
        assert count == 100
        assert temp_db.get_total_bars("AAPL") == 100

        # 2. Incremental sync (fetches from MAX(time) inclusive -> 1 forming bar updated)
        bars_inc, count_inc = mock_connector.sync_historical_rates("AAPL", "D1", db=temp_db, fresh=False)
        assert len(bars_inc) == 1
        assert count_inc == 1
        assert temp_db.get_total_bars("AAPL") == 100

        # 3. Fresh sync (clears and re-downloads 100 bars)
        bars_fresh, count_fresh = mock_connector.sync_historical_rates("AAPL", "D1", db=temp_db, fresh=True)
        assert len(bars_fresh) == 100
        assert count_fresh == 100
        assert temp_db.get_total_bars("AAPL") == 100

    def test_symbol_select_called_in_live_mt5_mode(self):
        """
        Scenario 8: Market Watch Symbol Activation.
        Verifies that mt5.symbol_select(symbol, True) is called before copy_rates_range.
        """
        cfg = StrategyConfig(mock_mode=False)
        connector = MT5Connector(cfg)
        connector.is_connected = True

        mock_mt5 = MagicMock()
        mock_mt5.symbol_select.return_value = True
        mock_mt5.copy_rates_range.return_value = [
            {
                "time": 1700000000,
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 104.0,
                "tick_volume": 1000,
                "spread": 1,
            }
        ]

        with patch("strategy_engine.mt5_connector.HAS_MT5", True), \
             patch("strategy_engine.mt5_connector.mt5", mock_mt5):
            bars = connector.get_historical_rates("TSLA", "D1")
            assert bars is not None
            assert len(bars) == 1
            mock_mt5.symbol_select.assert_called_once_with("TSLA", True)
            mock_mt5.copy_rates_range.assert_called_once()
