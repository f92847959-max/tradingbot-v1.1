"""One-shot training runner with a small live ETA dashboard."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Deque

import pandas as pd
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.training.config import PYTHON  # noqa: E402
from scripts.training.dashboard import format_duration  # noqa: E402


OHLCV_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}

RESAMPLE_RULES = {
    "1m": "1min",
    "5m": "5min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
}

STEP_PROGRESS = {
    1: 5.0,
    2: 12.0,
    3: 23.0,
    4: 31.0,
    5: 38.0,
    6: 45.0,
    7: 93.0,
}


class TrainingState:
    def __init__(self, *, timeframe: str, source_csv: Path, prepared_csv: Path, command: list[str]) -> None:
        self.timeframe = timeframe
        self.source_csv = source_csv
        self.prepared_csv = prepared_csv
        self.command = command
        self.started = time.time()
        self.status = "prepare"
        self.current_step = "Preparing data"
        self.progress = 1.0
        self.total_windows: int | None = None
        self.current_window: int | None = None
        self.return_code: int | None = None
        self.tail: Deque[str] = deque(maxlen=10)
        self.lock = threading.Lock()

    def add_line(self, line: str) -> None:
        clean = line.strip()
        if not clean:
            return
        with self.lock:
            self.tail.append(clean)
            self._update_from_line(clean)

    def _update_from_line(self, line: str) -> None:
        self.status = "running"
        step_match = re.search(r"(?<!\d)([1-7])/7\s+([^.\n]+)", line)
        if step_match:
            step_no = int(step_match.group(1))
            self.current_step = f"{step_no}/7 {step_match.group(2).strip()}"
            self.progress = max(self.progress, STEP_PROGRESS[step_no])

        windows_match = re.search(r"Walk-forward:\s+(\d+)\s+expanding windows", line, re.IGNORECASE)
        if not windows_match:
            windows_match = re.search(r"Walk-Forward Validation:\s+(\d+)\s+windows", line, re.IGNORECASE)
        if windows_match:
            self.total_windows = int(windows_match.group(1))
            self.current_step = f"Walk-forward ({self.total_windows} windows)"
            self.progress = max(self.progress, STEP_PROGRESS[6])

        window_match = re.search(r"--- Window\s+(\d+):", line)
        if window_match:
            self.current_window = int(window_match.group(1))
            self.current_step = f"Window {self.current_window}"
            self._set_window_progress(0.15)

        xgb_match = re.search(r"Training XGBoost .*window\s+(\d+)", line)
        if xgb_match:
            self.current_window = int(xgb_match.group(1))
            self.current_step = f"Window {self.current_window}: XGBoost"
            self._set_window_progress(0.35)

        lgbm_match = re.search(r"Training LightGBM .*window\s+(\d+)", line)
        if lgbm_match:
            self.current_window = int(lgbm_match.group(1))
            self.current_step = f"Window {self.current_window}: LightGBM"
            self._set_window_progress(0.70)

        finished_window_match = re.search(r"Window\s+(\d+):\s+\d+\s+trades", line)
        if finished_window_match:
            self.current_window = int(finished_window_match.group(1))
            self.current_step = f"Window {self.current_window}: done"
            self._set_window_progress(1.0)

        if "Saving models with versioning" in line:
            self.current_step = "Saving models"
            self.progress = max(self.progress, STEP_PROGRESS[7])

        if "Training complete" in line:
            self.current_step = "Complete"
            self.progress = 100.0

    def _set_window_progress(self, inner_fraction: float) -> None:
        if not self.total_windows or self.current_window is None:
            self.progress = max(self.progress, 50.0)
            return
        completed_before = max(0, min(self.current_window, self.total_windows))
        window_fraction = (completed_before + inner_fraction) / self.total_windows
        self.progress = max(self.progress, 45.0 + (window_fraction * 45.0))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="One-shot training dashboard")
    parser.add_argument("--timeframe", default="4h", choices=sorted(RESAMPLE_RULES))
    parser.add_argument("--source-csv", default=None)
    parser.add_argument("--prepared-csv", default=None)
    parser.add_argument("--output", default="ai_engine/saved_models")
    parser.add_argument("--min-data-months", type=int, default=6)
    parser.add_argument("--tp-pips", type=float, default=1500.0)
    parser.add_argument("--sl-pips", type=float, default=800.0)
    parser.add_argument("--pip-size", type=float, default=0.01)
    parser.add_argument("--max-holding", type=int, default=15)
    parser.add_argument("--prepare-only", action="store_true")
    return parser


def prepare_csv(source_csv: Path, prepared_csv: Path, timeframe: str) -> int:
    if not source_csv.exists():
        raise FileNotFoundError(f"Source CSV not found: {source_csv}")
    df = pd.read_csv(source_csv)
    if "timestamp" not in df.columns:
        raise ValueError(f"CSV has no timestamp column: {source_csv}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()

    missing = {"open", "high", "low", "close"}.difference(df.columns)
    if missing:
        raise ValueError(f"CSV misses OHLC columns: {sorted(missing)}")
    if "volume" not in df.columns:
        df["volume"] = 0.0

    rule = RESAMPLE_RULES[timeframe]
    out = df.resample(rule, label="left", closed="left").agg(OHLCV_AGG)
    out = out.dropna(subset=["open", "high", "low", "close"])
    out.index.name = "timestamp"
    prepared_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(prepared_csv)
    return len(out)


def build_train_command(args: argparse.Namespace, prepared_csv: Path) -> list[str]:
    return [
        PYTHON,
        "-u",
        "scripts/train_models.py",
        "--csv",
        str(prepared_csv.relative_to(PROJECT_ROOT)),
        "--timeframe",
        args.timeframe,
        "--output",
        args.output,
        "--min-data-months",
        str(args.min_data_months),
        "--tp-pips",
        str(args.tp_pips),
        "--sl-pips",
        str(args.sl_pips),
        "--pip-size",
        str(args.pip_size),
        "--max-holding",
        str(args.max_holding),
    ]


def render(state: TrainingState, *, row_count: int, log_file: Path) -> Panel:
    with state.lock:
        elapsed = time.time() - state.started
        progress = max(0.0, min(100.0, state.progress))
        eta = estimate_remaining(elapsed, progress, state.return_code)
        status = state.status
        current_step = state.current_step
        total_windows = state.total_windows
        current_window = state.current_window
        tail = list(state.tail)
        return_code = state.return_code

    table = Table.grid(expand=True)
    table.add_column(ratio=1)
    table.add_column(ratio=2)
    table.add_row("Status", status.upper() if return_code is None else final_status(return_code))
    table.add_row("Timeframe", state.timeframe)
    table.add_row("Rows", str(row_count))
    table.add_row("Step", current_step)
    if total_windows is not None:
        table.add_row("Window", f"{current_window if current_window is not None else '-'} / {total_windows - 1}")
    table.add_row("Elapsed", format_duration(elapsed))
    table.add_row("ETA", eta)
    table.add_row("Prepared CSV", str(state.prepared_csv.relative_to(PROJECT_ROOT)))
    table.add_row("Log", str(log_file.relative_to(PROJECT_ROOT)))
    table.add_row("Progress", f"{progress:5.1f}% {progress_bar(progress)}")

    log_text = "\n".join(tail[-8:]) if tail else "Waiting for training output..."
    return Panel(
        Group(table, Panel(Text(log_text), title="Last output", border_style="dim")),
        title=f"[bold cyan]{state.timeframe} Training Dashboard[/]",
        border_style="cyan" if return_code is None else ("green" if return_code == 0 else "red"),
    )


def progress_bar(progress: float, width: int = 28) -> str:
    done = int(round(width * progress / 100.0))
    done = max(0, min(width, done))
    return "[" + ("#" * done) + ("-" * (width - done)) + "]"


def estimate_remaining(elapsed: float, progress: float, return_code: int | None) -> str:
    if return_code is not None:
        return "0s"
    if progress < 3:
        return "calculating"
    remaining = elapsed * ((100.0 - progress) / progress)
    return format_duration(max(0.0, remaining))


def final_status(return_code: int) -> str:
    return "DONE" if return_code == 0 else f"FAILED rc={return_code}"


def stream_process(proc: subprocess.Popen[str], state: TrainingState, log_file: Path) -> None:
    with log_file.open("w", encoding="utf-8", errors="replace") as handle:
        handle.write("Command: " + " ".join(state.command) + "\n\n")
        handle.flush()
        assert proc.stdout is not None
        for line in proc.stdout:
            handle.write(line)
            handle.flush()
            state.add_line(line)


def main() -> int:
    args = build_parser().parse_args()
    default_source = "data/gold_1h.csv" if args.timeframe == "4h" else f"data/gold_{args.timeframe}.csv"
    source_csv = (PROJECT_ROOT / (args.source_csv or default_source)).resolve()
    prepared_default = PROJECT_ROOT / "data" / f"gold_{args.timeframe}.csv"
    prepared_csv = (PROJECT_ROOT / args.prepared_csv).resolve() if args.prepared_csv else prepared_default
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"training_{args.timeframe}_{timestamp}.log"

    console = Console(force_terminal=True, legacy_windows=False)
    try:
        row_count = prepare_csv(source_csv, prepared_csv, args.timeframe)
    except Exception as exc:
        console.print(f"[red]Could not prepare training CSV:[/] {exc}")
        return 1

    command = build_train_command(args, prepared_csv)
    if args.prepare_only:
        console.print(f"Prepared {row_count} rows -> {prepared_csv}")
        console.print("Command: " + " ".join(command))
        return 0

    state = TrainingState(
        timeframe=args.timeframe,
        source_csv=source_csv,
        prepared_csv=prepared_csv,
        command=command,
    )
    state.add_line(f"Prepared {row_count} rows from {source_csv.name}")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONUTF8"] = "1"
    proc = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    reader = threading.Thread(target=stream_process, args=(proc, state, log_file), daemon=True)
    reader.start()

    try:
        with Live(render(state, row_count=row_count, log_file=log_file), console=console, refresh_per_second=2) as live:
            while proc.poll() is None:
                live.update(render(state, row_count=row_count, log_file=log_file))
                time.sleep(0.5)
            state.return_code = proc.returncode
            if proc.returncode == 0:
                state.status = "done"
                state.progress = 100.0
            else:
                state.status = "failed"
            reader.join(timeout=2)
            live.update(render(state, row_count=row_count, log_file=log_file))
    except KeyboardInterrupt:
        state.status = "stopping"
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        return 130

    console.print(
        f"\n[bold {'green' if proc.returncode == 0 else 'red'}]"
        f"{final_status(proc.returncode)}[/] - log: {log_file}"
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
