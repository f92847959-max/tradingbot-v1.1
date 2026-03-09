import asyncio
import httpx
import os
import logging
from datetime import datetime

# Configuration
TRADER_URL = os.getenv("TRADER_URL", "http://localhost:8000")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - WATCHDOG - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def send_telegram_alert(message: str):
    """Sends a critical alert to the trader via Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not set. Alert skipped.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": f"🚨 CRITICAL ALERT: {message}"}
    
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload)
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")

async def check_health():
    """Pings the trader service health endpoint."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{TRADER_URL}/health")
            
            if response.status_code == 200:
                data = response.json()
                # Check for stale heartbeat (e.g., last_tick > 60s ago)
                last_tick = datetime.fromisoformat(data.get("last_tick_timestamp", datetime.utcnow().isoformat()))
                delta = (datetime.utcnow() - last_tick).total_seconds()
                
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
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        await send_telegram_alert(f"Watchdog error: {str(e)}")
        return False

async def main():
    logger.info("Starting Watchdog Service...")
    while True:
        await check_health()
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
