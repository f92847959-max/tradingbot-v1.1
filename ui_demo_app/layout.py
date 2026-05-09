"""Rich layout helpers for the terminal UI demo."""

from __future__ import annotations

from rich.layout import Layout


def make_layout() -> Layout:
    layout = Layout(name="root")
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=3),
    )
    layout["main"].split_row(
        Layout(name="left_panel", ratio=2),
        Layout(name="right_panel", ratio=5),
    )
    layout["left_panel"].split_column(
        Layout(name="metrics", ratio=2),
        Layout(name="system_stats", ratio=1),
    )
    layout["right_panel"].split_column(
        Layout(name="top_graphs", ratio=1),
        Layout(name="bottom_graphs", ratio=1),
    )
    layout["top_graphs"].split_row(
        Layout(name="graph_equity", ratio=1),
        Layout(name="graph_acc", ratio=1),
    )
    layout["bottom_graphs"].split_row(
        Layout(name="graph_loss", ratio=1),
        Layout(name="graph_conf", ratio=1),
    )
    return layout


def progress_bar(current: int, total: int, width: int = 40) -> str:
    total_safe = max(1, total)
    ratio = min(1.0, max(0.0, current / total_safe))
    filled = int(ratio * width)
    return "#" * filled + "-" * (width - filled)
