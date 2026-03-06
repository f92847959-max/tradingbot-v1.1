"""Gold Intraday Trading System -- Main Entry Point.

Runs the autonomous trading loop:
1. Fetch market data (candles + indicators)
2. Generate AI signal (XGBoost + LightGBM ensemble)
3. Filter and score signal (strategy + multi-timeframe)
4. Risk check (11 pre-trade checks)
5. [Semi-Auto] WhatsApp confirmation if enabled
6. Execute trade (if approved)
7. Monitor positions (trailing stops, TP/SL detection)
"""

import asyncio
import contextlib
import functools
import logging
import os
import signal
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

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
# Imports (after dotenv so env vars are available)
# ---------------------------------------------------------------------------

from config.settings import get_settings, Settings  # noqa: E402
from database.connection import init_db, close_db, get_session  # noqa: E402
from api.dependencies import set_trading_system  # noqa: E402

from trading.lifecycle import LifecycleMixin  # noqa: E402
from trading.trading_loop import TradingLoopMixin  # noqa: E402
from trading.signal_generator import SignalGeneratorMixin  # noqa: E402
from trading.monitors import MonitorMixin  # noqa: E402


# ---------------------------------------------------------------------------
# Trading System
# ---------------------------------------------------------------------------


class TradingSystem(LifecycleMixin, TradingLoopMixin, SignalGeneratorMixin, MonitorMixin):
    """Main trading system orchestrator.

    All trading logic is provided by mixin classes:
    - LifecycleMixin: init, health check, start, stop, mode switching
    - TradingLoopMixin: main loop, tick execution, multi-timeframe fetch
    - SignalGeneratorMixin: AI signal generation, signal persistence
    - MonitorMixin: daily cleanup, position monitoring, close handling
    """

    pass  # All methods provided by mixins


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------


async def main() -> None:
    settings = get_settings()

    # Validate configuration
    errors = settings.validate_required()
    if errors:
        for err in errors:
            logger.error("Config error: %s", err)
        logger.error("Fix your .env file (see .env.example)")
        sys.exit(1)

    system = TradingSystem(settings)

    # Graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(system.stop()))
        except NotImplementedError:
            # Windows: add_signal_handler is not supported
            signal.signal(sig, lambda s, f: asyncio.create_task(system.stop()))

    # Inject system into API layer
    set_trading_system(system, time.monotonic())

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
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
