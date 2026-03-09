"""WhatsApp-based trade confirmation for semi-automatic mode.

Flow:
1. Bot generates a trade signal
2. Signal details sent to user via WhatsApp
3. User replies YES/NO within timeout
4. YES -> trade executes, NO/timeout -> signal skipped
"""

import asyncio
import logging
from typing import Any

from shared.constants import CONFIRMATION_APPROVE_KEYWORDS, CONFIRMATION_REJECT_KEYWORDS

logger = logging.getLogger(__name__)


class ConfirmationHandler:
    """Manages the WhatsApp trade confirmation workflow."""

    def __init__(
        self,
        notification_manager: Any,
        timeout_seconds: int = 120,
    ) -> None:
        self._notifier = notification_manager
        self._timeout = timeout_seconds
        self._pending: dict | None = None
        self._pending_event: asyncio.Event | None = None
        self._response: str | None = None
        self._lock = asyncio.Lock()

    async def request_confirmation(self, signal: dict) -> tuple[bool, str]:
        """Send signal to user and wait for YES/NO response.

        Returns:
            Tuple of (approved: bool, reason: str)
        """
        async with self._lock:
            self._pending = signal
            self._pending_event = asyncio.Event()
            self._response = None

        # Build and send confirmation message
        msg = self._build_confirmation_message(signal)
        try:
            self._notifier.send_raw_message(msg)
        except Exception as e:
            logger.error("Failed to send confirmation WhatsApp: %s", e)
            async with self._lock:
                self._pending = None
            return False, f"WhatsApp send failed: {e}"

        # Wait for response or timeout
        try:
            await asyncio.wait_for(
                self._pending_event.wait(),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            async with self._lock:
                self._pending = None
            logger.info("Confirmation timed out after %ds", self._timeout)
            return False, f"Timeout nach {self._timeout}s"

        # Process response
        async with self._lock:
            response = self._response
            self._pending = None

        if response and response.strip().upper() in CONFIRMATION_APPROVE_KEYWORDS:
            return True, "User hat per WhatsApp bestaetigt"
        return False, f"User hat abgelehnt (Antwort: {response})"

    async def handle_incoming_message(self, message_body: str) -> str:
        """Handle an incoming WhatsApp message (webhook callback).

        Returns reply message to send back.
        """
        async with self._lock:
            if self._pending is None:
                return "Kein Signal ausstehend. Bot laeuft im Auto-Modus."

            self._response = message_body.strip()
            if self._pending_event:
                self._pending_event.set()

        upper = message_body.strip().upper()
        if upper in CONFIRMATION_APPROVE_KEYWORDS:
            return "Signal BESTAETIGT. Trade wird ausgefuehrt..."
        if upper in CONFIRMATION_REJECT_KEYWORDS:
            return "Signal ABGELEHNT. Trade wird uebersprungen."
        return f"Unbekannte Antwort: '{message_body}'. Sende JA oder NEIN."

    @property
    def has_pending(self) -> bool:
        return self._pending is not None

    def _build_confirmation_message(self, signal: dict) -> str:
        """Build WhatsApp confirmation message from signal data."""
        direction = signal.get("action", "?")
        price = signal.get("entry_price", 0)
        sl = signal.get("stop_loss", 0)
        tp = signal.get("take_profit", 0)
        confidence = signal.get("confidence", 0)
        score = signal.get("trade_score", 0)
        reasoning = signal.get("reasoning", [])

        # Format reasoning (can be list or dict)
        if isinstance(reasoning, list):
            reasons_text = "\n".join(f"  - {r}" for r in reasoning[:3])
        elif isinstance(reasoning, dict):
            reasons_text = "\n".join(f"  - {k}: {v}" for k, v in list(reasoning.items())[:3])
        else:
            reasons_text = str(reasoning)

        return (
            f"SIGNAL WARTET AUF BESTAETIGUNG\n"
            f"\n"
            f"{direction} GOLD @ ${price:.2f}\n"
            f"SL: ${sl:.2f} | TP: ${tp:.2f}\n"
            f"Konfidenz: {confidence * 100:.0f}% | Score: {score}\n"
            f"\n"
            f"Gruende:\n{reasons_text}\n"
            f"\n"
            f"Antworte JA zum Ausfuehren, NEIN zum Ueberspringen\n"
            f"(Laeuft in {self._timeout}s ab)"
        )
