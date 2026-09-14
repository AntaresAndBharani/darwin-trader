"""
PositionsTable widget for Darwin Trader TUI.
Displays active open positions in an interactive DataTable.
Columns: Ticket, Symbol, Type, Lots, Open Price, Current Price, S/L, T/P, PnL, Swap.
Uses DataTable.update_cell for in-place updates to avoid remounting rows and preserve selection identity.
"""
from typing import Dict, List, Optional
from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import DataTable, Static
from textual.containers import Container

from strategy_engine.models import OrderType, Position


class PositionsTable(Container):
    """
    Positions Table container wrapping a DataTable widget.
    Implements keyed row differential reconciliation and in-place cell updates.
    """

    DEFAULT_CSS = """
    PositionsTable {
        height: 1fr;
        min-height: 8;
        border: solid $primary;
        background: $surface;
        padding: 0 1;
    }

    .table-title {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }

    DataTable {
        height: 1fr;
    }
    """

    COLUMNS = [
        ("ticket", "Ticket"),
        ("symbol", "Symbol"),
        ("type", "Type"),
        ("lots", "Lots"),
        ("open_price", "Open Price"),
        ("current_price", "Current Price"),
        ("sl", "S/L"),
        ("tp", "T/P"),
        ("pnl", "PnL"),
        ("swap", "Swap"),
    ]

    def __init__(
        self,
        *children,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
        disabled: bool = False,
    ) -> None:
        super().__init__(*children, name=name, id=id, classes=classes, disabled=disabled)
        self._row_keys: Dict[int, str] = {}  # ticket -> row_key
        self._positions_cache: Dict[int, Position] = {}
        self._stale_cache: bool = False

    def compose(self) -> ComposeResult:
        yield Static("ACTIVE POSITIONS", classes="table-title", id="positions-table-title")
        yield DataTable(id="positions-data-table", cursor_type="row")

    def on_mount(self) -> None:
        """Initialize columns on the DataTable."""
        table = self.query_one("#positions-data-table", DataTable)
        for col_id, col_label in self.COLUMNS:
            table.add_column(col_label, key=col_id)

    def _format_type(self, order_type: OrderType | str) -> Text:
        val = order_type.value if isinstance(order_type, OrderType) else str(order_type)
        if val.upper() == "BUY":
            return Text("BUY", style="bold green")
        return Text("SELL", style="bold red")

    def _format_pnl(self, pnl: float) -> Text:
        if pnl > 0:
            return Text(f"▲ +${pnl:,.2f}", style="bold green")
        elif pnl < 0:
            return Text(f"▼ -${abs(pnl):,.2f}", style="bold red")
        return Text(f"${pnl:,.2f}", style="bold white")

    def _format_swap(self, swap: float) -> Text:
        if swap > 0:
            return Text(f"+${swap:,.2f}", style="green")
        elif swap < 0:
            return Text(f"-${abs(swap):,.2f}", style="red")
        return Text(f"${swap:,.2f}", style="text-muted")

    def _build_row_cells(self, pos: Position) -> list:
        """Builds formatted cell values for a position row."""
        return [
            str(pos.ticket),
            pos.symbol,
            self._format_type(pos.order_type),
            f"{pos.volume:.2f}",
            f"{pos.open_price:.5f}",
            f"{pos.current_price:.5f}",
            f"{pos.sl:.5f}" if pos.sl > 0 else "--",
            f"{pos.tp:.5f}" if pos.tp > 0 else "--",
            self._format_pnl(pos.pnl),
            self._format_swap(pos.swap),
        ]

    def update_positions(self, positions: List[Position], is_offline: bool = False) -> None:
        """
        Reconciles incoming open positions against existing table rows.
        - Adds newly opened tickets
        - Removes closed tickets
        - Updates changed cells (current_price, sl, tp, pnl, swap) in-place without remounting
        - Retains cached rows if is_offline is True, marking title as STALE
        """
        title_widget = self.query_one("#positions-table-title", Static)
        table = self.query_one("#positions-data-table", DataTable)

        if is_offline:
            self._stale_cache = True
            title_widget.update("ACTIVE POSITIONS [STALE / OFFLINE CACHE]")
            return

        self._stale_cache = False
        title_widget.update(f"ACTIVE POSITIONS ({len(positions)})")

        current_tickets = {p.ticket for p in positions}
        cached_tickets = set(self._row_keys.keys())

        # 1. Remove closed tickets
        for ticket in cached_tickets - current_tickets:
            row_key = self._row_keys.pop(ticket)
            self._positions_cache.pop(ticket, None)
            try:
                table.remove_row(row_key)
            except Exception:
                pass

        # 2. Add or update active positions
        for pos in positions:
            if pos.ticket not in self._row_keys:
                row_key = str(pos.ticket)
                self._row_keys[pos.ticket] = row_key
                self._positions_cache[pos.ticket] = pos
                table.add_row(*self._build_row_cells(pos), key=row_key)
            else:
                row_key = self._row_keys[pos.ticket]
                old_pos = self._positions_cache.get(pos.ticket)

                # In-place updates for dynamic cells
                if old_pos is None or old_pos.current_price != pos.current_price:
                    table.update_cell(row_key, "current_price", f"{pos.current_price:.5f}")
                if old_pos is None or old_pos.pnl != pos.pnl:
                    table.update_cell(row_key, "pnl", self._format_pnl(pos.pnl))
                if old_pos is None or old_pos.sl != pos.sl:
                    table.update_cell(row_key, "sl", f"{pos.sl:.5f}" if pos.sl > 0 else "--")
                if old_pos is None or old_pos.tp != pos.tp:
                    table.update_cell(row_key, "tp", f"{pos.tp:.5f}" if pos.tp > 0 else "--")
                if old_pos is None or old_pos.swap != pos.swap:
                    table.update_cell(row_key, "swap", self._format_swap(pos.swap))
                if old_pos is None or old_pos.volume != pos.volume:
                    table.update_cell(row_key, "lots", f"{pos.volume:.2f}")

                self._positions_cache[pos.ticket] = pos

    def clear_positions(self) -> None:
        """Clears all positions from table and resets internal key maps."""
        table = self.query_one("#positions-data-table", DataTable)
        table.clear()
        self._row_keys.clear()
        self._positions_cache.clear()
        title_widget = self.query_one("#positions-table-title", Static)
        title_widget.update("ACTIVE POSITIONS (0)")
