"""CLI-dispatch smoke tests for `main.py` (Plan 18-01).

Goal: prove the dispatcher refactor is non-breaking. We spawn `main.py` as
a real subprocess (rather than calling `dispatch()` in-process) so that:

1. The top-level `os.chdir(...)` in main.py is exercised.
2. Argparse exit-code semantics (0 for `--help`, 2 for unknown args) match
   what real shell invocations would see.
3. No test fixture leaks state into the dispatcher's import path.

The slow live-mode boot test is gated behind `@pytest.mark.slow` so the
fast suite stays under a few seconds.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = PROJECT_ROOT / "main.py"


def _run(args: list[str], cwd: Path | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    """Helper: run `python main.py <args>` and capture stdout/stderr."""
    return subprocess.run(
        [sys.executable, str(MAIN_PY), *args],
        cwd=str(cwd) if cwd else str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def test_main_help_lists_three_modes() -> None:
    """`python main.py --help` advertises all three modes."""
    result = _run(["--help"])
    assert result.returncode == 0, (
        f"main.py --help exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "train" in result.stdout
    assert "backtest" in result.stdout
    assert "live" in result.stdout
    # --profile flag must surface in --help so users discover it.
    assert "--profile" in result.stdout


def test_main_train_passthrough_help() -> None:
    """`python main.py train --help` exposes the start_ai_training flag surface."""
    result = _run(["train", "--help"])
    assert result.returncode == 0, (
        f"main.py train --help exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    # --target is one of the canonical training flags; if this disappears
    # the GUI subprocess contract is broken.
    assert "--target" in result.stdout
    # Spot-check a second flag so a partial-help failure is caught.
    assert "--timeframes" in result.stdout


def test_main_backtest_passthrough_help() -> None:
    """`python main.py backtest --help` exits cleanly and exposes backtest flags."""
    result = _run(["backtest", "--help"])
    assert result.returncode == 0, (
        f"main.py backtest --help exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    # --version-dir is the required flag the runner depends on.
    assert "--version-dir" in result.stdout


def test_main_chdir_resolves_paths() -> None:
    """`main.py` chdirs to its own directory regardless of caller CWD.

    This is the load-bearing invariant for relative paths
    (ai_engine/saved_models/, data/, logs/) -- if it ever breaks,
    `python main.py` from a parent directory will silently fail to find
    saved models.
    """
    with tempfile.TemporaryDirectory() as tmp:
        result = _run(["--help"], cwd=Path(tmp))
        assert result.returncode == 0, (
            f"main.py --help from tmp cwd exit={result.returncode}\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )


def test_main_unknown_subcommand_exits_nonzero() -> None:
    """Unknown subcommands surface as argparse errors, not silent live-mode boots."""
    # `live` mode rejects unknown args; an unknown subcommand falls through
    # to remaining-args validation. Either way: non-zero exit + non-empty stderr.
    result = _run(["doesnotexist"])
    assert result.returncode != 0
    assert result.stderr.strip() != ""


@pytest.mark.slow
def test_main_no_subcommand_is_live() -> None:
    """Bare `python main.py` (no args) boots into live mode.

    Slow because we have to actually start the process, wait for the boot
    log line, then terminate. Skipped by default; opt in with `-m slow`.
    """
    proc = subprocess.Popen(
        [sys.executable, str(MAIN_PY)],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    try:
        boot_seen = False
        # Read up to 3 s of output looking for the bootstrap marker.
        import time

        deadline = time.monotonic() + 5.0
        accumulated = []
        assert proc.stdout is not None
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            accumulated.append(line)
            if "Bootstrapping trading system modules" in line:
                boot_seen = True
                break
        assert boot_seen, (
            "Expected 'Bootstrapping trading system modules...' on stdout.\n"
            f"Got:\n{''.join(accumulated)}"
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
