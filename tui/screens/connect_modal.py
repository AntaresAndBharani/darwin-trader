"""
ConnectModal screen for MT5 account connection dialog.
Supports fields for Login, Password, Server dropdown, Path, and Mock Mode.
Displays connecting spinner and inline error banners when connection fails.
"""
import inspect
from typing import Any, Callable, Optional
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Select, Static

from strategy_engine.models import AccountConnectRequest, ConnectionState
from tui.api_client import DarwinApiClient


SERVER_CHOICES = [
    ("Darwinex-Demo", "Darwinex-Demo"),
    ("Darwinex-Live", "Darwinex-Live"),
    ("MetaQuotes-Demo", "MetaQuotes-Demo"),
]


class ConnectModal(ModalScreen[Optional[AccountConnectRequest]]):
    """Modal dialog for MT5 Account Connection."""

    DEFAULT_CSS = """
    ConnectModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #connect-dialog {
        width: 65;
        height: auto;
        max-height: 90%;
        overflow-y: auto;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }

    .modal-title {
        text-style: bold;
        text-align: center;
        color: $accent;
        margin-bottom: 0;
    }

    .form-field {
        height: auto;
        margin-bottom: 0;
    }

    .form-label {
        color: $text-muted;
        text-style: bold;
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

    #spinner-banner {
        background: $primary-darken-3;
        color: $accent;
        padding: 0 1;
        margin-bottom: 1;
        text-style: bold;
        text-align: center;
        display: none;
    }

    #spinner-banner.visible {
        display: block;
    }

    .modal-actions {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    .modal-actions Button {
        margin: 0 1;
        min-width: 14;
    }
    """

    def __init__(
        self,
        api_client: Optional[DarwinApiClient] = None,
        on_success: Optional[Callable[[AccountConnectRequest], Any]] = None,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.api_client = api_client
        self.on_success = on_success

    def compose(self) -> ComposeResult:
        with Container(id="connect-dialog"):
            yield Static("MT5 Account Connection [F2 / C]", classes="modal-title")
            yield Static("", id="error-banner")
            yield Static("Connecting to MT5 Gateway... ⏳", id="spinner-banner")

            with Vertical(classes="form-field"):
                yield Static("Login ID:", classes="form-label")
                yield Input(placeholder="e.g. 1234567", id="input-login", type="integer")

            with Vertical(classes="form-field"):
                yield Static("Password:", classes="form-label")
                yield Input(placeholder="MT5 account password", id="input-password", password=True)

            with Vertical(classes="form-field"):
                yield Static("Server:", classes="form-label")
                yield Select(
                    options=[(s, s) for s, _ in SERVER_CHOICES],
                    value="Darwinex-Demo",
                    id="select-server",
                )

            with Vertical(classes="form-field"):
                yield Static("Terminal Path (Optional):", classes="form-label")
                yield Input(placeholder="Optional path to terminal64.exe", id="input-path")

            with Horizontal(classes="form-field"):
                yield Checkbox("Mock Mode", value=True, id="checkbox-mock")

            with Horizontal(classes="modal-actions"):
                yield Button("Connect", variant="primary", id="btn-submit")
                yield Button("Close", id="btn-close")

    def show_error(self, message: str) -> None:
        """Displays error banner with error message."""
        banner = self.query_one("#error-banner", Static)
        banner.update(f"⚠ Error: {message}")
        banner.add_class("visible")
        spinner = self.query_one("#spinner-banner", Static)
        spinner.remove_class("visible")

    def clear_error(self) -> None:
        """Hides error banner."""
        banner = self.query_one("#error-banner", Static)
        banner.update("")
        banner.remove_class("visible")

    def show_spinner(self) -> None:
        """Displays connecting spinner."""
        spinner = self.query_one("#spinner-banner", Static)
        spinner.add_class("visible")
        self.clear_error()

    def hide_spinner(self) -> None:
        """Hides connecting spinner."""
        spinner = self.query_one("#spinner-banner", Static)
        spinner.remove_class("visible")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-close":
            self.dismiss(None)
        elif event.button.id == "btn-submit":
            await self._handle_connect()

    async def _handle_connect(self) -> None:
        login_raw = self.query_one("#input-login", Input).value.strip()
        password = self.query_one("#input-password", Input).value
        server_val = self.query_one("#select-server", Select).value
        server = str(server_val) if server_val is not Select.BLANK else "Darwinex-Demo"
        path_raw = self.query_one("#input-path", Input).value.strip()
        path = path_raw if path_raw else None
        mock_mode = self.query_one("#checkbox-mock", Checkbox).value

        try:
            login = int(login_raw) if login_raw else 0
        except ValueError:
            self.show_error("Login ID must be a valid integer")
            return

        req = AccountConnectRequest(
            login=login,
            password=password,
            server=server,
            path=path,
            mock_mode=mock_mode,
        )

        client = self.api_client or getattr(self.app, "api_client", None)
        if client is None:
            self.dismiss(req)
            return

        self.show_spinner()
        try:
            resp = await client.connect_account(req)
            if resp.status == ConnectionState.CONNECTED:
                self.hide_spinner()
                if self.on_success:
                    res = self.on_success(req)
                    if inspect.isawaitable(res):
                        await res
                self.dismiss(req)
            else:
                err_msg = resp.error or resp.message or "Connection failed"
                self.show_error(err_msg)
        except Exception as exc:
            self.show_error(str(exc))
