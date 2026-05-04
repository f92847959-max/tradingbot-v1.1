"""Continuous training loop: Core-AI + Exit-AI + Backtest for Gold and Silver.

Daten kommen aus yfinance (kostenlos, kein Broker). Pro Zyklus wird Gold und/oder
Silber trainiert, dann ein Backtest gemacht, dann mit dem letzten Zyklus desselben
Assets verglichen. Live-Dashboard im Terminal zeigt die Verbesserung in %.

Usage:
    python scripts/train_loop.py                          # beide Assets, endlos
    python scripts/train_loop.py --asset gold --cycles 5  # nur Gold, 5 Zyklen
    python scripts/train_loop.py --refresh-data           # frische Daten ziehen
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAVED_MODELS_DIR = PROJECT_ROOT / "ai_engine" / "saved_models"
HISTORY_FILE = PROJECT_ROOT / "logs" / "training_loop_history.json"

ASSETS: dict[str, dict[str, Any]] = {
    "gold":   {"csv": "data/gold_1h.csv",   "pip_size": 0.01,  "label": "Gold",
               "tp_pips": 1500.0, "sl_pips": 800.0},
    "silver": {"csv": "data/silver_1h.csv", "pip_size": 0.001, "label": "Silber",
               "tp_pips": 200.0,  "sl_pips": 100.0},
}


def _resolve_python() -> str:
    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    venv_python_unix = PROJECT_ROOT / ".venv" / "bin" / "python"
    if venv_python_unix.exists():
        return str(venv_python_unix)
    return sys.executable


PYTHON = _resolve_python()


# ---------- Data containers ----------

@dataclass
class CycleResult:
    cycle: int
    asset: str
    started_at: str
    duration_sec: float
    version_dir: str
    core_ai: dict[str, Any] = field(default_factory=dict)
    exit_ai: dict[str, Any] = field(default_factory=dict)
    backtest: dict[str, Any] = field(default_factory=dict)
    improvements_pct: dict[str, float] = field(default_factory=dict)


# ---------- History I/O ----------

def load_history() -> list[CycleResult]:
    if not HISTORY_FILE.exists():
        return []
    try:
        with HISTORY_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
        return [CycleResult(**entry) for entry in data]
    except (json.JSONDecodeError, TypeError):
        return []


def save_history(history: list[CycleResult]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("w", encoding="utf-8") as f:
        json.dump([h.__dict__ for h in history], f, indent=2)


def latest_for_asset(history: list[CycleResult], asset: str) -> CycleResult | None:
    for entry in reversed(history):
        if entry.asset == asset:
            return entry
    return None


# ---------- Subprocess runners ----------

def _run_subprocess(cmd: list[str], step_name: str) -> tuple[int, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        return proc.returncode, proc.stdout + proc.stderr
    except FileNotFoundError as exc:
        return 1, f"{step_name} failed to start: {exc}"


def find_version_dir_after(timestamp: float) -> Path | None:
    """Return the version_dir created after the given timestamp."""
    if not SAVED_MODELS_DIR.exists():
        return None
    candidates = [
        p for p in SAVED_MODELS_DIR.iterdir()
        if p.is_dir() and p.name.startswith("v") and "_" in p.name
        and p.stat().st_mtime >= timestamp
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def ensure_data(force: bool, console: Console) -> None:
    """Run fetch_market_data.py (force=True triggers refresh)."""
    cmd = [PYTHON, "scripts/fetch_market_data.py"]
    if force:
        cmd.append("--force")
    console.print(f"[dim]Lade Marktdaten: {' '.join(cmd[1:])}[/]")
    rc, out = _run_subprocess(cmd, "fetch_market_data")
    if rc != 0:
        console.print(f"[red]Daten-Fetch fehlgeschlagen:[/]\n{out[-500:]}")


# ---------- Metric extraction ----------

def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def extract_metrics(version_dir: Path) -> dict[str, dict[str, Any]]:
    train_report = _read_json(version_dir / "training_report.json")
    backtest_report = _read_json(version_dir / "backtest_report.json")

    exit_promotion: dict[str, Any] = {}
    specialist_root = SAVED_MODELS_DIR / "specialists" / "exit_ai"
    if specialist_root.exists():
        exit_versions = [p for p in specialist_root.iterdir() if p.is_dir() and p.name.startswith("v")]
        if exit_versions:
            latest_exit = max(exit_versions, key=lambda p: p.stat().st_mtime)
            exit_promotion = _read_json(latest_exit / "exit_ai_promotion_artifact.json")

    aggregate = train_report.get("aggregate", {})
    bt_aggregate = backtest_report.get("aggregate", {})
    eval_cand = exit_promotion.get("evaluation", {}).get("candidate_metrics", {})

    return {
        "core_ai": {
            "xgboost": _flatten_core(aggregate.get("xgboost", {})),
            "lightgbm": _flatten_core(aggregate.get("lightgbm", {})),
            "best_model": aggregate.get("best_model", ""),
        },
        "exit_ai": {
            "promotion_status": exit_promotion.get("promotion_status", "N/A"),
            "accuracy": _as_float(eval_cand.get("accuracy")),
            "calibration_score": _as_float(eval_cand.get("calibration_score")),
            "profit_factor_proxy": _as_float(eval_cand.get("profit_factor_proxy")),
            "trade_retention": _as_float(eval_cand.get("trade_retention")),
        },
        "backtest": {
            "profit_factor": _as_float(bt_aggregate.get("profit_factor")),
            "sharpe_ratio": _as_float(bt_aggregate.get("sharpe_ratio")),
            "win_rate": _as_float(bt_aggregate.get("win_rate")),
            "total_pips": _as_float(bt_aggregate.get("total_pips")),
            "max_drawdown_pct": _as_float(bt_aggregate.get("max_drawdown_pct")),
            "n_trades": int(bt_aggregate.get("n_trades", 0)),
        },
    }


def _as_float(v: Any, default: float = 0.0) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    return default


def _flatten_core(model_metrics: dict[str, Any]) -> dict[str, float]:
    return {
        "win_rate": model_metrics.get("win_rate", 0.0),
        "profit_factor": model_metrics.get("profit_factor", 0.0),
        "sharpe": model_metrics.get("sharpe", 0.0),
        "expectancy": model_metrics.get("expectancy", 0.0),
        "n_trades": model_metrics.get("n_trades", 0),
    }


def _safe_get(d: dict, keys: list[str], default: float = 0.0) -> float:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return float(cur) if isinstance(cur, (int, float)) else default


# ---------- Improvement comparison ----------

def compute_improvements(current: dict, previous: dict) -> dict[str, float]:
    if not previous:
        return {}
    deltas: dict[str, float] = {}

    def walk(prefix: str, cur: Any, prev: Any) -> None:
        if isinstance(cur, dict) and isinstance(prev, dict):
            for k in cur:
                if k in prev:
                    walk(f"{prefix}.{k}" if prefix else k, cur[k], prev[k])
        elif isinstance(cur, (int, float)) and isinstance(prev, (int, float)):
            if prev == 0:
                deltas[prefix] = 0.0 if cur == 0 else 100.0
            else:
                deltas[prefix] = ((cur - prev) / abs(prev)) * 100.0

    walk("", current, previous)
    return deltas


# ---------- Dashboard ----------

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

    def update(self, cycle: int, asset: str, step: str, history: list[CycleResult],
               run_completed: int = 0) -> None:
        self.cycle = cycle
        self.current_asset = asset
        self.step = step
        self.history = history
        self.run_completed = run_completed
        if step == "Core-AI Training" or self.cycle_started is None:
            self.cycle_started = time.time()

    def render(self) -> Panel:
        layout = Layout()
        children = [Layout(self._header(), name="header", size=3)]
        for asset in self.assets:
            children.append(Layout(self._asset_panel(asset), name=f"asset-{asset}", size=15))
        children.append(Layout(self._exit_ai_panel(), name="exit", size=8))
        children.append(Layout(self._trend(), name="trend", size=5))
        layout.split_column(*children)
        return Panel(layout, title="[bold cyan]Trading-Bot Training-Loop · Gold & Silber[/]", border_style="cyan")

    def _header(self) -> Panel:
        elapsed = "0s" if self.cycle_started is None else _format_duration(time.time() - self.cycle_started)
        if self.total_cycles:
            cycle_info = f"Zyklus #{self.cycle} (Sitzung {self.run_completed}/{self.total_cycles})"
        else:
            cycle_info = f"Zyklus #{self.cycle} (endlos)"
        text = Text.assemble(
            (cycle_info, "bold yellow"), "  ·  ",
            ("Asset: ", "dim"), (self.current_asset.upper() or "—", "bold magenta"), "  ·  ",
            ("Schritt: ", "dim"), (self.step, "bold green"), "  ·  ",
            ("Laufzeit: ", "dim"), (elapsed, "white"),
        )
        return Panel(text, border_style="dim")

    def _asset_panel(self, asset: str) -> Panel:
        history_for_asset = [h for h in self.history if h.asset == asset]
        prev = history_for_asset[-2] if len(history_for_asset) >= 2 else None
        cur = history_for_asset[-1] if history_for_asset else None
        label = ASSETS[asset]["label"].upper()
        color = "green" if asset == "gold" else "blue"

        layout = Layout()
        layout.split_row(
            Layout(self._core_table(prev, cur, label), name="core"),
            Layout(self._backtest_table(prev, cur, label), name="bt"),
        )
        return Panel(layout, title=f"[bold {color}]{label}[/]", border_style=color)

    def _core_table(self, prev: CycleResult | None, cur: CycleResult | None, label: str) -> Panel:
        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column(f"{label} Core AI", style="cyan", no_wrap=True)
        table.add_column("Vorher", justify="right")
        table.add_column("Aktuell", justify="right")
        table.add_column("Diff %", justify="right")
        for model in ("xgboost", "lightgbm"):
            for metric, mlabel, fmt in [
                ("profit_factor", f"{model.upper()} PF",     "{:.2f}"),
                ("sharpe",        f"{model.upper()} Sharpe", "{:.2f}"),
                ("win_rate",      f"{model.upper()} WR",     "{:.1%}"),
            ]:
                p_val = _dig(prev, ["core_ai", model, metric]) if prev else None
                c_val = _dig(cur, ["core_ai", model, metric]) if cur else None
                delta = _dig(cur, ["improvements_pct", f"core_ai.{model}.{metric}"]) if cur else None
                table.add_row(
                    mlabel,
                    fmt.format(p_val) if p_val is not None else "—",
                    fmt.format(c_val) if c_val is not None else "—",
                    _fmt_delta(delta),
                )
        return Panel(table, border_style="dim")

    def _backtest_table(self, prev: CycleResult | None, cur: CycleResult | None, label: str) -> Panel:
        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column(f"{label} Backtest", style="cyan", no_wrap=True)
        table.add_column("Vorher", justify="right")
        table.add_column("Aktuell", justify="right")
        table.add_column("Diff %", justify="right")
        for metric, mlabel, fmt in [
            ("profit_factor",    "Profit Factor",  "{:.2f}"),
            ("sharpe_ratio",     "Sharpe Ratio",   "{:.2f}"),
            ("win_rate",         "Win Rate",       "{:.1%}"),
            ("total_pips",       "Total Pips",     "{:+.1f}"),
            ("max_drawdown_pct", "Max DD %",       "{:.1%}"),
            ("n_trades",         "Trades",         "{:.0f}"),
        ]:
            p_val = _dig(prev, ["backtest", metric]) if prev else None
            c_val = _dig(cur, ["backtest", metric]) if cur else None
            delta = _dig(cur, ["improvements_pct", f"backtest.{metric}"]) if cur else None
            table.add_row(
                mlabel,
                fmt.format(p_val) if p_val is not None else "—",
                fmt.format(c_val) if c_val is not None else "—",
                _fmt_delta(delta),
            )
        return Panel(table, border_style="dim")

    def _exit_ai_panel(self) -> Panel:
        cur = self.history[-1] if self.history else None
        prev = self.history[-2] if len(self.history) >= 2 else None
        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column("Exit AI (gemeinsam)", style="cyan", no_wrap=True)
        table.add_column("Vorher", justify="right")
        table.add_column("Aktuell", justify="right")
        table.add_column("Diff %", justify="right")
        for metric, label, fmt in [
            ("accuracy",            "Accuracy",            "{:.1%}"),
            ("calibration_score",   "Calibration Score",   "{:.3f}"),
            ("profit_factor_proxy", "Profit-Factor (Proxy)","{:.2f}"),
            ("trade_retention",     "Trade Retention",     "{:.1%}"),
        ]:
            p_val = _dig(prev, ["exit_ai", metric]) if prev else None
            c_val = _dig(cur, ["exit_ai", metric]) if cur else None
            delta = _dig(cur, ["improvements_pct", f"exit_ai.{metric}"]) if cur else None
            table.add_row(
                label,
                fmt.format(p_val) if isinstance(p_val, (int, float)) and p_val != 0 else "—",
                fmt.format(c_val) if isinstance(c_val, (int, float)) and c_val != 0 else "—",
                _fmt_delta(delta),
            )
        promo_cur = _dig(cur, ["exit_ai", "promotion_status"]) or "—"
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
            pf_values = [h.backtest.get("profit_factor", 0.0) for h in hs]
            arrow = (
                "↑" if len(pf_values) >= 2 and pf_values[-1] > pf_values[0]
                else "↓" if len(pf_values) >= 2 and pf_values[-1] < pf_values[0]
                else "→"
            )
            trend = " > ".join(f"{v:.2f}" for v in pf_values)
            lines.append(f"{ASSETS[asset]['label']:7s}: {trend}  {arrow}")
        return Panel(
            Text("Trend Profit-Factor letzte 5 Zyklen:\n" + "\n".join(lines), style="white"),
            border_style="dim",
        )


def _dig(d: dict | CycleResult | None, keys: list[str]) -> Any:
    if d is None:
        return None
    cur: Any = d.__dict__ if isinstance(d, CycleResult) else d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _fmt_delta(delta: float | None) -> str:
    if delta is None:
        return "—"
    if abs(delta) < 0.01:
        return "[dim]0.0%[/]"
    color = "bold green" if delta > 0 else "bold red"
    return f"[{color}]{delta:+.1f}%[/]"


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


# ---------- Per-asset cycle ----------

_stop_requested = False


def _handle_sigint(signum: int, frame: Any) -> None:
    global _stop_requested
    _stop_requested = True


def run_asset_cycle(
    cycle: int,
    asset: str,
    args: argparse.Namespace,
    dashboard: Dashboard,
    history: list[CycleResult],
    live: Live,
) -> CycleResult | None:
    asset_cfg = ASSETS[asset]
    csv_path = asset_cfg["csv"]
    started = time.time()
    started_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if not (PROJECT_ROOT / csv_path).exists():
        live.console.print(f"[red]Daten-CSV fehlt: {csv_path} — wird übersprungen[/]")
        return None

    dashboard.update(cycle, asset, "Core-AI Training", history)
    live.update(dashboard.render())
    rc, out = _run_subprocess(
        [PYTHON, "scripts/train_models.py",
         "--csv", csv_path,
         "--pip-size", str(asset_cfg["pip_size"]),
         "--tp-pips", str(asset_cfg["tp_pips"]),
         "--sl-pips", str(asset_cfg["sl_pips"]),
         "--no-dynamic-atr",
         "--timeframe", "1h",
         "--output", "ai_engine/saved_models",
         "--min-data-months", str(args.min_data_months)],
        "train_models",
    )
    if rc != 0:
        live.console.print(f"[red]{asset_cfg['label']} Core-AI fehlgeschlagen (rc={rc}):[/]\n{out[-1500:]}")
        return None

    version_dir = find_version_dir_after(started - 5)
    if version_dir is None:
        live.console.print(f"[red]Kein Versions-Verzeichnis nach Core-AI-Training gefunden[/]")
        return None

    dashboard.update(cycle, asset, "Exit-AI Training", history)
    live.update(dashboard.render())
    rc, out = _run_subprocess(
        [PYTHON, "scripts/train_exit_ai.py", "--synthetic", str(args.exit_synthetic)],
        "train_exit_ai",
    )
    if rc != 0:
        live.console.print(f"[yellow]Exit-AI Warnung (rc={rc}):[/]\n{out[-500:]}")

    dashboard.update(cycle, asset, "Backtest", history)
    live.update(dashboard.render())
    rc, out = _run_subprocess(
        [PYTHON, "scripts/run_backtest.py",
         "--version-dir", str(version_dir),
         "--csv", csv_path,
         "--timeframe", "1h",
         "--commission", "0.0"],
        "run_backtest",
    )
    if rc != 0:
        live.console.print(f"[yellow]Backtest Warnung (rc={rc}):[/]\n{out[-500:]}")

    metrics = extract_metrics(version_dir)
    prev = latest_for_asset(history, asset)
    prev_metrics = (
        {"core_ai": prev.core_ai, "exit_ai": prev.exit_ai, "backtest": prev.backtest}
        if prev else {}
    )
    improvements = compute_improvements(metrics, prev_metrics)

    return CycleResult(
        cycle=cycle,
        asset=asset,
        started_at=started_iso,
        duration_sec=round(time.time() - started, 1),
        version_dir=str(version_dir.relative_to(PROJECT_ROOT)),
        core_ai=metrics["core_ai"],
        exit_ai=metrics["exit_ai"],
        backtest=metrics["backtest"],
        improvements_pct=improvements,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Continuous training loop for Core-AI + Exit-AI (Gold + Silber)")
    parser.add_argument("--asset", choices=["gold", "silver", "both"], default="both")
    parser.add_argument("--cycles", type=int, default=0, help="Anzahl Zyklen (0 = endlos)")
    parser.add_argument("--cooldown", type=int, default=5, help="Sekunden zwischen Zyklen")
    parser.add_argument("--exit-synthetic", type=int, default=360, help="Synthetic snapshot count for Exit-AI")
    parser.add_argument("--min-data-months", type=int, default=6, help="Mindest-Datenzeitraum in Monaten")
    parser.add_argument("--refresh-data", action="store_true", help="Daten am Loop-Start neu laden")
    parser.add_argument("--refresh-each-cycle", action="store_true",
                        help="Vor jedem Zyklus frische Marktdaten ziehen (für echte cycle-to-cycle Verbesserung)")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_sigint)

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    console = Console(force_terminal=True, legacy_windows=False)
    history = load_history()
    starting_cycle = (max((h.cycle for h in history), default=0) + 1) if history else 1
    selected_assets = ["gold", "silver"] if args.asset == "both" else [args.asset]

    dashboard = Dashboard(console, args.cycles or None, selected_assets)
    dashboard.history = history

    console.print(f"[bold cyan]Training-Loop startet[/] · Assets: {', '.join(a.upper() for a in selected_assets)} · ab Zyklus {starting_cycle}")
    console.print("[dim]Strg+C: nach aktuellem Subzyklus sauber beenden[/]\n")

    ensure_data(args.refresh_data, console)

    cycle = starting_cycle
    completed = 0
    with Live(dashboard.render(), console=console, refresh_per_second=2, screen=False) as live:
        while True:
            if args.cycles and completed >= args.cycles:
                break
            if _stop_requested:
                live.console.print("[yellow]Stop-Signal empfangen — beende sauber[/]")
                break

            if args.refresh_each_cycle and cycle > starting_cycle:
                live.console.print("[dim]Lade frische Marktdaten für diesen Zyklus...[/]")
                ensure_data(force=True, console=live.console)

            for asset in selected_assets:
                if _stop_requested:
                    break
                result = run_asset_cycle(cycle, asset, args, dashboard, history, live)
                if result is None:
                    live.console.print(f"[red]{ASSETS[asset]['label']}-Subzyklus übersprungen[/]")
                    continue
                history.append(result)
                save_history(history)
                dashboard.update(cycle, asset, "Fertig", history, run_completed=completed)
                live.update(dashboard.render())
                live.console.print(
                    f"[green]✓ Zyklus {cycle} {ASSETS[asset]['label']} abgeschlossen "
                    f"in {_format_duration(result.duration_sec)}[/]"
                )

            cycle += 1
            completed += 1

            if args.cycles and completed >= args.cycles:
                break
            if _stop_requested:
                break

            for _ in range(args.cooldown):
                if _stop_requested:
                    break
                time.sleep(1)

    console.print(f"\n[bold green]Training-Loop beendet[/] · {completed} Zyklen ausgeführt · History: {HISTORY_FILE}")


if __name__ == "__main__":
    main()
