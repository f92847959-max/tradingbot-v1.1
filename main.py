"""GoldBot 2 -- unified CLI dispatcher.

Three modes, one entry point::

    python main.py                      # live trading (default, no args)
    python main.py live                 # live trading (explicit)
    python main.py train [flags]        # parallel AI training pipeline
    python main.py backtest [flags]     # OOS walk-forward backtest

A `--profile` flag (before the subcommand) routes the dispatched call through
`scripts.profiling_harness.profile_call`, which dumps a cProfile to
`logs/profiling/<mode>_<ts>.prof` plus a top-N text summary.

Backward compatibility: bare `python main.py` (no args) defaults to live mode
and reproduces the exact boot sequence that existed before the dispatcher
refactor.

`TradingSystem` and `run_live` are re-exported from `trading.runner` so legacy
callers (api/dependencies.py TYPE_CHECKING import, tests/test_lifecycle.py
`from main import TradingSystem`) keep working without modification.
"""

import argparse
import asyncio
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# Relative paths (logs/, ai_engine/saved_models/, data/) assume CWD == project
# root. This must run BEFORE any other import that resolves relative paths.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Bootstrap -- pydantic-settings (config/settings.py) handles .env loading
# (including the external ~/secrets/ai-trading-gold/.env path resolution).
# Do NOT call load_dotenv() here: it would double-load env vars and also
# silently override the pydantic-settings resolution order.
# ---------------------------------------------------------------------------

os.makedirs("logs", exist_ok=True)

log_level = os.getenv("LOG_LEVEL", "INFO")
log_format = "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"

logging.basicConfig(
    level=log_level,
    format=log_format,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(
            "logs/trading.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        ),
    ],
)
logger = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Re-export TradingSystem and run_live from trading.runner so existing
# callers (api/dependencies.py TYPE_CHECKING import, tests/test_lifecycle.py
# `from main import TradingSystem`) continue to work without modification.
# Lazy: import only when something asks for it via `from main import ...`.
# ---------------------------------------------------------------------------

from trading.runner import TradingSystem, run_live  # noqa: E402,F401

__all__ = ["TradingSystem", "run_live"]


# ---------------------------------------------------------------------------
# Argparse dispatcher
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goldbot",
        description="GoldBot 2 unified entry: live trading, AI training, OOS backtest.",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Enable cProfile output to logs/profiling/<mode>_<timestamp>.prof",
    )

    subparsers = parser.add_subparsers(
        dest="mode",
        title="modes",
        metavar="{train,backtest,live}",
        help="Operation mode. Default (no subcommand) is 'live'.",
    )

    # Train and backtest subparsers leave their flag surface empty here;
    # the wrapper modules (start_ai_training.py, scripts/run_backtest.py)
    # own the canonical flag definitions and parse `remaining_argv`
    # themselves via parse_known_args() below. This avoids importing the
    # heavy ML stack at dispatcher load time.
    subparsers.add_parser(
        "train",
        help="Train Core-AI / Exit-AI (delegates to start_ai_training.run_train)",
        add_help=False,
    )
    subparsers.add_parser(
        "backtest",
        help="OOS walk-forward backtest (delegates to scripts.run_backtest.run_backtest)",
        add_help=False,
    )
    subparsers.add_parser(
        "live",
        help="Live trading loop (delegates to trading.runner.run_live)",
    )

    return parser


def _dispatch_train(remaining_argv: list[str], profile: bool) -> int:
    # Lazy import: keeps `main.py --help` fast and avoids loading the ML
    # stack for non-training modes.
    from start_ai_training import run_train

    if profile:
        from scripts.profiling_harness import profile_call

        return int(profile_call(run_train, remaining_argv, mode_label="train"))
    return int(run_train(remaining_argv))


def _dispatch_backtest(remaining_argv: list[str], profile: bool) -> int:
    from scripts.run_backtest import run_backtest

    if profile:
        from scripts.profiling_harness import profile_call

        return int(profile_call(run_backtest, remaining_argv, mode_label="backtest"))
    return int(run_backtest(remaining_argv))


def _dispatch_live(profile: bool) -> int:
    from config.settings import get_settings

    logger.info("Bootstrapping trading system modules...")
    settings = get_settings()
    if profile:
        from scripts.profiling_harness import profile_call

        # profile_call swallows the coroutine's return value (None for live).
        profile_call(asyncio.run, run_live(settings), mode_label="live")
        return 0
    asyncio.run(run_live(settings))
    return 0


def dispatch(argv: list[str] | None = None) -> int:
    """Parse top-level argv and route to the selected mode.

    Uses parse_known_args() so any unknown flags after `train`/`backtest`
    pass through to the wrapper modules untouched.
    """
    parser = _build_parser()
    args, remaining = parser.parse_known_args(argv)

    mode = args.mode
    if mode is None or mode == "live":
        if remaining:
            # Live mode accepts no extra flags; reject to surface mistakes.
            parser.error(f"unrecognized arguments for live mode: {' '.join(remaining)}")
        return _dispatch_live(profile=args.profile)
    if mode == "train":
        return _dispatch_train(remaining, profile=args.profile)
    if mode == "backtest":
        return _dispatch_backtest(remaining, profile=args.profile)

    parser.error(f"unknown mode: {mode}")
    return 2  # parser.error raises SystemExit; this is unreachable but typed.


if __name__ == "__main__":
    sys.exit(dispatch(sys.argv[1:]))
