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
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# Relative paths (logs/, ai_engine/saved_models/, data/) assume CWD == project root.
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
# ---------------------------------------------------------------------------

from config.settings import get_settings  # noqa: E402
from trading.runner import TradingSystem, run_live  # noqa: E402,F401

__all__ = ["TradingSystem", "run_live"]


if __name__ == "__main__":
    logger.info("Bootstrapping trading system modules...")
    asyncio.run(run_live(get_settings()))
