import time
import requests
import redis
import os
import logging

# Configuration
BROKER_API_URL = "https://api-capital.backend-capital.com" # Or relevant demo/live endpoint
MAX_LATENCY_MS = int(os.getenv("MAX_LATENCY_MS", 100))
CHECK_INTERVAL = 5  # seconds
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - LATENCY - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def check_latency():
    try:
        start_time = time.time()
        # Simple HEAD request to check round-trip time
        response = requests.head(BROKER_API_URL, timeout=2.0)
        latency_ms = (time.time() - start_time) * 1000
        
        if response.status_code == 200:
            return latency_ms
        else:
            logger.warning(f"Broker returned status {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Latency check failed: {e}")
        return None

def main():
    logger.info("Starting Latency Monitor...")
    r = redis.from_url(REDIS_URL)
    
    while True:
        latency = check_latency()
        
        if latency is None:
             # Connection lost - Pause Trading
            r.set("TRADING_PAUSED", "TRUE", ex=60) # Auto-expire if monitor dies
            logger.critical("Connection lost! Trading PAUSED.")
        
        elif latency > MAX_LATENCY_MS:
            # Latency too high - Pause Trading
            r.set("TRADING_PAUSED", "TRUE", ex=60)
            logger.warning(f"High Latency: {latency:.2f}ms > {MAX_LATENCY_MS}ms. Trading PAUSED.")
        
        else:
            # Latency OK - Resume Trading
            if r.get("TRADING_PAUSED"):
                logger.info(f"Latency OK: {latency:.2f}ms. Resuming trading.")
                r.delete("TRADING_PAUSED")
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
