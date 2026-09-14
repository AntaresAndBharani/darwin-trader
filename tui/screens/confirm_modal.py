"""
ConfirmModal screen for high-stakes action confirmations.
Supports danger warning styling for Kill Switch and informational prompt when no positions are open.
"""
from typing import Optional
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmModal(ModalScreen[bool]):
    """
    Modal confirmation dialog.
    Dismisses with True when confirmed, False when cancelled or rejected.
    """

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #confirm-dialog {
        width: 65;
        height: auto;
        min-height: 12;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }

    #confirm-dialog.dialog-danger {
        border: thick $error;
    }

    #confirm-dialog.dialog-info {
        border: thick $primary;
    }

    .modal-title {
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }

    .title-danger {
        color: $error;
    }

    .title-info {
        color: $accent;
    }

    .modal-prompt {
        text-align: center;
        margin-bottom: 1;
        height: auto;
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
        title: str,
        prompt: str,
        is_danger: bool = False,
        confirm_label: str = "Yes",
        cancel_label: str = "No",
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.dialog_title = title
        self.prompt = prompt
        self.is_danger = is_danger
        self.confirm_label = confirm_label
        self.cancel_label = cancel_label

    def compose(self) -> ComposeResult:
        dialog_class = "dialog-danger" if self.is_danger else "dialog-info"
        title_class = "title-danger" if self.is_danger else "title-info"

        with Container(id="confirm-dialog", classes=dialog_class):
            yield Static(self.dialog_title, id="confirm-title", classes=f"modal-title {title_class}")
            yield Static(self.prompt, id="confirm-prompt", classes="modal-prompt")
            with Horizontal(classes="modal-actions"):
                yield Button(self.confirm_label, variant="error" if self.is_danger else "primary", id="btn-confirm")
                yield Button(self.cancel_label, id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm":
            self.dismiss(True)
        elif event.button.id == "btn-cancel":
            self.dismiss(False)
