"""
HeaderBar widget for Darwin Trader TUI.
Displays live telemetry: connection badge, broker server, account login ID, and reconnect countdown.
"""
from typing import Optional
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static, Button

from strategy_engine.models import ConnectionState, ConnectionStatus


class HeaderBar(Horizontal):
    """Top telemetry bar displaying connection status and server info."""

    DEFAULT_CSS = """
    HeaderBar {
        dock: top;
        height: 3;
        background: $surface;
        color: $text;
        padding: 0 1;
        border-bottom: solid $primary;
        align-vertical: middle;
    }

    .title {
        text-style: bold;
        color: $accent;
        width: 18;
    }

    .status-badge {
        width: 28;
        text-style: bold;
    }

    .status-connected-live {
        color: $success;
    }

    .status-connected-demo {
        color: $primary;
    }

    .status-simulation {
        color: $warning;
    }

    .status-offline {
        color: $error;
    }

    .telemetry-info {
        width: 1fr;
        color: $text-muted;
    }

    .connect-btn {
        width: 16;
        min-width: 14;
        height: 1;
        border: none;
    }
    """

    def __init__(
        self,
        *children,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
        disabled: bool = False,
    ) -> None:
        super().__init__(*children, name=name, id=id, classes=classes, disabled=disabled)
        self._status: ConnectionState = ConnectionState.DISCONNECTED
        self._server: str = "Unreachable"
        self._login: int = 0
        self._mock_mode: bool = False
        self._reconnect_seconds: int = 3
        self._is_offline: bool = True

    def compose(self) -> ComposeResult:
        yield Static("DARWIN TRADER", classes="title")
        yield Static("[○ GATEWAY UNREACHABLE (3s)]", id="status-badge", classes="status-badge status-offline")
        yield Static("Server: -- | Login: --", id="telemetry-info", classes="telemetry-info")
        yield Button("Connect [F2/C]", id="btn-connect", classes="connect-btn")

    def update_telemetry(
        self,
        status: ConnectionStatus,
        login: Optional[int] = None,
        reconnect_seconds: Optional[int] = None,
    ) -> None:
        """Updates header bar visuals according to connection status."""
        badge_widget = self.query_one("#status-badge", Static)
        info_widget = self.query_one("#telemetry-info", Static)

        if reconnect_seconds is not None:
            self._reconnect_seconds = reconnect_seconds

        if status.status == ConnectionState.CONNECTED:
            self._is_offline = False
            login_val = login or (status.account_info.login if status.account_info else 0)
            server_val = status.server or "Darwinex"

            if status.mock_mode or "mock" in server_val.lower() or "sim" in server_val.lower():
                badge_widget.update("[● SIMULATION]")
                badge_widget.remove_class("status-connected-live", "status-connected-demo", "status-offline")
                badge_widget.add_class("status-simulation")
            elif "demo" in server_val.lower():
                badge_widget.update("[● CONNECTED (DEMO)]")
                badge_widget.remove_class("status-connected-live", "status-simulation", "status-offline")
                badge_widget.add_class("status-connected-demo")
            else:
                badge_widget.update("[● CONNECTED (LIVE)]")
                badge_widget.remove_class("status-connected-demo", "status-simulation", "status-offline")
                badge_widget.add_class("status-connected-live")

            info_widget.update(f"Server: {server_val} | Login: {login_val} | Latency: {status.latency_ms:.1f}ms")
        else:
            self._is_offline = True
            badge_widget.update(f"[○ GATEWAY UNREACHABLE ({self._reconnect_seconds}s)]")
            badge_widget.remove_class("status-connected-live", "status-connected-demo", "status-simulation")
            badge_widget.add_class("status-offline")
            info_widget.update(f"Server: {status.server or '--'} | Login: -- | {status.last_error or 'Offline'}")
