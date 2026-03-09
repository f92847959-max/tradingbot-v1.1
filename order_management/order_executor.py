"""Order executor — sends orders to Capital.com and processes confirmations."""

import logging
from datetime import datetime

from market_data.broker_client import (
    CapitalComClient,
    OrderResult,
    BrokerError,
    OrderRejectedError,
)

logger = logging.getLogger(__name__)


class OrderExecutor:
    """Handles order submission and confirmation with Capital.com."""

    def __init__(self, broker_client: CapitalComClient) -> None:
        self.client = broker_client

    async def execute_market_order(
        self,
        direction: str,
        size: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        """Submit a market order and wait for confirmation.

        Args:
            direction: BUY or SELL
            size: Lot size
            stop_loss: Stop loss price level
            take_profit: Take profit price level

        Returns:
            OrderResult with deal_id, status, level

        Raises:
            OrderRejectedError: If the order was rejected by the broker
            BrokerError: For other API errors
        """
        logger.info(
            "Submitting %s order: size=%.2f, SL=%s, TP=%s",
            direction, size,
            f"{stop_loss:.2f}" if stop_loss else "none",
            f"{take_profit:.2f}" if take_profit else "none",
        )

        result = await self.client.open_position(
            direction=direction,
            size=size,
            stop_level=stop_loss,
            limit_level=take_profit,
        )

        if result.status == "REJECTED":
            raise OrderRejectedError(
                reason=result.reason,
                deal_reference=result.deal_reference,
            )

        logger.info(
            "Order confirmed: deal_id=%s, status=%s, level=%.2f",
            result.deal_id, result.status, result.level,
        )
        return result

    async def close_position(self, deal_id: str) -> OrderResult:
        """Close an existing position."""
        logger.info("Closing position: deal_id=%s", deal_id)
        result = await self.client.close_position(deal_id)

        if result.status == "REJECTED":
            raise OrderRejectedError(
                reason=result.reason,
                deal_reference=result.deal_reference,
            )

        logger.info("Position closed: deal_id=%s, status=%s", deal_id, result.status)
        return result

    async def modify_position(
        self,
        deal_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        """Modify SL/TP on an existing position."""
        logger.info(
            "Modifying position %s: SL=%s, TP=%s",
            deal_id,
            f"{stop_loss:.2f}" if stop_loss else "unchanged",
            f"{take_profit:.2f}" if take_profit else "unchanged",
        )
        return await self.client.modify_position(
            deal_id=deal_id,
            stop_level=stop_loss,
            limit_level=take_profit,
        )

    async def close_all(self) -> list[OrderResult]:
        """Emergency close all positions (for kill switch)."""
        logger.critical("CLOSING ALL POSITIONS (kill switch)")
        return await self.client.close_all_positions()

    async def measure_slippage(
        self, expected_price: float, actual_price: float, direction: str
    ) -> float:
        """Calculate slippage in price units.

        Positive = unfavorable (worse than expected)
        Negative = favorable (better than expected)
        """
        if direction == "BUY":
            slippage = actual_price - expected_price
        else:
            slippage = expected_price - actual_price

        if abs(slippage) > 0.01:
            logger.info("Slippage detected: %.2f (direction=%s)", slippage, direction)
        return slippage
