"""Health checks for all system components."""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class HealthResult:
    component: str
    ok: bool
    detail: str = ""


async def check_database() -> HealthResult:
    """Verify database connectivity."""
    try:
        from database.connection import get_session
        from sqlalchemy import text
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        return HealthResult("database", True, "connected")
    except Exception as e:
        return HealthResult("database", False, str(e))


async def check_broker(broker=None) -> HealthResult:
    """Verify broker is authenticated."""
    if broker is None:
        return HealthResult("broker", False, "no broker instance")
    try:
        authenticated = bool(getattr(broker, "_cst", None))
        if authenticated:
            return HealthResult("broker", True, "authenticated")
        return HealthResult("broker", False, "not authenticated")
    except Exception as e:
        return HealthResult("broker", False, str(e))


async def check_redis() -> HealthResult:
    """Verify Redis connectivity (optional)."""
    try:
        import redis.asyncio as aioredis
        import os
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        client = aioredis.from_url(redis_url, socket_connect_timeout=2)
        await client.ping()
        await client.aclose()
        return HealthResult("redis", True, "connected")
    except ImportError:
        return HealthResult("redis", True, "redis not installed, skipping")
    except Exception as e:
        return HealthResult("redis", False, str(e))


async def run_all(broker=None) -> list[HealthResult]:
    """Run all health checks and return results."""
    results = []
    results.append(await check_database())
    results.append(await check_broker(broker))
    results.append(await check_redis())
    all_ok = all(r.ok for r in results)
    status = "HEALTHY" if all_ok else "DEGRADED"
    logger.info(
        "Health check: %s | %s",
        status,
        " | ".join(f"{r.component}={'OK' if r.ok else 'FAIL: ' + r.detail}" for r in results),
    )
    return results
