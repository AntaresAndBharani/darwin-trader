"""
HistoricalDataModal screen for Darwin Trader TUI.
Provides interactive historical OHLCV bar inspection with self-contained DataTable,
timeframe filtering, 500-bar viewport pagination with keyboard navigation (] / PgDn, [ / PgUp),
symbol-scoped fresh restart action (F5), in-place progress banner, and 409 conflict handling.
"""
import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Select, Static

from strategy_engine.models import ConnectionState, HistoricalBar
from tui.api_client import DarwinApiClient


TIMEFRAME_OPTIONS = [
    ("D1 (Daily)", "D1"),
    ("H4 (4 Hours)", "H4"),
    ("H1 (1 Hour)", "H1"),
    ("M30 (30 Min)", "M30"),
    ("M15 (15 Min)", "M15"),
    ("M5 (5 Min)", "M5"),
    ("M1 (1 Min)", "M1"),
    ("W1 (Weekly)", "W1"),
    ("MN1 (Monthly)", "MN1"),
]


class HistoricalDataModal(ModalScreen[None]):
    """Modal dialog for inspecting historical OHLCV bars with pagination and fresh restart."""

    DEFAULT_CSS = """
    HistoricalDataModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #historical-dialog {
        width: 95%;
        height: 90%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }

    .modal-title {
        text-style: bold;
        text-align: center;
        color: $accent;
        margin-bottom: 1;
    }

    #controls-bar {
        height: auto;
        margin-bottom: 1;
        align: left middle;
    }

    .control-label {
        color: $text-muted;
        margin-right: 1;
        text-style: bold;
        width: auto;
        height: auto;
        padding-top: 1;
    }

    #timeframe-select {
        width: 20;
        margin-right: 1;
    }

    #btn-fresh-restart {
        width: auto;
        margin-right: 1;
    }

    #simulation-badge {
        color: cyan;
        text-style: bold;
        width: auto;
        margin-left: 1;
        display: none;
    }

    #simulation-badge.visible {
        display: block;
    }

    #progress-banner {
        background: $primary-darken-3;
        color: $primary-lighten-2;
        border: solid $primary;
        padding: 0 1;
        margin-bottom: 1;
        text-style: bold;
        display: none;
    }

    #progress-banner.visible {
        display: block;
    }

    #error-banner {
        background: $error-darken-3;
        color: $error;
        border: solid $error;
        padding: 0 1;
        margin-bottom: 1;
        text-style: bold;
        display: none;
    }

    #error-banner.visible {
        display: block;
    }

    #status-bar {
        color: $text-muted;
        text-style: italic;
        padding: 0 1;
        margin-bottom: 1;
    }

    DataTable {
        height: 1fr;
        border: solid $primary-darken-2;
    }

    #pagination-bar {
        height: auto;
        margin-top: 1;
        align: left middle;
    }

    #page-footer {
        color: $text;
        text-style: bold;
        width: 1fr;
    }

    #footer-status {
        color: $warning;
        text-style: bold;
        width: auto;
        margin-left: 1;
    }

    .modal-footer {
        height: auto;
        margin-top: 1;
        align: right middle;
    }

    .help-hint {
        color: $text-muted;
        margin-right: 2;
        text-style: dim;
    }

    #btn-close {
        min-width: 12;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", show=True),
        Binding("]", "next_page", "Next Page", show=True),
        Binding("pagedown", "next_page", "Next Page", show=True),
        Binding("[", "prev_page", "Prev Page", show=True),
        Binding("pageup", "prev_page", "Prev Page", show=True),
        Binding("f5", "fresh_restart", "Fresh Restart", show=True),
    ]

    def __init__(
        self,
        symbol: str,
        digits: int = 2,
        timeframe: str = "D1",
        api_client: Optional[DarwinApiClient] = None,
        mock_mode: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.symbol = symbol.strip().upper()
        self.digits = digits
        self.current_timeframe = timeframe.strip().upper()
        self.api_client = api_client or DarwinApiClient()
        self._mock_mode = mock_mode
        self.limit = 500
        self.current_offset = 0
        self.total_bars = 0
        self.page = 1
        self.total_pages = 1
        self.current_bars: List[HistoricalBar] = []
        self._at_end_of_history = False

    def compose(self) -> ComposeResult:
        with Container(id="historical-dialog"):
            yield Static(
                f"HISTORICAL DATA INSPECTOR - {self.symbol}",
                classes="modal-title",
                id="modal-title",
            )
            with Horizontal(id="controls-bar"):
                yield Static("Timeframe: ", classes="control-label")
                yield Select[str](
                    options=TIMEFRAME_OPTIONS,
                    value=self.current_timeframe,
                    allow_blank=False,
                    id="timeframe-select",
                )
                yield Button("Fresh Restart (F5)", id="btn-fresh-restart", variant="warning")
                yield Static("[SIMULATION HISTORY]", id="simulation-badge", classes="badge-simulation")

            yield Static("", id="progress-banner")
            yield Static("", id="error-banner")
            yield Static("Loading historical data...", id="status-bar")
            yield DataTable(id="historical-data-table", cursor_type="row")

            with Horizontal(id="pagination-bar"):
                yield Static(
                    "Page 1 of 1 (Bars 0-0) | [PgDn/]] Next  [PgUp/[] Prev",
                    id="page-footer",
                )
                yield Static("", id="footer-status")

            with Horizontal(classes="modal-footer"):
                yield Static(
                    "[↑/↓] Navigate  |  [PgDn/]] Next  |  [PgUp/[] Prev  |  [F5] Fresh Restart  |  [ESC] Close",
                    classes="help-hint",
                )
                yield Button("Close", id="btn-close", variant="default")

    async def on_mount(self) -> None:
        """Initialize columns, check simulation mode, and load initial rates page."""
        table = self.query_one("#historical-data-table", DataTable)
        table.add_columns("Date", "Open", "High", "Low", "Close", "Volume", "Change %")
        await self._check_simulation_mode()
        await self._load_data()

    async def _check_simulation_mode(self) -> None:
        """Determines if simulation history badge should be shown."""
        badge = self.query_one("#simulation-badge", Static)
        if self._mock_mode:
            badge.add_class("visible")
            return
        try:
            status = await self.api_client.get_account_status()
            if status.mock_mode or status.status != ConnectionState.CONNECTED:
                self._mock_mode = True
                badge.add_class("visible")
            else:
                badge.remove_class("visible")
        except Exception:
            self._mock_mode = True
            badge.add_class("visible")

    def _format_date(self, timestamp: int) -> str:
        """Formats UNIX epoch timestamp to human readable date/time string."""
        try:
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            if self.current_timeframe in ("D1", "W1", "MN1"):
                return dt.strftime("%Y-%m-%d")
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(timestamp)

    def _update_footer(self) -> None:
        """Renders page status string and pagination boundary indicators."""
        page_footer = self.query_one("#page-footer", Static)
        footer_status = self.query_one("#footer-status", Static)

        if self.total_bars <= 0 or not self.current_bars:
            self.total_pages = max(1, (self.total_bars + self.limit - 1) // self.limit) if self.total_bars > 0 else 1
            self.page = max(1, min(self.total_pages, (self.current_offset // self.limit) + 1))
            start_bar = 0
            end_bar = 0
        else:
            self.total_pages = max(1, (self.total_bars + self.limit - 1) // self.limit)
            self.page = min(self.total_pages, (self.current_offset // self.limit) + 1)
            start_bar = self.current_offset + 1
            end_bar = min(self.current_offset + len(self.current_bars), self.total_bars)

        footer_text = f"Page {self.page} of {self.total_pages} (Bars {start_bar}-{end_bar}) | [PgDn/]] Next  [PgUp/[] Prev"
        if self._at_end_of_history:
            footer_text += " | [End of history]"
            footer_status.update("[End of history]")
        else:
            footer_status.update("")

        page_footer.update(footer_text)

    async def _load_data(self) -> None:
        """Fetches paginated historical rates from gateway and populates DataTable."""
        table = self.query_one("#historical-data-table", DataTable)
        status_bar = self.query_one("#status-bar", Static)
        error_banner = self.query_one("#error-banner", Static)

        status_bar.update(f"Fetching {self.symbol} {self.current_timeframe} rates (offset {self.current_offset})...")
        error_banner.remove_class("visible")

        try:
            resp = await self.api_client.get_historical_rates(
                symbol=self.symbol,
                timeframe=self.current_timeframe,
                limit=self.limit,
                offset=self.current_offset,
            )
            self.current_bars = resp.bars
            self.total_bars = resp.total_bars
            table.clear()

            for idx, bar in enumerate(self.current_bars):
                date_str = self._format_date(bar.time)
                open_str = f"{bar.open:.{self.digits}f}"
                high_str = f"{bar.high:.{self.digits}f}"
                low_str = f"{bar.low:.{self.digits}f}"
                close_str = f"{bar.close:.{self.digits}f}"
                vol_str = f"{bar.tick_volume:,}"

                if bar.open and bar.open > 0:
                    change_pct = ((bar.close - bar.open) / bar.open) * 100.0
                else:
                    change_pct = 0.0

                if change_pct > 0.0001:
                    change_text = Text(f"+{change_pct:.2f}%", style="bold green")
                elif change_pct < -0.0001:
                    change_text = Text(f"{change_pct:.2f}%", style="bold red")
                else:
                    change_text = Text("0.00%", style="dim")

                table.add_row(
                    date_str,
                    open_str,
                    high_str,
                    low_str,
                    close_str,
                    vol_str,
                    change_text,
                    key=f"{bar.time}_{idx}",
                )

            self._update_footer()
            status_bar.update(f"Displaying {len(self.current_bars)} bars for {self.symbol} ({self.current_timeframe})")
        except Exception as exc:
            self.current_bars = []
            table.clear()
            self._update_footer()
            error_banner.update(f"Error loading rates: {exc}")
            error_banner.add_class("visible")
            status_bar.update("Failed to retrieve historical rates")

    async def action_next_page(self) -> None:
        """Navigates to next page (] / PgDn) or clamps safely at end of history."""
        if self.page >= self.total_pages or (self.current_offset + self.limit) >= self.total_bars:
            self._at_end_of_history = True
            self._update_footer()
            return

        self._at_end_of_history = False
        self.current_offset += self.limit
        await self._load_data()

    async def action_prev_page(self) -> None:
        """Navigates to previous page ([ / PgUp) or safe no-op on Page 1."""
        if self.page <= 1 or self.current_offset <= 0:
            return

        self._at_end_of_history = False
        self.current_offset = max(0, self.current_offset - self.limit)
        await self._load_data()

    async def action_fresh_restart(self) -> None:
        """Submits scoped fresh sync request (F5) and updates progress banner."""
        if getattr(self, "_is_syncing", False):
            return
        self._is_syncing = True

        banner = self.query_one("#progress-banner", Static)
        banner.update(f"Refreshing {self.symbol} historical data...")
        banner.add_class("visible")

        try:
            resp = await self.api_client.sync_historical_rates(
                symbol=self.symbol,
                timeframe=self.current_timeframe,
                fresh=True,
            )

            # Check for 409 Conflict rejection
            if resp.status == "IN_PROGRESS" and (
                "already in progress" in (resp.message or "").lower()
                or "conflict" in (resp.message or "").lower()
            ):
                self.notify("Sync already in progress; please wait for completion", severity="warning")
                banner.remove_class("visible")
                banner.update("")
                return

            if resp.status == "ERROR":
                if "already in progress" in (resp.message or "").lower() or "409" in (resp.message or ""):
                    self.notify("Sync already in progress; please wait for completion", severity="warning")
                else:
                    self.notify(f"Sync failed: {resp.message}", severity="error")
                banner.remove_class("visible")
                banner.update("")
                return

            # Poll status until finished or max 1.5 seconds
            sync_failed = False
            fail_msg = ""
            for _ in range(30):
                status = await self.api_client.get_sync_status()
                if status.status in ("COMPLETED", "FAILED", "IDLE"):
                    if status.status == "FAILED":
                        sync_failed = True
                        fail_msg = status.message or "Sync failed"
                    break
                await asyncio.sleep(0.05)

            if sync_failed:
                self.notify(f"Sync failed: {fail_msg}", severity="error")

            self.current_offset = 0
            self._at_end_of_history = False
            await self._load_data()
        except Exception as exc:
            if "already in progress" in str(exc).lower() or "409" in str(exc):
                self.notify("Sync already in progress; please wait for completion", severity="warning")
            else:
                self.notify(f"Sync error: {exc}", severity="error")
        finally:
            self._is_syncing = False
            banner.remove_class("visible")
            banner.update("")

    async def on_key(self, event: events.Key) -> None:
        """Intercepts pagination and fresh restart keys regardless of child focus."""
        if event.key in ("]", "pagedown", "page_down"):
            event.prevent_default()
            event.stop()
            await self.action_next_page()
        elif event.key in ("[", "pageup", "page_up"):
            event.prevent_default()
            event.stop()
            await self.action_prev_page()
        elif event.key == "f5":
            event.prevent_default()
            event.stop()
            await self.action_fresh_restart()

    @on(Select.Changed, "#timeframe-select")
    async def on_timeframe_changed(self, event: Select.Changed) -> None:
        if event.value and event.value != Select.BLANK:
            self.current_timeframe = str(event.value)
            self.current_offset = 0
            self._at_end_of_history = False
            await self._load_data()

    @on(Button.Pressed, "#btn-fresh-restart")
    async def on_fresh_restart_pressed(self) -> None:
        await self.action_fresh_restart()

    @on(Button.Pressed, "#btn-close")
    def on_close_pressed(self) -> None:
        self.dismiss(None)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)
