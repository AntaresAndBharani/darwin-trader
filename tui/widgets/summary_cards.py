"""
SummaryCards widget for Darwin Trader TUI.
Displays financial metrics overview: Balance, Equity, Margin, and Floating P&L.
Uses dual-glyph styling: green '▲' for positive P&L and red '▼' for negative P&L.
Supports responsive collapsing from horizontal row into 2x2 grid layout below 80 columns.
"""
from typing import Optional
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

from strategy_engine.models import AccountInfo


class MetricCard(Static):
    """A single financial metric card with title, formatted value, and dual-glyph."""

    DEFAULT_CSS = """
    MetricCard {
        background: $surface;
        border: solid $primary;
        padding: 0 1;
        height: auto;
        min-height: 3;
        min-width: 16;
        content-align: center middle;
    }

    MetricCard .metric-title {
        color: $text-muted;
        text-style: bold;
        text-align: center;
    }

    MetricCard .metric-value {
        text-align: center;
        text-style: bold;
    }

    MetricCard.profit-positive .metric-value {
        color: $success;
    }

    MetricCard.profit-negative .metric-value {
        color: $error;
    }

    MetricCard.profit-neutral .metric-value {
        color: $text;
    }
    """

    def __init__(
        self,
        title: str,
        value_text: str = "$0.00",
        card_id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        super().__init__(id=card_id, classes=classes)
        self.title_str = title
        self.value_str = value_text

    def compose(self) -> ComposeResult:
        yield Static(self.title_str, classes="metric-title", id=f"{self.id}-title")
        yield Static(self.value_str, classes="metric-value", id=f"{self.id}-value")

    def update_value(self, formatted_text: str | Text, status_class: Optional[str] = None) -> None:
        """Updates the metric value display and optionally toggles styling classes."""
        val_widget = self.query_one(f"#{self.id}-value", Static)
        val_widget.update(formatted_text)
        if status_class:
            self.remove_class("profit-positive", "profit-negative", "profit-neutral")
            self.add_class(status_class)


class SummaryCards(Container):
    """
    Overview widget displaying 4 summary cards:
    - Balance
    - Equity
    - Margin (or Margin Level)
    - Floating P&L (with dual glyph ▲ / ▼)
    """

    DEFAULT_CSS = """
    SummaryCards {
        layout: horizontal;
        height: auto;
        margin: 0 0 1 0;
    }

    SummaryCards > MetricCard {
        width: 1fr;
        margin-right: 1;
    }

    SummaryCards > MetricCard:last-of-type {
        margin-right: 0;
    }

    /* Responsive styling for narrow viewports */
    SummaryCards.compact-grid {
        layout: grid;
        grid-size: 2 2;
        grid-gutter: 1 1;
    }

    SummaryCards.compact-grid > MetricCard {
        width: 1fr;
        margin-right: 0;
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
        self._balance: float = 0.0
        self._equity: float = 0.0
        self._margin: float = 0.0
        self._profit: float = 0.0

    def compose(self) -> ComposeResult:
        yield MetricCard("BALANCE", "$0.00", card_id="card-balance")
        yield MetricCard("EQUITY", "$0.00", card_id="card-equity")
        yield MetricCard("MARGIN", "$0.00", card_id="card-margin")
        yield MetricCard("FLOATING P&L", "0.00", card_id="card-pnl", classes="profit-neutral")

    def update_metrics(
        self,
        account_info: Optional[AccountInfo] = None,
        balance: Optional[float] = None,
        equity: Optional[float] = None,
        margin: Optional[float] = None,
        floating_pnl: Optional[float] = None,
    ) -> None:
        """
        Updates cards with latest account metrics.
        Accepts either an AccountInfo object or individual numeric values.
        """
        if account_info is not None:
            self._balance = account_info.balance
            self._equity = account_info.equity
            self._margin = account_info.margin
            self._profit = account_info.profit
        else:
            if balance is not None:
                self._balance = balance
            if equity is not None:
                self._equity = equity
            if margin is not None:
                self._margin = margin
            if floating_pnl is not None:
                self._profit = floating_pnl

        # Update Balance
        card_bal = self.query_one("#card-balance", MetricCard)
        card_bal.update_value(f"${self._balance:,.2f}")

        # Update Equity
        card_eq = self.query_one("#card-equity", MetricCard)
        card_eq.update_value(f"${self._equity:,.2f}")

        # Update Margin
        card_mar = self.query_one("#card-margin", MetricCard)
        card_mar.update_value(f"${self._margin:,.2f}")

        # Update Floating P&L with dual glyphs
        card_pnl = self.query_one("#card-pnl", MetricCard)
        if self._profit > 0:
            card_pnl.update_value(f"▲ +${self._profit:,.2f}", status_class="profit-positive")
        elif self._profit < 0:
            card_pnl.update_value(f"▼ -${abs(self._profit):,.2f}", status_class="profit-negative")
        else:
            card_pnl.update_value("$0.00", status_class="profit-neutral")

    def set_compact_layout(self, compact: bool) -> None:
        """Toggles compact 2x2 grid styling for responsive viewports."""
        if compact:
            self.add_class("compact-grid")
        else:
            self.remove_class("compact-grid")
