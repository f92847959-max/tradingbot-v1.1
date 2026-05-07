"""Rich terminal dashboard for the continuous training loop."""

from __future__ import annotations

import math
import time
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import ASSETS
from .history import latest_for_asset
from .metrics import dig
from .models import CycleResult


class Dashboard:
    def __init__(self, console: Console, total_cycles: int | None, assets: list[str]) -> None:
        self.console = console
        self.total_cycles = total_cycles
        self.assets = assets
        self.cycle = 0
        self.run_completed = 0
        self.current_asset = ""
        self.step = "Initialisierung"
        self.cycle_started: float | None = None
        self.history: list[CycleResult] = []

    def update(
        self,
        cycle: int,
        asset: str,
        step: str,
        history: list[CycleResult],
        run_completed: int = 0,
    ) -> None:
        self.cycle = cycle
        self.current_asset = asset
        self.step = step
        self.history = history
        self.run_completed = run_completed
        if step == "Core-AI Training" or self.cycle_started is None:
            self.cycle_started = time.time()

    def render(self) -> Panel:
        return Panel(
            Group(
                self._header(),
                *(self._asset_panel(asset) for asset in self.assets),
                self._exit_ai_panel(),
                self._trend(),
            ),
            title="[bold cyan]Trading-Bot Training-Loop - Gold & Silber[/]",
            border_style="cyan",
        )

    def _header(self) -> Panel:
        elapsed = "0s" if self.cycle_started is None else format_duration(
            time.time() - self.cycle_started
        )
        if self.total_cycles:
            cycle_info = f"Zyklus #{self.cycle} (Sitzung {self.run_completed}/{self.total_cycles})"
        else:
            cycle_info = f"Zyklus #{self.cycle} (endlos)"
        text = Text.assemble(
            (cycle_info, "bold yellow"),
            "  -  ",
            ("Asset: ", "dim"),
            (self.current_asset.upper() or "--", "bold magenta"),
            "  -  ",
            ("Schritt: ", "dim"),
            (self.step, "bold green"),
            "  -  ",
            ("Laufzeit: ", "dim"),
            (elapsed, "white"),
        )
        return Panel(text, border_style="dim")

    def _asset_panel(self, asset: str) -> Panel:
        history_for_asset = [h for h in self.history if h.asset == asset]
        prev = history_for_asset[-2] if len(history_for_asset) >= 2 else None
        cur = history_for_asset[-1] if history_for_asset else None
        label = ASSETS[asset]["label"].upper()
        color = "green" if asset == "gold" else "blue"
        return Panel(
            self._asset_table(prev, cur),
            title=f"[bold {color}]{label}[/]",
            border_style=color,
        )

    def _asset_table(self, prev: CycleResult | None, cur: CycleResult | None) -> Table:
        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column("Teil", style="cyan", no_wrap=True, width=8)
        table.add_column("Metrik", no_wrap=True, min_width=12)
        table.add_column("Vorher", justify="right")
        table.add_column("Aktuell", justify="right")
        table.add_column("Diff %", justify="right")

        for model, prefix in (("xgboost", "XGB"), ("lightgbm", "LGB")):
            for metric, mlabel, fmt in [
                ("profit_factor", f"{prefix} PF", "{:.2f}"),
                ("win_rate", f"{prefix} WR", "{:.1%}"),
                ("n_trades", f"{prefix} Trades", "{:.0f}"),
            ]:
                self._add_metric_row(
                    table,
                    "Core",
                    mlabel,
                    prev,
                    cur,
                    ["core_ai", model, metric],
                    fmt,
                )

        for metric, mlabel, fmt in [
            ("profit_factor", "BT PF", "{:.2f}"),
            ("win_rate", "BT WR", "{:.1%}"),
            ("total_pips", "BT Pips", "{:+.1f}"),
            ("max_drawdown_pct", "BT DD", "{:.1f}%"),
            ("n_trades", "BT Trades", "{:.0f}"),
        ]:
            self._add_metric_row(
                table,
                "Backtest",
                mlabel,
                prev,
                cur,
                ["backtest", metric],
                fmt,
            )
        return table

    def _add_metric_row(
        self,
        table: Table,
        section: str,
        label: str,
        prev: CycleResult | None,
        cur: CycleResult | None,
        keys: list[str],
        fmt: str,
    ) -> None:
        metric_key = ".".join(keys)
        p_val = dig(prev, keys) if prev else None
        c_val = dig(cur, keys) if cur else None
        delta = dig(cur, ["improvements_pct", metric_key]) if cur else None
        table.add_row(
            section,
            label,
            fmt_value(p_val, fmt),
            fmt_value(c_val, fmt),
            fmt_delta(delta),
        )

    def _exit_ai_panel(self) -> Panel:
        cur = self.history[-1] if self.history else None
        prev = self.history[-2] if len(self.history) >= 2 else None
        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column("Exit AI (gemeinsam)", style="cyan", no_wrap=True)
        table.add_column("Vorher", justify="right")
        table.add_column("Aktuell", justify="right")
        table.add_column("Diff %", justify="right")
        for metric, label, fmt in [
            ("accuracy", "Accuracy", "{:.1%}"),
            ("calibration_score", "Calibration Score", "{:.3f}"),
            ("profit_factor_proxy", "Profit-Factor (Proxy)", "{:.2f}"),
            ("trade_retention", "Trade Retention", "{:.1%}"),
        ]:
            p_val = dig(prev, ["exit_ai", metric]) if prev else None
            c_val = dig(cur, ["exit_ai", metric]) if cur else None
            delta = dig(cur, ["improvements_pct", f"exit_ai.{metric}"]) if cur else None
            table.add_row(label, fmt_value(p_val, fmt), fmt_value(c_val, fmt), fmt_delta(delta))
        promo_cur = dig(cur, ["exit_ai", "promotion_status"]) or "--"
        table.add_row("Promotion-Status", "", str(promo_cur).upper(), "")
        return Panel(table, title="[bold magenta]Exit AI[/]", border_style="magenta")

    def _trend(self) -> Panel:
        if not self.history:
            return Panel(Text("Noch keine Zyklen abgeschlossen", style="dim"), border_style="dim")

        lines = []
        for asset in self.assets:
            hs = [h for h in self.history if h.asset == asset][-5:]
            if not hs:
                continue
            pf_values = [
                float(v) if isinstance(v, (int, float)) and math.isfinite(float(v)) else 0.0
                for v in (h.backtest.get("profit_factor", 0.0) for h in hs)
            ]
            arrow = (
                "up"
                if len(pf_values) >= 2 and pf_values[-1] > pf_values[0]
                else "down"
                if len(pf_values) >= 2 and pf_values[-1] < pf_values[0]
                else "flat"
            )
            trend = " > ".join(f"{v:.2f}" for v in pf_values)
            lines.append(f"{ASSETS[asset]['label']:7s}: {trend}  {arrow}")
        return Panel(
            Text("Trend Profit-Factor letzte 5 Zyklen:\n" + "\n".join(lines), style="white"),
            border_style="dim",
        )


