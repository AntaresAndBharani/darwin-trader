"""
ConnectModal screen placeholder for MT5 connection dialog.
Triggered via F2, C, or Connect button.
"""
from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConnectModal(ModalScreen[None]):
    """Modal dialog for MT5 Account Connection."""

    DEFAULT_CSS = """
    ConnectModal {
        align: center middle;
    }

    #connect-dialog {
        grid-size: 1;
        grid-gutter: 1;
        padding: 1 2;
        width: 50;
        height: 12;
        border: thick $primary;
        background: $surface;
    }

    .modal-title {
        text-style: bold;
        text-align: center;
        color: $accent;
    }

    .modal-btn {
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        with Grid(id="connect-dialog"):
            yield Static("MT5 Account Connection", classes="modal-title")
            yield Static("Connection dialog [F2 / C]")
            yield Button("Close", id="btn-close", classes="modal-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-close":
            self.dismiss()
