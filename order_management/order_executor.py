"""Order executor — sends orders to Capital.com and processes confirmations."""

import asyncio
import logging
import uuid
from collections import OrderedDict

from market_data.broker_client import (
    CapitalComClient,
    OrderResult,
    OrderRejectedError,
)

logger = logging.getLogger(__name__)


class OrderExecutor:
    """Handles order submission and confirmation with Capital.com."""

    # Max number of idempotency keys to retain in the in-memory cache
    _MAX_IDEMPOTENCY_CACHE: int = 512

    def __init__(self, broker_client: CapitalComClient) -> None:
        self.client = broker_client
        # Idempotency cache: client_order_id -> OrderResult
        # Used to short-circuit retries of the same logical order so we
        # never submit duplicate market orders to the broker.
        self._idempotency_cache: "OrderedDict[str, OrderResult]" = OrderedDict()
        self._idempotency_inflight: dict[str, asyncio.Lock] = {}
        self._idempotency_guard = asyncio.Lock()

    @staticmethod
    def generate_client_order_id() -> str:
        """Generate a fresh idempotency key for a new logical order."""
        return f"coid-{uuid.uuid4().hex}"

    def _remember_result(self, client_order_id: str, result: OrderResult) -> None:
        self._idempotency_cache[client_order_id] = result
        self._idempotency_cache.move_to_end(client_order_id)
        while len(self._idempotency_cache) > self._MAX_IDEMPOTENCY_CACHE:
            self._idempotency_cache.popitem(last=False)

    async def execute_market_order(
        self,
        direction: str,
        size: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        client_order_id: str | None = None,
    ) -> OrderResult:
        """Submit a market order and wait for confirmation.

        Args:
            direction: BUY or SELL
            size: Lot size
            stop_loss: Stop loss price level
            take_profit: Take profit price level
            client_order_id: Idempotency key. When the same key is passed on a
                retry, the cached OrderResult from the first successful
                submission is returned instead of sending a duplicate order.
                If None, a fresh key is generated (no idempotency guarantee
                across retries from the caller).

        Returns:
            OrderResult with deal_id, status, level

        Raises:
            OrderRejectedError: If the order was rejected by the broker
            BrokerError: For other API errors
        """
        if client_order_id is None:
            client_order_id = self.generate_client_order_id()

        # Fast path: key already completed successfully → return cached result
        cached = self._idempotency_cache.get(client_order_id)
        if cached is not None:
            logger.warning(
                "Idempotent replay for client_order_id=%s — returning cached deal_id=%s",
                client_order_id, cached.deal_id,
            )
            self._idempotency_cache.move_to_end(client_order_id)
            return cached

        # Serialize concurrent submissions that share the same key
        async with self._idempotency_guard:
            inflight = self._idempotency_inflight.get(client_order_id)
            if inflight is None:
                inflight = asyncio.Lock()
                self._idempotency_inflight[client_order_id] = inflight

        async with inflight:
            cached = self._idempotency_cache.get(client_order_id)
            if cached is not None:
                self._idempotency_inflight.pop(client_order_id, None)
                return cached

            logger.info(
                "Submitting %s order: size=%.2f, SL=%s, TP=%s, coid=%s",
                direction, size,
                f"{stop_loss:.2f}" if stop_loss else "none",
                f"{take_profit:.2f}" if take_profit else "none",
                client_order_id,
            )

            try:
                result = await self.client.open_position(
                    direction=direction,
                    size=size,
                    stop_level=stop_loss,
                    limit_level=take_profit,
                )
            finally:
                # Only drop the inflight lock; do not cache failures so the
                # caller can safely retry with the same key.
                pass

            if result.status == "REJECTED":
                self._idempotency_inflight.pop(client_order_id, None)
                raise OrderRejectedError(
                    reason=result.reason,
                    deal_reference=result.deal_reference,
                )

            self._remember_result(client_order_id, result)
            self._idempotency_inflight.pop(client_order_id, None)

            logger.info(
                "Order confirmed: deal_id=%s, status=%s, level=%.2f, coid=%s",
                result.deal_id, result.status, result.level, client_order_id,
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
