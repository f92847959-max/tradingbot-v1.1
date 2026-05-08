"""CLI orchestration for the continuous training loop."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

from rich.console import Console
from rich.live import Live

from . import process
from .config import ASSETS, HISTORY_FILE, PROJECT_ROOT, PYTHON
from .dashboard import Dashboard, format_duration
from .history import latest_for_asset, load_history, save_history
from .metrics import compute_improvements, extract_metrics, find_version_dir_after
from .models import CycleResult


def _asset_output_dir(asset_cfg: dict) -> str:
    return str(asset_cfg.get("output") or "ai_engine/saved_models")


def _build_train_models_command(
    asset_cfg: dict,
    args: argparse.Namespace,
    output_dir: str,
) -> list[str]:
    return [
        PYTHON,
        "scripts/train_models.py",
        "--csv",
        asset_cfg["csv"],
        "--pip-size",
        str(asset_cfg["pip_size"]),
        "--tp-pips",
        str(asset_cfg["tp_pips"]),
        "--sl-pips",
        str(asset_cfg["sl_pips"]),
        "--no-dynamic-atr",
        "--timeframe",
        "1h",
        "--output",
        output_dir,
        "--min-data-months",
        str(args.min_data_months),
    ]


def _build_exit_ai_command(args: argparse.Namespace, output_dir: str) -> list[str]:
    return [
        PYTHON,
        "scripts/train_exit_ai.py",
        "--synthetic",
        str(args.exit_synthetic),
        "--output",
        output_dir,
    ]


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
    output_dir = _asset_output_dir(asset_cfg)
    started = time.time()
    started_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if not (PROJECT_ROOT / csv_path).exists():
        live.console.print(f"[red]Daten-CSV fehlt: {csv_path} - wird uebersprungen[/]")
        return None

    dashboard.update(cycle, asset, "Core-AI Training", history)
    live.update(dashboard.render())
    rc, out = process._run_subprocess(
        _build_train_models_command(asset_cfg, args, output_dir),
        "train_models",
    )
    if rc != 0:
        live.console.print(
            f"[red]{asset_cfg['label']} Core-AI fehlgeschlagen (rc={rc}):[/]\n{out[-1500:]}"
        )
        return None

    version_dir = find_version_dir_after(started - 5, PROJECT_ROOT / output_dir)
    if version_dir is None:
        live.console.print("[red]Kein Versions-Verzeichnis nach Core-AI-Training gefunden[/]")
        return None

    dashboard.update(cycle, asset, "Exit-AI Training", history)
    live.update(dashboard.render())
    rc, out = process._run_subprocess(
        _build_exit_ai_command(args, output_dir),
        "train_exit_ai",
    )
    if rc != 0:
        live.console.print(f"[yellow]Exit-AI Warnung (rc={rc}):[/]\n{out[-500:]}")

    dashboard.update(cycle, asset, "Backtest", history)
    live.update(dashboard.render())
    rc, out = process._run_subprocess(
        [
            PYTHON,
            "scripts/run_backtest.py",
            "--version-dir",
            str(version_dir),
            "--csv",
            csv_path,
            "--timeframe",
            "1h",
            "--commission",
            "0.0",
        ],
        "run_backtest",
    )
    if rc != 0:
        live.console.print(f"[yellow]Backtest Warnung (rc={rc}):[/]\n{out[-500:]}")

    metrics = extract_metrics(version_dir)
    prev = latest_for_asset(history, asset)
    prev_metrics = (
        {"core_ai": prev.core_ai, "exit_ai": prev.exit_ai, "backtest": prev.backtest}
        if prev
        else {}
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Continuous training loop for Core-AI + Exit-AI (Gold + Silber)"
    )
    parser.add_argument("--asset", choices=["gold", "silver", "both"], default="both")
    parser.add_argument("--cycles", type=int, default=0, help="Anzahl Zyklen (0 = endlos)")
    parser.add_argument("--cooldown", type=int, default=5, help="Sekunden zwischen Zyklen")
    parser.add_argument(
        "--exit-synthetic",
        type=int,
        default=360,
        help="Synthetic snapshot count for Exit-AI",
    )
    parser.add_argument(
        "--min-data-months",
        type=int,
        default=6,
        help="Mindest-Datenzeitraum in Monaten",
    )
    parser.add_argument("--refresh-data", action="store_true", help="Daten am Loop-Start neu laden")
    parser.add_argument(
        "--refresh-each-cycle",
        action="store_true",
        help="Vor jedem Zyklus frische Marktdaten ziehen",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    process.install_signal_handler()

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

    console.print(
        f"[bold cyan]Training-Loop startet[/] - Assets: "
        f"{', '.join(a.upper() for a in selected_assets)} - ab Zyklus {starting_cycle}"
    )
    console.print("[dim]Strg+C: sauber beenden; erneut: sofort abbrechen[/]\n")

    process.ensure_data(args.refresh_data, console)

    cycle = starting_cycle
    completed = 0
    with Live(dashboard.render(), console=console, refresh_per_second=2, screen=False) as live:
        while True:
            if args.cycles and completed >= args.cycles:
                break
            if process.stop_requested():
                live.console.print("[yellow]Stop-Signal empfangen - beende sauber[/]")
                break

            if args.refresh_each_cycle and cycle > starting_cycle:
                live.console.print("[dim]Lade frische Marktdaten fuer diesen Zyklus...[/]")
                process.ensure_data(force=True, console=live.console)

            for asset in selected_assets:
                if process.stop_requested():
                    break
                result = run_asset_cycle(cycle, asset, args, dashboard, history, live)
                if result is None:
                    live.console.print(f"[red]{ASSETS[asset]['label']}-Subzyklus uebersprungen[/]")
                    continue
                history.append(result)
                save_history(history)
                dashboard.update(cycle, asset, "Fertig", history, run_completed=completed)
                live.update(dashboard.render())
                live.console.print(
                    f"[green]Zyklus {cycle} {ASSETS[asset]['label']} abgeschlossen "
                    f"in {format_duration(result.duration_sec)}[/]"
                )

            cycle += 1
            completed += 1

            if args.cycles and completed >= args.cycles:
                break
            if process.stop_requested():
                break

            for _ in range(args.cooldown):
                if process.stop_requested():
                    break
                time.sleep(1)

    console.print(
        f"\n[bold green]Training-Loop beendet[/] - {completed} Zyklen ausgefuehrt - "
        f"History: {HISTORY_FILE}"
    )
