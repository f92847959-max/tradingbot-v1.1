"""WhatsApp message sender via Twilio API with retry and fallback."""

import asyncio
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

FAILED_LOG_PATH = Path(__file__).parent / "failed_messages.log"


class WhatsAppSender:
    """Sends WhatsApp messages via Twilio with retry and fallback."""

    MAX_RETRIES = 3
    BACKOFF_BASE = 2.0  # seconds
    FAILURE_ALERT_THRESHOLD = 5  # alert if >5 failures per hour

    def __init__(
        self,
        account_sid: str | None = None,
        auth_token: str | None = None,
        from_number: str | None = None,
        to_number: str | None = None,
    ) -> None:
        self.account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = from_number or os.getenv("TWILIO_FROM_NUMBER", "")
        self.to_number = to_number or os.getenv("TWILIO_TO_NUMBER", "")
        self._client = None

        # Failure tracking
        self._failure_timestamps: list[float] = []

    def _get_client(self):
        if self._client is None:
            try:
                from twilio.rest import Client
                self._client = Client(self.account_sid, self.auth_token)
            except ImportError:
                logger.error("twilio package not installed. Run: pip install twilio")
                return None
            except Exception as e:
                logger.error("Failed to create Twilio client: %s", e)
                return None
        return self._client

    @property
    def failures_last_hour(self) -> int:
        """Count failures in the last 60 minutes."""
        now = time.monotonic()
        self._failure_timestamps = [
            t for t in self._failure_timestamps if now - t < 3600
        ]
        return len(self._failure_timestamps)

    def _record_failure(self) -> None:
        """Track a failure and alert if threshold exceeded."""
        self._failure_timestamps.append(time.monotonic())
        count = self.failures_last_hour
        if count >= self.FAILURE_ALERT_THRESHOLD:
            logger.critical(
                "NOTIFICATION ALERT: %d WhatsApp failures in the last hour "
                "(threshold: %d). Check Twilio credentials and service status.",
                count, self.FAILURE_ALERT_THRESHOLD,
            )

    def _log_to_fallback(self, message: str, error: str) -> None:
        """Write failed message to fallback log file."""
        try:
            with open(FAILED_LOG_PATH, "a", encoding="utf-8") as f:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] ERROR: {error}\n")
                f.write(f"  MESSAGE: {message}\n\n")
            logger.info("Failed message saved to %s", FAILED_LOG_PATH)
        except OSError as e:
            logger.error("Could not write to fallback log: %s", e)

    async def send(self, message: str) -> bool:
        """Send a WhatsApp message with retry and fallback (async-safe).

        Returns True if sent successfully. Uses asyncio.sleep for backoff
        so the event loop is not blocked, and offloads the blocking Twilio
        HTTP call to a worker thread.
        """
        if not self.account_sid or not self.auth_token:
            logger.debug("Twilio not configured, skipping WhatsApp message")
            return False

        client = self._get_client()
        if client is None:
            self._record_failure()
            self._log_to_fallback(message, "Twilio client unavailable")
            return False

        last_error = ""
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                msg = await asyncio.to_thread(
                    client.messages.create,
                    body=message,
                    from_=self.from_number,
                    to=self.to_number,
                )
                logger.info("WhatsApp sent: sid=%s", msg.sid)
                return True
            except Exception as e:
                last_error = str(e)
                if attempt < self.MAX_RETRIES:
                    wait = self.BACKOFF_BASE ** attempt
                    logger.warning(
                        "WhatsApp send attempt %d/%d failed: %s. Retrying in %.1fs...",
                        attempt, self.MAX_RETRIES, e, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "WhatsApp send failed after %d attempts: %s",
                        self.MAX_RETRIES, e,
                    )

        # All retries exhausted -- fallback
        self._record_failure()
        self._log_to_fallback(message, last_error)
        return False
