"""
AssetExplorerModal screen for Darwin Trader TUI.
Allows hierarchical cascading category browsing (Class, Region, Exchange),
real-time client-side substring searching, separate category columns,
and fluid keyboard navigation.
"""
from typing import Dict, List, Optional, Set, Tuple
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Select, Static

from strategy_engine.models import AssetInfo, InstitutionalMetrics
from tui.api_client import DarwinApiClient


def parse_category_parts(category: Optional[str], symbol: Optional[str] = "") -> Tuple[str, str, str]:
    """
    Parses hierarchical category path into (Class, Region, Exchange).
    - Preserves exact source segment casing (e.g. 'ETFs', 'Stocks', 'Nasdaq').
    - Strips trailing segment if equal to asset symbol (case-insensitive).
    - Missing or empty attributes normalize to '--'.
    """
    if not category or not str(category).strip():
        return ("--", "--", "--")

    cleaned = str(category).replace("\\", "/").strip()
    parts = [p.strip() for p in cleaned.split("/") if p.strip()]
    if not parts:
        return ("--", "--", "--")

    sym = (symbol or "").strip()
    if sym and parts and parts[-1].upper() == sym.upper():
        parts.pop()

    cls_val = parts[0] if len(parts) >= 1 and parts[0] else "--"
    reg_val = parts[1] if len(parts) >= 2 and parts[1] else "--"
    exc_val = parts[2] if len(parts) >= 3 and parts[2] else "--"

    return (cls_val, reg_val, exc_val)


