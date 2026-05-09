"""Rich render fragments for the terminal UI demo."""

from __future__ import annotations

from rich.table import Table

from .simulator import TrainingFrame, TrainingStats


def metrics_table(frame: TrainingFrame, max_epochs: int) -> Table:
    table = Table(title="Live Metriken", expand=True)
    table.add_column("Metrik", style="cyan")
    table.add_column("Wert", justify="right", style="magenta")

    loss_color = "green" if frame.validation_loss < 0.2 else "yellow"
    acc_color = "green" if frame.accuracy > 0.6 else "yellow"
    table.add_row("Aktuelle Epoche", f"{frame.epoch} / {max_epochs}")
    table.add_row("Val Loss", f"[{loss_color}]{frame.validation_loss:.4f}[/{loss_color}]")
    table.add_row("Win Rate", f"[{acc_color}]{frame.accuracy * 100:.1f}%[/{acc_color}]")
    table.add_row("Avg Reward", f"{frame.reward:.2f}")
    table.add_row("Drawdown", f"-{frame.drawdown_pct:.1f}%")
    table.add_row("Trades/Batch", f"{frame.trades_per_batch}")
    return table


def summary_table(stats: TrainingStats) -> Table:
    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("Metrik", style="cyan", ratio=1)
    table.add_column("Letzter Wert", justify="right", style="white", ratio=1)
    table.add_column("Bestwert", justify="right", style="green", ratio=1)
    table.add_column("Bewertung", justify="center", ratio=1)

    table.add_row(
        "Portfolio Equity",
        f"${stats.final_eq:.2f}",
        f"${stats.best_eq:.2f}",
        "[green]Profitabel[/green]" if stats.final_eq > 1000 else "[red]Verlust[/red]",
    )
    table.add_row(
        "Win Rate / Acc",
        f"{stats.final_acc * 100:.2f}%",
        f"{stats.best_acc * 100:.2f}%",
        "[green]Solide[/green]" if stats.final_acc > 0.55 else "[yellow]Verbessern[/yellow]",
    )
    table.add_row(
        "Validation Loss",
        f"{stats.final_loss:.4f}",
        f"{stats.min_loss:.4f}",
        "[green]Konvergiert[/green]" if stats.final_loss < 1.0 else "[yellow]Underfitting[/yellow]",
    )
    return table


def summary_details(stats: TrainingStats, max_epochs: int) -> str:
    good_points: list[str] = []
    if stats.final_acc > 0.55:
        good_points.append(
            f"[green]Win-Rate ({stats.final_acc * 100:.1f}%):[/green] "
            "Das Modell gewinnt mehr Trades als es verliert.",
        )
    if stats.final_eq > 1050:
        good_points.append(
            f"[green]Profitabilitaet (+${stats.final_eq - 1000:.2f}):[/green] "
            "Die Equity-Kurve zeigt einen klaren Aufwaertstrend.",
        )
    if stats.min_loss < 0.2:
        good_points.append(
            f"[green]Feature-Konvergenz:[/green] Der Loss fiel auf {stats.min_loss:.4f}.",
        )
    if not good_points:
        good_points.append("[dim]Bisher keine klaren Staerken erkennbar.[/dim]")

    bad_points: list[str] = []
    if stats.final_acc < 0.50:
        bad_points.append(
            f"[red]Win-Rate zu niedrig ({stats.final_acc * 100:.1f}%):[/red] "
            "Labels oder Feature-Skalierung pruefen.",
        )
    if _drawdown_from_peak(stats) > 0.05:
        bad_points.append(
            f"[red]Hoher Drawdown ({_drawdown_from_peak(stats) * 100:.1f}%):[/red] "
            "Stop-Losses und Positionsgroessen pruefen.",
        )
    if stats.final_loss > stats.min_loss * 1.5:
        bad_points.append(
            f"[red]Overfitting-Risiko:[/red] Validation Loss {stats.final_loss:.4f} "
            f"liegt deutlich ueber dem Bestwert {stats.min_loss:.4f}.",
        )
    if not bad_points:
        bad_points.append("[green]Keine kritischen Schwaechen gefunden.[/green]")

    next_steps = _next_steps(stats)
    duration = max(stats.duration_sec, 0.001)
    return f"""[b]System-Laufzeit:[/b]
Absolvierte Epochen: [cyan]{stats.epochs} / {max_epochs}[/cyan] \
({stats.epochs / max(1, max_epochs) * 100:.1f}%) in [cyan]{duration:.1f}s[/cyan] \
({stats.epochs / duration:.1f} Epochen/s)

[b]Was gut funktioniert:[/b]
{chr(10).join(good_points)}

[b]Was verbessert werden muss:[/b]
{chr(10).join(bad_points)}

[b]Strategische Empfehlung:[/b]
{next_steps}"""


def _drawdown_from_peak(stats: TrainingStats) -> float:
    if stats.best_eq <= 0:
        return 0.0
    return max(0.0, (stats.best_eq - stats.final_eq) / stats.best_eq)


def _next_steps(stats: TrainingStats) -> str:
    if stats.final_loss > stats.min_loss * 1.5:
        return (
            "- Overfitting bekaempfen: Dropout/L2 erhoehen oder Modell verkleinern.\n"
            "- Early Stopping nutzen, sobald der Validation Loss steigt."
        )
    if stats.final_acc < 0.52:
        return (
            "- Feature Engineering erweitern.\n"
            "- Class Imbalance und Label-Qualitaet pruefen."
        )
    if stats.final_eq < 1000:
        return "- Risk Management pruefen: Take-Profit sollte groesser als Stop-Loss sein."
    return "- Paper-Trading/Forward-Test starten und Slippage/Spread messen."
