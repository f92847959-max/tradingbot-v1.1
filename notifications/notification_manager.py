"""Notification Manager -- dispatches alerts via WhatsApp.

Includes:
- Per-type rate limiting (rolling window)
- Short-window deduplication (drop identical messages within 60s)
- Async-safe send pipeline (does not block the event loop)
"""

import hashlib
import logging
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

from . import message_templates as tpl
from .whatsapp_sender import WhatsAppSender

logger = logging.getLogger(__name__)


# (max_messages, window_seconds). None == unlimited.
DEFAULT_RATE_LIMITS: Dict[str, Tuple[int, int] | None] = {
    "TRADE_OPEN": (30, 3600),
    "TRADE_CLOSE": (30, 3600),
    "WARNING": (12, 3600),
    "DAILY": (5, 3600),
    "CONFIRMATION": (60, 3600),
    "KILL_SWITCH": None,  # never throttled -- safety critical
}

# Drop identical (msg_type, message) pairs sent within this many seconds
DEDUP_WINDOW_SECONDS = 60


class RateLimiter:
    """Sliding-window rate limiter with per-type buckets and dedup.

    Not thread-safe. Intended for single-event-loop use.
    """

    def __init__(
        self,
        limits: Dict[str, Tuple[int, int] | None] | None = None,
        dedup_window: int = DEDUP_WINDOW_SECONDS,
    ) -> None:
        self._limits = limits if limits is not None else DEFAULT_RATE_LIMITS
        self._dedup_window = dedup_window
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)
        # key -> last sent monotonic timestamp
        self._dedup: Dict[str, float] = {}

    def _key(self, msg_type: str, message: str) -> str:
        digest = hashlib.sha1(message.encode("utf-8", errors="replace")).hexdigest()
        return f"{msg_type}:{digest}"

    def _purge_dedup(self, now: float) -> None:
        if not self._dedup:
            return
        cutoff = now - self._dedup_window
        stale = [k for k, ts in self._dedup.items() if ts < cutoff]
        for k in stale:
            del self._dedup[k]

    def allow(self, msg_type: str, message: str) -> Tuple[bool, str]:
        """Return (allowed, reason). reason is empty if allowed."""
        now = time.monotonic()

        # Dedup check
        self._purge_dedup(now)
        key = self._key(msg_type, message)
        last_seen = self._dedup.get(key)
        if last_seen is not None and (now - last_seen) < self._dedup_window:
            return False, f"duplicate within {self._dedup_window}s"

        # Rate limit check
        limit = self._limits.get(msg_type)
        if limit is not None:
            max_count, window = limit
            bucket = self._buckets[msg_type]
            cutoff = now - window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= max_count:
                return False, f"rate-limited ({max_count}/{window}s)"
            bucket.append(now)

        self._dedup[key] = now
        return True, ""


class NotificationManager:
    """Central notification dispatcher.

    Sends WhatsApp alerts for:
    - Trade opened/closed
    - Kill switch activation
    - Daily summary
    - System warnings
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._sender = WhatsAppSender()
        self._send_count = 0
        self._dropped_count = 0
        self._rate_limiter = RateLimiter()

    async def _send(self, message: str, msg_type: str) -> bool:
        """Send message and log result. Honors rate-limits and dedup."""
        if not self.enabled:
            logger.debug("Notifications disabled, skipping: %s", msg_type)
            return False

        allowed, reason = self._rate_limiter.allow(msg_type, message)
        if not allowed:
            self._dropped_count += 1
            logger.info(
                "Notification dropped (%s): type=%s reason=%s",
                self._dropped_count, msg_type, reason,
            )
            return False

        success = await self._sender.send(message)
        self._send_count += 1

        # Log to DB (async version would use get_session)
        self._log_notification(msg_type, message[:100], success)
        return success

    async def notify_trade_opened(
        self,
        direction: str,
        price: float,
        lot_size: float,
        stop_loss: float,
        take_profit: float,
        score: int = 0,
        confidence: float = 0.0,
    ) -> bool:
        msg = tpl.trade_opened(direction, price, lot_size, stop_loss, take_profit, score, confidence)
        return await self._send(msg, "TRADE_OPEN")

    async def notify_trade_closed(
        self,
        direction: str,
        entry: float,
        exit_price: float,
        pnl: float,
        reason: str,
        duration_min: int = 0,
    ) -> bool:
        msg = tpl.trade_closed(direction, entry, exit_price, pnl, reason, duration_min)
        return await self._send(msg, "TRADE_CLOSE")

    async def notify_kill_switch(
        self,
        reason: str,
        drawdown_pct: float,
        positions_closed: int,
    ) -> bool:
        msg = tpl.kill_switch_activated(reason, drawdown_pct, positions_closed)
        return await self._send(msg, "KILL_SWITCH")

    async def notify_daily_summary(
        self,
        date: str,
        trades_total: int,
        trades_won: int,
        trades_lost: int,
        net_pnl: float,
        win_rate: float,
        equity: float,
    ) -> bool:
        msg = tpl.daily_summary(date, trades_total, trades_won, trades_lost, net_pnl, win_rate, equity)
        return await self._send(msg, "DAILY")

    async def notify_warning(self, message: str) -> bool:
        msg = tpl.system_warning(message)
        return await self._send(msg, "WARNING")

    async def send_raw_message(self, message: str) -> bool:
        """Send a raw message (used by ConfirmationHandler)."""
        return await self._send(message, "CONFIRMATION")

    def _log_notification(self, msg_type: str, preview: str, success: bool) -> None:
        """Log notification to database (sync fallback -- async in Phase 2)."""
        try:
            # Phase 2: Use async DB session to persist NotificationLog
            status = "SENT" if success else "FAILED"
            logger.debug("Notification logged: type=%s, status=%s", msg_type, status)
        except Exception as e:
            logger.error("Failed to log notification: %s", e)