def fmt_value(value: Any, fmt: str) -> str:
    if not isinstance(value, (int, float)):
        return "--"
    value_f = float(value)
    if not math.isfinite(value_f):
        return "--"
    return fmt.format(value_f)


def fmt_delta(delta: float | None) -> str:
    if delta is None or not isinstance(delta, (int, float)) or not math.isfinite(float(delta)):
        return "--"
    if abs(delta) < 0.01:
        return "[dim]0.0%[/]"
    color = "bold green" if delta > 0 else "bold red"
    return f"[{color}]{delta:+.1f}%[/]"


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def cycle_summary_panel(result: CycleResult) -> Panel:
    label = ASSETS[result.asset]["label"]
    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("Bereich", style="cyan", no_wrap=True)
    table.add_column("Metrik", no_wrap=True)
    table.add_column("Wert", justify="right")

    for model, model_label in (("xgboost", "XGBoost"), ("lightgbm", "LightGBM")):
        metrics = result.core_ai.get(model, {})
        table.add_row("Core", f"{model_label} PF", fmt_value(metrics.get("profit_factor"), "{:.2f}"))
        table.add_row("Core", f"{model_label} WR", fmt_value(metrics.get("win_rate"), "{:.1%}"))
        table.add_row("Core", f"{model_label} Trades", fmt_value(metrics.get("n_trades"), "{:.0f}"))

    table.add_row("Core", "Bestes Modell", str(result.core_ai.get("best_model", "--")).upper())
    table.add_row("Backtest", "PF", fmt_value(result.backtest.get("profit_factor"), "{:.2f}"))
    table.add_row("Backtest", "WR", fmt_value(result.backtest.get("win_rate"), "{:.1%}"))
    table.add_row("Backtest", "Pips", fmt_value(result.backtest.get("total_pips"), "{:+.1f}"))
    table.add_row("Backtest", "Trades", fmt_value(result.backtest.get("n_trades"), "{:.0f}"))
    table.add_row("Backtest", "Max DD", fmt_value(result.backtest.get("max_drawdown_pct"), "{:.1f}%"))
    table.add_row("Exit AI", "Status", str(result.exit_ai.get("promotion_status", "--")).upper())

    return Panel(
        table,
        title=f"[bold green]{label} Ergebnis - Zyklus {result.cycle} - {format_duration(result.duration_sec)}[/]",
        border_style="green",
    )


def session_summary_panel(history: list[CycleResult], assets: list[str]) -> Panel:
    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("Asset", style="cyan", no_wrap=True)
    table.add_column("Zyklus", justify="right")
    table.add_column("Best", justify="right")
    table.add_column("Core PF", justify="right")
    table.add_column("BT PF", justify="right")
    table.add_column("BT Pips", justify="right")
    table.add_column("BT Trades", justify="right")

    for asset in assets:
        result = latest_for_asset(history, asset)
        if result is None:
            table.add_row(ASSETS[asset]["label"], "--", "--", "--", "--", "--", "--")
            continue
        best = str(result.core_ai.get("best_model", "xgboost"))
        core_pf = result.core_ai.get(best, {}).get("profit_factor")
        table.add_row(
            ASSETS[asset]["label"],
            str(result.cycle),
            best.upper(),
            fmt_value(core_pf, "{:.2f}"),
            fmt_value(result.backtest.get("profit_factor"), "{:.2f}"),
            fmt_value(result.backtest.get("total_pips"), "{:+.1f}"),
            fmt_value(result.backtest.get("n_trades"), "{:.0f}"),
        )

    return Panel(table, title="[bold cyan]Letzte Training-Ergebnisse[/]", border_style="cyan")
