"""Notification Manager — dispatches alerts via WhatsApp."""

import logging
from datetime import datetime

from . import message_templates as tpl
from .whatsapp_sender import WhatsAppSender

logger = logging.getLogger(__name__)


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

    def _send(self, message: str, msg_type: str) -> bool:
        """Send message and log result."""
        if not self.enabled:
            logger.debug("Notifications disabled, skipping: %s", msg_type)
            return False

        success = self._sender.send(message)
        self._send_count += 1

        # Log to DB (async version would use get_session)
        self._log_notification(msg_type, message[:100], success)
        return success

    def notify_trade_opened(
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
        return self._send(msg, "TRADE_OPEN")

    def notify_trade_closed(
        self,
        direction: str,
        entry: float,
        exit_price: float,
        pnl: float,
        reason: str,
        duration_min: int = 0,
    ) -> bool:
        msg = tpl.trade_closed(direction, entry, exit_price, pnl, reason, duration_min)
        return self._send(msg, "TRADE_CLOSE")

    def notify_kill_switch(
        self,
        reason: str,
        drawdown_pct: float,
        positions_closed: int,
    ) -> bool:
        msg = tpl.kill_switch_activated(reason, drawdown_pct, positions_closed)
        return self._send(msg, "KILL_SWITCH")

    def notify_daily_summary(
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
        return self._send(msg, "DAILY")

    def notify_warning(self, message: str) -> bool:
        msg = tpl.system_warning(message)
        return self._send(msg, "WARNING")

    def send_raw_message(self, message: str) -> bool:
        """Send a raw message (used by ConfirmationHandler)."""
        return self._send(message, "CONFIRMATION")

    def _log_notification(self, msg_type: str, preview: str, success: bool) -> None:
        """Log notification to database (sync fallback — async in Phase 2)."""
        try:
            # Phase 2: Use async DB session to persist NotificationLog
            status = "SENT" if success else "FAILED"
            logger.debug("Notification logged: type=%s, status=%s", msg_type, status)
        except Exception as e:
            logger.error("Failed to log notification: %s", e)