class AssetExplorerModal(ModalScreen[None]):
    """Modal dialog for browsing tradeable MT5 assets and contract specs with cascading filters."""

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

    #select-class {
        width: 17;
        margin-right: 1;
    }

    #select-region {
        width: 17;
        margin-right: 1;
    }

    #select-exchange {
        width: 17;
        margin-right: 1;
    }

    #asset-search-input {
        width: 1fr;
        margin-right: 1;
    }

    #btn-reset-filters {
        width: 13;
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

    #institutional-metrics-drawer {
        height: 4;
        border: solid $accent;
        background: $surface;
        padding: 0 1;
        display: none;
    }

    #institutional-metrics-drawer.visible {
        display: block;
    }

    #metrics-drawer-header {
        text-style: bold;
        color: $accent;
    }

    #metrics-drawer-content {
        color: $text;
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

    #btn-inspect-history {
        min-width: 16;
        margin-right: 1;
    }

    #btn-close {
        min-width: 12;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", show=True),
        Binding("h", "inspect_history", "Inspect History", show=True),
        Binding("H", "inspect_history", "Inspect History", show=False),
        Binding("i", "toggle_metrics_drawer", "Metrics", show=True),
        Binding("I", "toggle_metrics_drawer", "Metrics", show=False),
        Binding("s", "focus_search", "Search", show=False),
        Binding("f4", "reset_filters", "Reset Filters", show=True),
        Binding("F4", "reset_filters", "Reset Filters", show=False),
    ]

    def __init__(
        self,
        api_client: Optional[DarwinApiClient] = None,
        default_category: Optional[str] = None,
        debounce_delay: float = 0.15,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.api_client = api_client or DarwinApiClient()
        self.default_category = default_category
        self._all_assets: List[AssetInfo] = []
        self._visible_assets: List[AssetInfo] = []
        self._current_assets: List[AssetInfo] = []
        self._taxonomy: Dict[str, Dict[str, Set[str]]] = {}
        self._updating_filters: bool = False
        self._drawer_open: bool = False
        self._metrics_request_symbol: Optional[str] = None
        self._current_metrics: Optional[InstitutionalMetrics] = None
        self._metrics_timer = None
        self.debounce_delay: float = debounce_delay

    def compose(self) -> ComposeResult:
        with Container(id="asset-explorer-dialog"):
            yield Static("DARWINEX ASSET EXPLORER [A / F3]", classes="modal-title", id="modal-title")
            with Horizontal(id="filter-bar"):
                yield Select[str](
                    options=[("All Classes", "ALL")],
                    value="ALL",
                    allow_blank=False,
                    id="select-class",
                    prompt="Class",
                )
                yield Select[str](
                    options=[("All Regions", "ALL")],
                    value="ALL",
                    allow_blank=False,
                    disabled=True,
                    id="select-region",
                    prompt="Region",
                )
                yield Select[str](
                    options=[("All Exchanges", "ALL")],
                    value="ALL",
                    allow_blank=False,
                    disabled=True,
                    id="select-exchange",
                    prompt="Exchange",
                )
                yield Input(
                    placeholder="Search ticker or company (e.g. NVDA, ADBE)...",
                    id="asset-search-input",
                )
                yield Button("Reset (F4)", id="btn-reset-filters")
            yield Static("", id="error-banner")
            yield Static("Loading assets...", id="status-bar")
            yield DataTable(id="assets-data-table", cursor_type="row")
            with Container(id="institutional-metrics-drawer"):
                yield Static("", id="metrics-drawer-header")
                yield Static("", id="metrics-drawer-content")
            with Horizontal(classes="modal-footer"):
                yield Static(
                    "[↑/↓] Navigate  |  [I] Metrics  |  [H] Inspect History  |  [F4] Reset Filters  |  [S] Focus Search  |  [ESC] Close",
                    classes="help-hint",
                )
                yield Button("Inspect History", id="btn-inspect-history", variant="primary")
                yield Button("Close", id="btn-close", variant="default")

    async def on_mount(self) -> None:
        """Initialize table columns and load initial asset catalog."""
        table = self.query_one("#assets-data-table", DataTable)
        table.add_columns(
            "Symbol",
            "Description",
            "Class",
            "Region",
            "Exchange",
            "CCY",
            "Min Lot",
            "Max Lot",
            "Bid",
            "Ask",
        )
        await self._load_assets()
        table.focus()

    def _build_taxonomy(self) -> None:
        """Extracts taxonomy mapping {class: {region: set(exchanges)}} from self._all_assets."""
        self._taxonomy = {}
        for asset in self._all_assets:
            c, r, e = parse_category_parts(asset.category, asset.symbol)
            if c == "--":
                continue
            if c not in self._taxonomy:
                self._taxonomy[c] = {}
            if r != "--":
                if r not in self._taxonomy[c]:
                    self._taxonomy[c][r] = set()
                if e != "--":
                    self._taxonomy[c][r].add(e)

    async def _load_assets(self) -> None:
        """Loads assets from API gateway with error resilience and initializes taxonomy."""
        status = self.query_one("#status-bar", Static)
        error_banner = self.query_one("#error-banner", Static)

        status.update("Loading assets...")
        error_banner.remove_class("visible")

        try:
            assets = await self.api_client.get_assets(category="all")
            self._all_assets = assets
            self._build_taxonomy()

            self._updating_filters = True
            try:
                class_select = self.query_one("#select-class", Select)
                region_select = self.query_one("#select-region", Select)
                exchange_select = self.query_one("#select-exchange", Select)

                classes = sorted(self._taxonomy.keys())
                class_options = [("All Classes", "ALL")] + [(c, c) for c in classes]
                class_select.set_options(class_options)
                class_select.value = "ALL"
                class_select.disabled = False

                region_select.set_options([("All Regions", "ALL")])
                region_select.value = "ALL"
                region_select.disabled = True

                exchange_select.set_options([("All Exchanges", "ALL")])
                exchange_select.value = "ALL"
                exchange_select.disabled = True
            finally:
                self._updating_filters = False

            self._apply_filters()

            if len(assets) == 0:
                status.update("No assets found (Gateway may be in mock or offline mode)")

        except Exception as exc:
            self._all_assets = []
            self._visible_assets = []
            self._current_assets = []
            error_banner.update(f"Error loading assets: {exc}")
            error_banner.add_class("visible")
            status.update("Failed to retrieve asset catalog from gateway")

    def _clean_select_val(self, select_id: str) -> str:
        try:
            val = self.query_one(select_id, Select).value
            if val is None or val == Select.BLANK:
                return "ALL"
            return str(val)
        except Exception:
            return "ALL"

    def _apply_filters(self) -> None:
        """Centralized in-memory multi-predicate filtering and status reporting."""
        class_val = self._clean_select_val("#select-class")
        region_val = self._clean_select_val("#select-region")
        exchange_val = self._clean_select_val("#select-exchange")
        raw_search = self.query_one("#asset-search-input", Input).value
        search_term = raw_search.strip().lower()

        filtered: List[AssetInfo] = []
        for asset in self._all_assets:
            c, r, e = parse_category_parts(asset.category, asset.symbol)
            if class_val != "ALL" and c != class_val:
                continue
            if region_val != "ALL" and r != region_val:
                continue
            if exchange_val != "ALL" and e != exchange_val:
                continue
            if search_term:
                sym_lower = (asset.symbol or "").lower()
                desc_lower = (asset.description or "").lower()
                if search_term not in sym_lower and search_term not in desc_lower:
                    continue
            filtered.append(asset)

        self._visible_assets = filtered
        self._current_assets = filtered

        table = self.query_one("#assets-data-table", DataTable)
        table.clear()
        for asset in self._visible_assets:
            c, r, e = parse_category_parts(asset.category, asset.symbol)
            bid_str = f"{asset.bid:.2f}" if asset.bid is not None else "--"
            ask_str = f"{asset.ask:.2f}" if asset.ask is not None else "--"
            table.add_row(
                Text(asset.symbol, style="bold cyan"),
                asset.description,
                c,
                r,
                e,
                asset.currency,
                f"{asset.lot_min:.2f}",
                f"{asset.lot_max:.2f}",
                bid_str,
                ask_str,
                key=asset.symbol,
            )

        status = self.query_one("#status-bar", Static)
        total = len(self._all_assets)
        visible = len(self._visible_assets)

        cat_parts = []
        if class_val != "ALL":
            cat_parts.append(class_val)
        if region_val != "ALL":
            cat_parts.append(region_val)
        if exchange_val != "ALL":
            cat_parts.append(exchange_val)

        filter_desc = []
        if cat_parts:
            filter_desc.append(" > ".join(cat_parts))
        if search_term:
            filter_desc.append(f'"{raw_search.strip()}"')

        if filter_desc:
            match_str = f" matching [{' | '.join(filter_desc)}]"
        else:
            match_str = ""

        if total == 0:
            status.update("No assets found (Gateway may be in mock or offline mode)")
        else:
            status.update(f"Showing {visible} of {total} assets{match_str}")

        if self._drawer_open:
            asset = self._get_selected_asset()
            if asset:
                self._on_symbol_highlighted(asset.symbol, immediate=True)
            else:
                self._metrics_request_symbol = None
                self._current_metrics = None
                self.query_one("#metrics-drawer-header", Static).update("Institutional Metrics")
                self.query_one("#metrics-drawer-content", Static).update("No asset selected")

    @on(Select.Changed, "#select-class")
    def on_class_changed(self, event: Select.Changed) -> None:
        if self._updating_filters:
            return
        class_val = self._clean_select_val("#select-class")
        self._updating_filters = True
        try:
            region_select = self.query_one("#select-region", Select)
            exchange_select = self.query_one("#select-exchange", Select)

            if class_val == "ALL" or class_val not in self._taxonomy:
                region_select.set_options([("All Regions", "ALL")])
                region_select.value = "ALL"
                region_select.disabled = True

                exchange_select.set_options([("All Exchanges", "ALL")])
                exchange_select.value = "ALL"
                exchange_select.disabled = True
            else:
                regions = sorted(self._taxonomy.get(class_val, {}).keys())
                if regions:
                    region_select.set_options([("All Regions", "ALL")] + [(r, r) for r in regions])
                    region_select.value = "ALL"
                    region_select.disabled = False
                else:
                    region_select.set_options([("All Regions", "ALL")])
                    region_select.value = "ALL"
                    region_select.disabled = True

                exchange_select.set_options([("All Exchanges", "ALL")])
                exchange_select.value = "ALL"
                exchange_select.disabled = True
        finally:
            self._updating_filters = False

        self._apply_filters()

    @on(Select.Changed, "#select-region")
    def on_region_changed(self, event: Select.Changed) -> None:
        if self._updating_filters:
            return
        class_val = self._clean_select_val("#select-class")
        region_val = self._clean_select_val("#select-region")
        self._updating_filters = True
        try:
            exchange_select = self.query_one("#select-exchange", Select)

            if region_val == "ALL" or class_val == "ALL" or region_val not in self._taxonomy.get(class_val, {}):
                exchange_select.set_options([("All Exchanges", "ALL")])
                exchange_select.value = "ALL"
                exchange_select.disabled = True
            else:
                exchanges = sorted(self._taxonomy.get(class_val, {}).get(region_val, set()))
                if exchanges:
                    exchange_select.set_options([("All Exchanges", "ALL")] + [(e, e) for e in exchanges])
                    exchange_select.value = "ALL"
                    exchange_select.disabled = False
                else:
                    exchange_select.set_options([("All Exchanges", "ALL")])
                    exchange_select.value = "ALL"
                    exchange_select.disabled = True
        finally:
            self._updating_filters = False

        self._apply_filters()

    @on(Select.Changed, "#select-exchange")
    def on_exchange_changed(self, event: Select.Changed) -> None:
        if self._updating_filters:
            return
        self._apply_filters()

    @on(Input.Changed, "#asset-search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        self._apply_filters()

    @on(Input.Submitted, "#asset-search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        self.query_one("#assets-data-table", DataTable).focus()

    async def action_reset_filters(self) -> None:
        """Resets all filters to defaults, or triggers a catalog reload if catalog is empty."""
        if not self._all_assets:
            await self._load_assets()
            return

        self._updating_filters = True
        try:
            class_select = self.query_one("#select-class", Select)
            region_select = self.query_one("#select-region", Select)
            exchange_select = self.query_one("#select-exchange", Select)
            search_input = self.query_one("#asset-search-input", Input)

            class_select.value = "ALL"

            region_select.set_options([("All Regions", "ALL")])
            region_select.value = "ALL"
            region_select.disabled = True

            exchange_select.set_options([("All Exchanges", "ALL")])
            exchange_select.value = "ALL"
            exchange_select.disabled = True

            search_input.value = ""
        finally:
            self._updating_filters = False

        self._apply_filters()

    @on(Button.Pressed, "#btn-reset-filters")
    async def on_reset_filters_pressed(self) -> None:
        await self.action_reset_filters()

    @on(Button.Pressed, "#btn-close")
    def on_close_pressed(self) -> None:
        self.dismiss(None)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    def action_focus_search(self) -> None:
        self.query_one("#asset-search-input", Input).focus()

    def _get_selected_asset(self) -> Optional[AssetInfo]:
        """Returns the currently highlighted or selected AssetInfo."""
        table = self.query_one("#assets-data-table", DataTable)
        if table.row_count == 0 or not self._visible_assets:
            return None
        try:
            cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
            if cell_key and cell_key.row_key and cell_key.row_key.value:
                sym = str(cell_key.row_key.value)
                for asset in self._visible_assets:
                    if asset.symbol == sym:
                        return asset
                return AssetInfo(symbol=sym)
        except Exception:
            pass
        if 0 <= table.cursor_row < len(self._visible_assets):
            return self._visible_assets[table.cursor_row]
        return self._visible_assets[0]

    def action_inspect_history(self) -> None:
        """Opens HistoricalDataModal for the highlighted asset."""
        asset = self._get_selected_asset()
        if not asset:
            return
        from tui.screens.historical_data_modal import HistoricalDataModal
        self.app.push_screen(
            HistoricalDataModal(
                symbol=asset.symbol,
                digits=asset.digits,
                api_client=self.api_client,
            )
        )

    @on(Button.Pressed, "#btn-inspect-history")
    def on_inspect_history_pressed(self) -> None:
        self.action_inspect_history()

    @on(DataTable.RowSelected, "#assets-data-table")
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_inspect_history()

    def action_toggle_metrics_drawer(self) -> None:
        """Toggles the institutional metrics drawer when table is focused."""
        search_input = self.query_one("#asset-search-input", Input)
        if search_input.has_focus:
            return
        self._toggle_metrics_drawer()

    def _toggle_metrics_drawer(self) -> None:
        """Toggles visibility of the institutional metrics drawer."""
        drawer = self.query_one("#institutional-metrics-drawer")
        self._drawer_open = not self._drawer_open
        if self._drawer_open:
            drawer.add_class("visible")
            asset = self._get_selected_asset()
            if asset:
                self._on_symbol_highlighted(asset.symbol, immediate=True)
        else:
            drawer.remove_class("visible")
            if self._metrics_timer is not None:
                self._metrics_timer.stop()
                self._metrics_timer = None

    def _on_symbol_highlighted(self, symbol: str, immediate: bool = False) -> None:
        """Updates drawer to loading state and schedules a debounced metrics fetch."""
        clean_sym = symbol.strip().upper()
        self._metrics_request_symbol = clean_sym
        self._update_drawer_loading(clean_sym)

        if self._metrics_timer is not None:
            self._metrics_timer.stop()
            self._metrics_timer = None

        if immediate or self.debounce_delay <= 0:
            self.run_worker(self._fetch_metrics(clean_sym))
        else:
            self._metrics_timer = self.set_timer(
                self.debounce_delay,
                lambda sym=clean_sym: self.run_worker(self._fetch_metrics(sym)),
            )

    def _update_drawer_loading(self, symbol: str) -> None:
        """Sets the drawer to the initial loading state."""
        header = self.query_one("#metrics-drawer-header", Static)
        content = self.query_one("#metrics-drawer-content", Static)
        header.update(f"Institutional Metrics: {symbol}")
        content.update(f"Loading institutional metrics for {symbol}...")

    async def _fetch_metrics(self, request_symbol: str) -> None:
        """Asynchronously queries metrics and discards out-of-order responses."""
        try:
            metrics = await self.api_client.get_asset_metrics(request_symbol)
        except Exception:
            metrics = None

        # Guard: safely discard out-of-order responses during fast navigation
        if self._metrics_request_symbol != request_symbol:
            return

        if not self._drawer_open:
            return

        self._render_metrics(request_symbol, metrics)

    def _render_metrics(self, symbol: str, metrics: Optional[InstitutionalMetrics]) -> None:
        """Renders verified metrics, unsynced (404), or insufficient data states."""
        header = self.query_one("#metrics-drawer-header", Static)
        content = self.query_one("#metrics-drawer-content", Static)
        header.update(f"Institutional Metrics: {symbol}")

        if metrics is None:
            # Unsynced / 404 state (Scenario 11)
            self._current_metrics = None
            content.update(f"No local rates synced for {symbol}. Press [H] to view/sync history.")
            return

        self._current_metrics = metrics

        if metrics.insufficient_data:
            # Insufficient data state (Scenario 9)
            content.update(
                f"Insufficient historical data for {symbol} ({metrics.bars_found}/{metrics.bars_required} bars found). Press [H] to sync."
            )
            return

        # Verified metrics state (Scenario 10)
        yz_str = f"{metrics.yang_zhang_vol_annualized * 100:.1f}%" if metrics.yang_zhang_vol_annualized is not None else "--"
        amihud_str = f"{metrics.amihud_sensitivity:.2e}" if metrics.amihud_sensitivity is not None else "--"
        vwap_str = f"{metrics.vwap:.2f}" if metrics.vwap is not None else "--"
        dev_str = f"{metrics.vwap_deviation_sigmas:+.2f}σ" if metrics.vwap_deviation_sigmas is not None else "--"
        roll_str = f"{metrics.roll_spread_pct * 100:.2f}%" if metrics.roll_spread_pct is not None else "--"

        content.update(
            Text.from_markup(
                f"YZ Vol: [bold]{yz_str}[/]  |  "
                f"Amihud: [bold]{amihud_str}[/]  |  "
                f"VWAP: [bold]{vwap_str}[/] ({dev_str})  |  "
                f"Roll Spread: [bold]{roll_str}[/]"
            )
        )

    @on(DataTable.RowHighlighted, "#assets-data-table")
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if not self._drawer_open:
            return
        symbol = None
        if event.row_key and event.row_key.value:
            symbol = str(event.row_key.value)
        if not symbol:
            asset = self._get_selected_asset()
            symbol = asset.symbol if asset else None
        if not symbol:
            return
        self._on_symbol_highlighted(symbol, immediate=False)
