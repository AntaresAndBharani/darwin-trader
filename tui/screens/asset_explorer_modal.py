"""
AssetExplorerModal screen for Darwin Trader TUI.
Allows browsing, filtering by category (stocks, etfs, forex, all),
and real-time substring searching of all tradeable assets and contract specifications.
"""
from typing import List, Optional
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Select, Static

from strategy_engine.models import AssetInfo
from tui.api_client import DarwinApiClient


CATEGORY_OPTIONS = [
    ("Stocks (US / EU)", "stocks"),
    ("ETFs", "etfs"),
    ("Forex", "forex"),
    ("All Assets", "all"),
]


class AssetExplorerModal(ModalScreen[None]):
    """Modal dialog for browsing tradeable MT5 assets and contract specs."""

    DEFAULT_CSS = """
    AssetExplorerModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #asset-explorer-dialog {
        width: 90%;
        height: 85%;
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

    #filter-bar {
        height: auto;
        margin-bottom: 1;
        align: left middle;
    }

    #category-select {
        width: 25;
        margin-right: 1;
    }

    #asset-search-input {
        width: 1fr;
    }

    #status-bar {
        color: $text-muted;
        text-style: italic;
        padding: 0 1;
        margin-bottom: 1;
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

    DataTable {
        height: 1fr;
        border: solid $primary-darken-2;
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
        Binding("s", "focus_search", "Search", show=False),
    ]

    def __init__(
        self,
        api_client: Optional[DarwinApiClient] = None,
        default_category: str = "stocks",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.api_client = api_client or DarwinApiClient()
        self.current_category = default_category
        self._current_assets: List[AssetInfo] = []

    def compose(self) -> ComposeResult:
        with Container(id="asset-explorer-dialog"):
            yield Static("DARWINEX ASSET EXPLORER [A / F3]", classes="modal-title", id="modal-title")
            with Horizontal(id="filter-bar"):
                yield Select[str](
                    options=CATEGORY_OPTIONS,
                    value=self.current_category,
                    allow_blank=False,
                    id="category-select",
                )
                yield Input(
                    placeholder="Search ticker or company (e.g. NVDA, Apple)...",
                    id="asset-search-input",
                )
            yield Static("", id="error-banner")
            yield Static("Loading assets...", id="status-bar")
            yield DataTable(id="assets-data-table", cursor_type="row")
            with Horizontal(classes="modal-footer"):
                yield Static(
                    "[↑/↓] Navigate  |  [S] Focus Search  |  [ESC] Close",
                    classes="help-hint",
                )
                yield Button("Close", id="btn-close", variant="default")

    async def on_mount(self) -> None:
        """Initialize table columns and load initial asset catalog."""
        table = self.query_one("#assets-data-table", DataTable)
        table.add_columns(
            "Symbol",
            "Description",
            "Category",
            "CCY",
            "Min Lot",
            "Max Lot",
            "Bid",
            "Ask",
        )
        await self._load_assets(category=self.current_category)

    async def _load_assets(self, category: str, search: str = "") -> None:
        """Loads and populates assets from API gateway with error resilience."""
        table = self.query_one("#assets-data-table", DataTable)
        status = self.query_one("#status-bar", Static)
        error_banner = self.query_one("#error-banner", Static)

        status.update(f"Fetching {category} assets...")
        error_banner.remove_class("visible")

        try:
            assets = await self.api_client.get_assets(
                category=category if category != "all" else "all",
                search=search.strip() if search else None,
            )
            self._current_assets = assets
            table.clear()

            for asset in assets:
                bid_str = f"{asset.bid:.2f}" if asset.bid is not None else "--"
                ask_str = f"{asset.ask:.2f}" if asset.ask is not None else "--"
                table.add_row(
                    Text(asset.symbol, style="bold cyan"),
                    asset.description,
                    asset.category,
                    asset.currency,
                    f"{asset.lot_min:.2f}",
                    f"{asset.lot_max:.2f}",
                    bid_str,
                    ask_str,
                    key=asset.symbol,
                )

            search_info = f' matching "{search.strip()}"' if search.strip() else ""
            status.update(f"Showing {len(assets)} {category} assets{search_info}")

            if len(assets) == 0 and not search.strip():
                status.update(f"No assets found for category '{category}' (Gateway may be in mock or offline mode)")

        except Exception as exc:
            error_banner.update(f"Error loading assets: {exc}")
            error_banner.add_class("visible")
            status.update("Failed to retrieve asset catalog from gateway")

    @on(Select.Changed, "#category-select")
    async def on_category_changed(self, event: Select.Changed) -> None:
        if event.value and event.value != Select.BLANK:
            self.current_category = str(event.value)
            search_val = self.query_one("#asset-search-input", Input).value
            await self._load_assets(category=self.current_category, search=search_val)

    @on(Input.Changed, "#asset-search-input")
    async def on_search_changed(self, event: Input.Changed) -> None:
        await self._load_assets(category=self.current_category, search=event.value)

    @on(Button.Pressed, "#btn-close")
    def on_close_pressed(self) -> None:
        self.dismiss(None)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    def action_focus_search(self) -> None:
        self.query_one("#asset-search-input", Input).focus()
