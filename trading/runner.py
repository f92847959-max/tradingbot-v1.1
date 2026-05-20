"""Trading-system runner.

Owns the live-mode `TradingSystem` composition (mixin-based) and the
`run_live(settings)` coroutine that wires up the signal handlers, the optional
FastAPI server and the trading lifecycle.

This module is the single source of truth for the live trading entry point.
`main.py` re-exports `TradingSystem` so existing callers (api/dependencies.py
TYPE_CHECKING imports, tests/test_lifecycle.py) keep working unchanged.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from typing import TYPE_CHECKING

from trading.lifecycle import LifecycleMixin
from trading.monitors import MonitorMixin
from trading.signal_generator import SignalGeneratorMixin
from trading.trading_loop import TradingLoopMixin

if TYPE_CHECKING:
    from config.settings import Settings

logger = logging.getLogger("main")


class TradingSystem(LifecycleMixin, TradingLoopMixin, SignalGeneratorMixin, MonitorMixin):
    """Main trading system orchestrator.

    All trading logic is provided by mixin classes:
    - LifecycleMixin: init, health check, start, stop, mode switching
    - TradingLoopMixin: main loop, tick execution, multi-timeframe fetch
    - SignalGeneratorMixin: AI signal generation, signal persistence
    - MonitorMixin: daily cleanup, position monitoring, close handling
    """

    pass  # All methods provided by mixins


async def run_live(settings: "Settings") -> None:
    """Bootstrap and run the live trading loop.

    Extracted verbatim from the previous main.py main() coroutine. No behavior
    change: same signal-handler dance, same API-server bootstrap, same
    SystemExit propagation through asyncio.run().
    """
    # Validate configuration
    errors = settings.validate_required()
    if errors:
        for err in errors:
            logger.error("Config error: %s", err)
        logger.error("Fix your .env file (see .env.example)")
        # Raise SystemExit so asyncio.run() tears the loop down cleanly.
        # A bare sys.exit(1) here converts to SystemExit on the Task and can
        # leave other scheduled tasks (API server, signal handlers) in a
        # "Task exception was never retrieved" state; historical logs show
        # that pattern on startups where .env was unavailable.
        raise SystemExit(1)

    system = TradingSystem(settings)

    # Graceful shutdown -- idempotent across repeated signals (a second Ctrl+C
    # must not spawn a second stop() coroutine racing the first).
    loop = asyncio.get_running_loop()
    shutdown_requested = False

    def _request_stop() -> None:
        nonlocal shutdown_requested
        if shutdown_requested or loop.is_closed():
            return
        shutdown_requested = True
        asyncio.create_task(system.stop())

    def _signal_handler(_signum: int, _frame: object) -> None:
        # Windows path: signal arrives on the main thread without a loop in
        # asyncio context, so we hop back onto the loop thread before touching
        # any loop state.
        if loop.is_closed():
            return
        loop.call_soon_threadsafe(_request_stop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # Windows: add_signal_handler is not supported
            signal.signal(sig, _signal_handler)

    # NOTE: do NOT call set_trading_system() here -- create_app() in api/app.py
    # already injects the system into the API layer. Calling it twice leaves
    # stale state if the API is later rebuilt.

    try:
        if settings.api_enabled:
            # Conditional imports -- only needed when API is enabled
            import uvicorn
            from api.app import create_app

            fastapi_app = create_app(system)
            api_config = uvicorn.Config(
                fastapi_app,
                host=settings.api_host,
                port=settings.api_port,
                log_level="warning",
                loop="none",
            )
            api_server = uvicorn.Server(api_config)
            logger.info(
                "API server: http://%s:%d/docs", settings.api_host, settings.api_port,
            )

            # Start API server as a background task and then start the trading system.
            server_task = asyncio.create_task(api_server.serve())
            try:
                await system.start()
            finally:
                # ensure server_task is cancelled when system stops
                server_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await server_task
        else:
            await system.start()
    except KeyboardInterrupt:
        await system.stop()
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
        await system.stop()
        # Same reasoning as the config-error path above: let SystemExit
        # propagate through asyncio.run() rather than calling sys.exit()
        # while other tasks may still be queued on the loop.
        raise SystemExit(1)


__all__ = ["TradingSystem", "run_live"]
