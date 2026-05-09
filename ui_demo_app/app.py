"""Application orchestration for the terminal UI demo."""

from __future__ import annotations

import argparse
import time
from collections.abc import Sequence
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.panel import Panel

from .analysis import GeminiAnalysisClient
from .config import DemoConfig
from .layout import make_layout, progress_bar
from .plotting import PlotextRenderable
from .rendering import metrics_table, summary_details, summary_table
from .simulator import TrainingFrame, TrainingSimulator, TrainingStats


def run_mock_ui(config: DemoConfig | None = None) -> None:
    config = config or DemoConfig.from_env()
    console = Console()
    layout = make_layout()
    simulator = TrainingSimulator(config)
    last_frame: TrainingFrame | None = None

    layout["header"].update(
        Panel(
            f"[bold gold1]AI TradingBot - Perfect Fit Dashboard "
            f"(Ziel: {config.max_epochs} Epochen)[/bold gold1]",
            style="white on dark_blue",
        ),
    )

    print("Starte UI-Demo... (STRG+C beendet und zeigt den Report)")
    time.sleep(0.2)

    try:
        with Live(
            layout,
            refresh_per_second=config.refresh_per_second,
            screen=config.screen,
            console=console,
        ):
            for epoch in range(1, config.max_epochs + 1):
                last_frame = simulator.step(epoch)
                _update_layout(layout, last_frame, config)
                time.sleep(config.step_delay_sec)
    except KeyboardInterrupt:
        pass

    if last_frame is not None:
        show_summary(console, last_frame.stats, config)


def show_summary(console: Console, stats: TrainingStats, config: DemoConfig) -> None:
    console.clear()
    console.print(
        Panel(
            "[bold gold1]TRAINING ABGESCHLOSSEN - AUSFUEHRLICHER REPORT[/bold gold1]",
            style="white on dark_blue",
        ),
        justify="center",
    )
    console.print()
    console.print(summary_table(stats))
    console.print()
    console.print(
        Panel(
            summary_details(stats, config.max_epochs),
            title="Logik-Analyst & Diagnose-Report",
            border_style="blue",
        ),
    )
    console.print()

    with console.status("[bold cyan]Warte auf KI-Auswertung...[/bold cyan]", spinner="dots"):
        llm_response = GeminiAnalysisClient(config).analyze(stats)

    console.print(
        Panel(
            llm_response,
            title="Cloud LLM Experten-Feedback",
            border_style="magenta",
        ),
    )
    console.print()


def _update_layout(layout: object, frame: TrainingFrame, config: DemoConfig) -> None:
    series = frame.series
    layout["metrics"].update(Panel(metrics_table(frame, config.max_epochs)))
    layout["system_stats"].update(
        Panel(
            "System Running...\n"
            f"Report: {config.report_path}",
            title="Logs",
        ),
    )
    layout["graph_equity"].update(
        Panel(
            PlotextRenderable(series.equity, "PnL", "cyan", title="Portfolio PnL"),
            title="Portfolio PnL",
        ),
    )
    layout["graph_acc"].update(
        Panel(
            PlotextRenderable(series.accuracy, "Acc", "green", title="Accuracy"),
            title="Accuracy",
        ),
    )
    layout["graph_loss"].update(
        Panel(
            PlotextRenderable(
                series.train_loss,
                "Train",
                "blue",
                series.validation_loss,
                "Val",
                "red",
                title="Train vs Val Loss",
            ),
            title="Train vs Val Loss",
        ),
    )
    layout["graph_conf"].update(
        Panel(
            PlotextRenderable(series.confidence, "Conf", "magenta", title="Confidence"),
            title="Confidence",
        ),
    )
    bar = progress_bar(frame.epoch, config.max_epochs)
    layout["footer"].update(
        Panel(
            f"Epoch [{bar}] {frame.epoch / max(1, config.max_epochs) * 100:.1f}% | "
            "[yellow]STRG+C fuer Report[/yellow]",
        ),
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the terminal UI training demo.")
    parser.add_argument("--max-epochs", type=int)
    parser.add_argument("--history-len", type=int)
    parser.add_argument("--refresh-per-second", type=int)
    parser.add_argument("--step-delay-sec", type=float)
    parser.add_argument("--llm-timeout-sec", type=float)
    parser.add_argument("--report-path", type=Path)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--no-screen", action="store_true")
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> DemoConfig:
    config = DemoConfig.from_env()
    return config.with_overrides(
        max_epochs=args.max_epochs,
        history_len=args.history_len,
        refresh_per_second=args.refresh_per_second,
        step_delay_sec=args.step_delay_sec,
        llm_timeout_sec=args.llm_timeout_sec,
        report_path=args.report_path,
        llm_enabled=False if args.no_llm else None,
        screen=False if args.no_screen else None,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    run_mock_ui(config_from_args(args))
    return 0
