"""
StrategyPanel widget for Darwin Trader TUI.
Displays strategy status, algorithm name, target symbol, daily drawdown, and total exposure.
"""
from typing import Any, Dict, List, Optional
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Static

from strategy_engine.models import Position


class StrategyPanel(Container):
    """
    Control and telemetry panel for the running algorithmic strategy.
    Displays:
      - Running state badge (e.g., RUNNING, PAUSED, IDLE, STOPPED)
      - Strategy name and symbol
      - Daily drawdown percentage with threshold warning
      - Total open exposure (lots)
    """

    DEFAULT_CSS = """
    StrategyPanel {
        height: auto;
        min-height: 5;
        border: solid $primary;
        background: $surface;
        padding: 0 1;
        margin-top: 1;
    }

    .panel-title {
        text-style: bold;
        color: $accent;
    }

    .strategy-grid {
        height: auto;
        layout: horizontal;
        align-vertical: middle;
        padding-top: 1;
    }

    .strategy-item {
        width: 1fr;
        padding: 0 1;
        border-right: solid $primary-darken-2;
    }

    .strategy-item:last-of-type {
        border-right: none;
    }

    .item-label {
        color: $text-muted;
        text-style: bold;
    }

    .item-value {
        text-style: bold;
    }

    .state-running {
        color: $success;
    }

    .state-paused {
        color: $warning;
    }

    .state-idle {
        color: $primary;
    }

    .state-stopped, .state-error {
        color: $error;
    }

    .drawdown-normal {
        color: $success;
    }

    .drawdown-warning {
        color: $error;
        text-style: bold;
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
        self._strategy_status: str = "IDLE"
        self._strategy_name: str = "Darwin_Trend_ATR_V1"
        self._symbol: str = "EURUSD"
        self._drawdown_pct: float = 0.0
        self._total_exposure_lots: float = 0.0

    def compose(self) -> ComposeResult:
        yield Static("STRATEGY CONTROL & TELEMETRY", classes="panel-title", id="strategy-panel-title")
        with Horizontal(classes="strategy-grid"):
            with Container(classes="strategy-item"):
                yield Static("STATE", classes="item-label")
                yield Static("[● IDLE]", id="strategy-state-value", classes="item-value state-idle")
            with Container(classes="strategy-item"):
                yield Static("STRATEGY / SYMBOL", classes="item-label")
                yield Static("Darwin_Trend_ATR_V1 (EURUSD)", id="strategy-name-value", classes="item-value")
            with Container(classes="strategy-item"):
                yield Static("DAILY DRAWDOWN", classes="item-label")
                yield Static("0.00%", id="strategy-drawdown-value", classes="item-value drawdown-normal")
            with Container(classes="strategy-item"):
                yield Static("TOTAL EXPOSURE", classes="item-label")
                yield Static("0.00 lots", id="strategy-exposure-value", classes="item-value")

    def update_telemetry(
        self,
        strategy_data: Optional[Dict[str, Any]] = None,
        positions: Optional[List[Position]] = None,
        is_offline: bool = False,
    ) -> None:
        """
        Updates strategy telemetry and drawdown / exposure values.
        """
        state_widget = self.query_one("#strategy-state-value", Static)
        name_widget = self.query_one("#strategy-name-value", Static)
        drawdown_widget = self.query_one("#strategy-drawdown-value", Static)
        exposure_widget = self.query_one("#strategy-exposure-value", Static)
        title_widget = self.query_one("#strategy-panel-title", Static)

        if is_offline:
            title_widget.update("STRATEGY CONTROL & TELEMETRY [OFFLINE]")
            state_widget.update("[○ UNKNOWN]")
            state_widget.remove_class("state-running", "state-paused", "state-idle", "state-stopped", "state-error")
            state_widget.add_class("state-error")
            return

        title_widget.update("STRATEGY CONTROL & TELEMETRY")
        if strategy_data:
            self._strategy_status = str(strategy_data.get("status", "IDLE")).upper()
            self._strategy_name = str(strategy_data.get("strategy_name", "Darwin_Trend_ATR_V1"))
            self._symbol = str(strategy_data.get("symbol", "EURUSD"))

            # Calculate daily drawdown if balance/equity provided
            balance = float(strategy_data.get("account_balance", 0.0) or 0.0)
            equity = float(strategy_data.get("account_equity", 0.0) or 0.0)
            if balance > 0:
                self._drawdown_pct = max(0.0, (balance - equity) / balance * 100.0)
            else:
                self._drawdown_pct = float(strategy_data.get("daily_drawdown_pct", 0.0) or 0.0)

        # Update state badge
        state_widget.remove_class("state-running", "state-paused", "state-idle", "state-stopped", "state-error")
        if self._strategy_status == "RUNNING":
            state_widget.update("[● RUNNING]")
            state_widget.add_class("state-running")
        elif self._strategy_status == "PAUSED":
            state_widget.update("[⏸ PAUSED]")
            state_widget.add_class("state-paused")
        elif self._strategy_status == "STOPPED":
            state_widget.update("[■ STOPPED]")
            state_widget.add_class("state-stopped")
        else:
            state_widget.update(f"[● {self._strategy_status}]")
            state_widget.add_class("state-idle")

        name_widget.update(f"{self._strategy_name} ({self._symbol})")

        # Update drawdown
        drawdown_widget.remove_class("drawdown-normal", "drawdown-warning")
        drawdown_widget.update(f"{self._drawdown_pct:.2f}%")
        if self._drawdown_pct >= 3.0:
            drawdown_widget.add_class("drawdown-warning")
        else:
            drawdown_widget.add_class("drawdown-normal")

        # Update exposure
        if positions is not None:
            self._total_exposure_lots = sum(p.volume for p in positions)
        exposure_widget.update(f"{self._total_exposure_lots:.2f} lots")
