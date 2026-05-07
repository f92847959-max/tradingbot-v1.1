"""Subprocess and signal helpers for training loop commands."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Any

from rich.console import Console

from .config import PROJECT_ROOT, PYTHON


_stop_requested = False
_force_stop_requested = False
_active_proc: subprocess.Popen[str] | None = None


def stop_requested() -> bool:
    return _stop_requested


def install_signal_handler() -> None:
    signal.signal(signal.SIGINT, _handle_sigint)


def _handle_sigint(signum: int, frame: Any) -> None:
    global _force_stop_requested, _stop_requested
    if _stop_requested:
        _force_stop_requested = True
        proc = _active_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
        return
    _stop_requested = True


def _run_subprocess(cmd: list[str], step_name: str) -> tuple[int, str]:
    global _active_proc

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=_subprocess_creation_flags(),
            start_new_session=_subprocess_start_new_session(),
        )
        _active_proc = proc
        stdout, stderr = proc.communicate()
        return proc.returncode, (stdout or "") + (stderr or "")
    except FileNotFoundError as exc:
        return 1, f"{step_name} failed to start: {exc}"
    finally:
        if proc is not None and _active_proc is proc:
            _active_proc = None


def _subprocess_creation_flags() -> int:
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return 0


def _subprocess_start_new_session() -> bool:
    return sys.platform != "win32"


def ensure_data(force: bool, console: Console) -> None:
    cmd = [PYTHON, "scripts/fetch_market_data.py"]
    if force:
        cmd.append("--force")
    console.print(f"[dim]Lade Marktdaten: {' '.join(cmd[1:])}[/]")
    rc, out = _run_subprocess(cmd, "fetch_market_data")
    if rc != 0:
        console.print(f"[red]Daten-Fetch fehlgeschlagen:[/]\n{out[-500:]}")
