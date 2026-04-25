"""Tests for the WhatsApp confirmation handler (semi-auto mode)."""

import asyncio
import pytest
from unittest.mock import MagicMock

from notifications.confirmation_handler import ConfirmationHandler


@pytest.fixture
def mock_notifier():
    notifier = MagicMock()
    notifier.send_raw_message = MagicMock(return_value=True)
    return notifier


@pytest.fixture
def handler(mock_notifier):
    return ConfirmationHandler(
        notification_manager=mock_notifier,
        timeout_seconds=2,  # Short timeout for tests
    )


@pytest.fixture
def sample_signal():
    return {
        "action": "BUY",
        "confidence": 0.78,
        "entry_price": 2045.50,
        "stop_loss": 2042.00,
        "take_profit": 2052.00,
        "trade_score": 72,
        "reasoning": ["EMA Trend aufwaerts", "RSI bei 42"],
    }


class TestConfirmationHandler:

    @pytest.mark.asyncio
    async def test_yes_response_approves_trade(self, handler, sample_signal):
        """User replying YES should approve the trade."""

        async def simulate_yes():
            await asyncio.sleep(0.1)
            await handler.handle_incoming_message("YES")

        asyncio.create_task(simulate_yes())
        approved, reason = await handler.request_confirmation(sample_signal)

        assert approved is True
        assert "bestaetigt" in reason.lower() or "approved" in reason.lower()

    @pytest.mark.asyncio
    async def test_ja_response_approves_trade(self, handler, sample_signal):
        """German 'JA' should also approve."""

        async def simulate_ja():
            await asyncio.sleep(0.1)
            await handler.handle_incoming_message("JA")

        asyncio.create_task(simulate_ja())
        approved, reason = await handler.request_confirmation(sample_signal)

        assert approved is True

    @pytest.mark.asyncio
    async def test_no_response_rejects_trade(self, handler, sample_signal):
        """User replying NO should reject the trade."""

        async def simulate_no():
            await asyncio.sleep(0.1)
            await handler.handle_incoming_message("NEIN")

        asyncio.create_task(simulate_no())
        approved, reason = await handler.request_confirmation(sample_signal)

        assert approved is False
        assert "abgelehnt" in reason.lower() or "rejected" in reason.lower()

    @pytest.mark.asyncio
    async def test_timeout_rejects_trade(self, handler, sample_signal):
        """No response within timeout should reject."""
        approved, reason = await handler.request_confirmation(sample_signal)

        assert approved is False
        assert "timeout" in reason.lower()

    @pytest.mark.asyncio
    async def test_sends_whatsapp_message(self, handler, mock_notifier, sample_signal):
        """Should send a WhatsApp message with signal details."""
        # Will timeout but should still send the message
        await handler.request_confirmation(sample_signal)

        mock_notifier.send_raw_message.assert_called_once()
        msg = mock_notifier.send_raw_message.call_args[0][0]
        assert "BUY" in msg
        assert "2045" in msg

    @pytest.mark.asyncio
    async def test_no_pending_returns_info_message(self, handler):
        """When no signal is pending, incoming message should inform user."""
        reply = await handler.handle_incoming_message("YES")
        assert "kein" in reply.lower() or "auto" in reply.lower()

    def test_has_pending_initially_false(self, handler):
        assert handler.has_pending is False

    def test_build_confirmation_message(self, handler, sample_signal):
        msg = handler._build_confirmation_message(sample_signal)
        assert "BUY" in msg
        assert "2045.50" in msg
        assert "2042.00" in msg
        assert "2052.00" in msg
        assert "78%" in msg
        assert "JA" in msg
        assert "NEIN" in msg
