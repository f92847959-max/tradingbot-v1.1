import asyncio
import httpx
import os
import logging
from datetime import datetime, timezone

# Configuration
TRADER_URL = os.getenv("TRADER_URL", "http://localhost:8000")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - WATCHDOG - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _build_telegram_url(token: str) -> str:
    """Build the Telegram sendMessage URL.

    Kept in a helper so the URL (which embeds the bot token) is never
    interpolated into log strings or exception messages by accident.
    """
    return f"https://api.telegram.org/bot{token}/sendMessage"


async def send_telegram_alert(message: str):
    """Sends a critical alert to the trader via Telegram.

    The bot token is part of the request URL and MUST NEVER be logged.
    On failure we emit a generic error message that does not include
    the URL or the underlying exception text (which httpx may embed
    the URL into).
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not set. Alert skipped.")
        return

    url = _build_telegram_url(TELEGRAM_TOKEN)
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": f"CRITICAL ALERT: {message}"}

    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload)
    except Exception:
        # Do NOT log the exception object directly -- httpx errors can
        # contain the request URL (and thus the bot token).
        logger.error("Failed to send Telegram alert (see watchdog status).")

async def check_health():
    """Pings the trader service health endpoint."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{TRADER_URL}/health")

            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError:
                    logger.error("Trader /health returned non-JSON payload")
                    await send_telegram_alert("Trader /health returned non-JSON payload")
                    return False
                # Check for stale heartbeat (e.g., last_tick > 60s ago)
                default_ts = datetime.now(timezone.utc).isoformat()
                last_tick_raw = data.get("last_tick_timestamp", default_ts)
                try:
                    last_tick = datetime.fromisoformat(last_tick_raw)
                except (TypeError, ValueError):
                    logger.error("Could not parse last_tick_timestamp; treating as stale")
                    await send_telegram_alert("Trader heartbeat unparsable -- treating as stale")
                    return False
                if last_tick.tzinfo is None:
                    last_tick = last_tick.replace(tzinfo=timezone.utc)
                delta = (datetime.now(timezone.utc) - last_tick).total_seconds()
                
                if delta > 60:
                    logger.error(f"Trader is zombie! Last tick was {delta}s ago.")
                    await send_telegram_alert(f"Trader ZOMBIE state detected! Last tick: {delta}s ago.")
                    # In a real setup, trigger a restart here (e.g., via Docker socket)
                    return False
                
                logger.info("Trader is healthy.")
                return True
            else:
                logger.error(f"Trader returned status {response.status_code}")
                await send_telegram_alert(f"Trader unhealthy. Status: {response.status_code}")
                return False

    except httpx.ConnectError:
        logger.error("Could not connect to Trader service.")
        await send_telegram_alert("Trader service UNREACHABLE. Connection refused.")
        return False
    except Exception:
        # Use logger.exception so the traceback goes to logs, but the
        # alert message stays generic. Avoid passing the exception text
        # into the Telegram payload (it may contain the bot URL).
        logger.exception("Health check failed")
        await send_telegram_alert("Watchdog encountered an error during health check.")
        return False

async def main():
    logger.info("Starting Watchdog Service...")
    while True:
        await check_health()
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
