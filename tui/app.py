"""
Main Application Shell for Darwin Trader Terminal User Interface (TUI).
Provides base layout, header bar, summary cards, positions table,
and dual keybindings (F2 and C) to invoke connection modal.
"""
from typing import Optional
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.events import Resize
from textual.widgets import Footer

from .api_client import DarwinApiClient
from .screens.connect_modal import ConnectModal
from .widgets.header_bar import HeaderBar
from .widgets.summary_cards import SummaryCards
from .widgets.positions_table import PositionsTable


class DarwinTraderApp(App[None]):
    """Darwin Trader Terminal User Interface Application."""

    CSS = """
    Screen {
        background: $background;
        color: $text;
    }

    #main-viewport {
        height: 1fr;
    }

    #main-container {
        height: auto;
        min-height: 100%;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("f2", "open_connect_modal", "Connect", show=True),
        Binding("c", "open_connect_modal", "Connect", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(
        self,
        api_client: Optional[DarwinApiClient] = None,
        poll_interval: float = 3.0,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.api_client = api_client or DarwinApiClient()
        self.poll_interval = poll_interval
        self._countdown: int = int(poll_interval)
        self._reconnect_timer = None

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header-bar")
        with VerticalScroll(id="main-viewport"):
            with Container(id="main-container"):
                yield SummaryCards(id="summary-cards")
                yield PositionsTable(id="positions-table")
        yield Footer()

    async def on_mount(self) -> None:
        """Called when app is mounted; initiates background telemetry polling."""
        await self.poll_telemetry()
        self._reconnect_timer = self.set_interval(1.0, self._tick_timer)

    def on_resize(self, event: Resize) -> None:
        """Responsive behavior: collapse SummaryCards into 2x2 grid below 80 cols or 24 rows."""
        try:
            summary = self.query_one(SummaryCards)
            if event.size.width < 80 or event.size.height < 24:
                summary.set_compact_layout(True)
            else:
                summary.set_compact_layout(False)
        except Exception:
            pass

    async def _tick_timer(self) -> None:
        """Timer callback running every second to update countdown or trigger poll."""
        self._countdown -= 1
        if self._countdown <= 0:
            self._countdown = int(self.poll_interval)
            await self.poll_telemetry()
        else:
            try:
                header = self.query_one(HeaderBar)
                if header._is_offline:
                    status = await self.api_client.get_account_status()
                    header.update_telemetry(status, reconnect_seconds=self._countdown)
            except Exception:
                pass

    async def poll_telemetry(self) -> None:
        """Polls backend status and updates widgets without unhandled exceptions."""
        try:
            status = await self.api_client.get_account_status()
            header = self.query_one(HeaderBar)
            header.update_telemetry(status, reconnect_seconds=self._countdown)

            summary = self.query_one(SummaryCards)
            positions_tbl = self.query_one(PositionsTable)

            if status.account_info:
                summary.update_metrics(account_info=status.account_info)
            else:
                info = await self.api_client.get_account_info()
                if info:
                    summary.update_metrics(account_info=info)

            # Positions polling
            is_offline = (status.status != "CONNECTED")
            positions = await self.api_client.get_positions()
            positions_tbl.update_positions(positions, is_offline=is_offline)
        except Exception:
            pass

    def action_open_connect_modal(self) -> None:
        """Action invoked by F2 or C keybinding or button to open connect modal."""
        self.push_screen(ConnectModal())

    async def on_button_pressed(self, event) -> None:
        """Handles button clicks, such as the Connect button in HeaderBar."""
        if getattr(event.button, "id", None) == "btn-connect":
            self.action_open_connect_modal()


if __name__ == "__main__":
    app = DarwinTraderApp()
    app.run()
