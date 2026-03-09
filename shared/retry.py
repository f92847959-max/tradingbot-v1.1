"""Generic async retry utilities."""

import asyncio
import logging
from typing import Callable, TypeVar, Awaitable

T = TypeVar("T")
logger = logging.getLogger(__name__)


async def retry_async(func: Callable[[], Awaitable[T]], max_retries: int = 3, backoff_base: float = 2.0, max_backoff: float = 60.0) -> T:
    """Run an async callable with retries and exponential backoff.

    Usage:
        result = await retry_async(lambda: self.broker.get_account(), max_retries=3)
    """
    for attempt in range(max_retries):
        try:
            return await func()
        except (asyncio.TimeoutError, ConnectionError) as e:
            if attempt == max_retries - 1:
                logger.exception("Final retry failed: %s", e)
                raise
            backoff = min(backoff_base ** attempt, max_backoff)
            logger.warning("Retry attempt %d failed, sleeping %.1fs: %s", attempt + 1, backoff, e)
            await asyncio.sleep(backoff)
