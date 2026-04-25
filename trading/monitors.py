"""Monitor mixin -- daily cleanup, position monitoring, close handling."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from database.connection import get_session
from database.repositories.candle_repo import CandleRepository
from database.repositories.trade_repo import TradeRepository
from market_data.broker_client import BrokerError

if TYPE_CHECKING:
    from main import TradingSystem

logger = logging.getLogger("main")


class MonitorMixin:
    """Daily cleanup loop, position monitor loop, and close handling."""

    async def _daily_cleanup_loop(self: TradingSystem) -> None:
        """Run DB cleanup once per day at midnight UTC."""
        _last_cleanup_date = None

        while self._running:
            try:
                now_utc = datetime.now(timezone.utc)
                today = now_utc.date()

                if _last_cleanup_date != today and now_utc.hour == 0:
                    logger.info("Running daily DB cleanup...")
                    try:
                        async with get_session() as session:
                            candle_repo = CandleRepository(session)
                            deleted = await candle_repo.delete_older_than(days=30)
                            if deleted:
                                logger.info("Cleanup: removed %d old candles", deleted)
                        _last_cleanup_date = today
                    except Exception as e:
                        logger.error("Daily cleanup failed: %s", e)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Error in cleanup loop: %s", e)

            await asyncio.sleep(300)  # Check every 5 minutes

    async def _position_monitor_loop(self: TradingSystem) -> None:
        """Monitor open positions every 30 seconds."""
        while self._running:
            try:
                if self.orders.get_open_count() > 0:
                    status = await asyncio.wait_for(
                        self.orders.check_positions(), timeout=30,
                    )

                    for deal_id in status.get("newly_closed", []):
                        await self._handle_position_closed(deal_id)

            except asyncio.CancelledError:
                raise
            except BrokerError as e:
                logger.error("Broker error in position monitor: %s", e)
            except Exception as e:
                logger.error(
                    "Unexpected error in position monitor: %s", e, exc_info=True,
                )

            await asyncio.sleep(self.settings.position_check_seconds)

    async def _handle_position_closed(self: TradingSystem, deal_id: str) -> None:
        """Handle a position that was closed (TP/SL/trailing hit)."""
        pnl = 0.0
        async with get_session() as session:
            repo = TradeRepository(session)
            trade = await repo.get_by_deal_id(deal_id)
            if trade is None:
                logger.warning(
                    "Untracked position closed at broker (deal_id=%s) -- "
                    "no DB record; skipping heat release/notify (never tracked).",
                    deal_id,
                )
                return

            pnl = float(trade.net_pnl) if trade.net_pnl is not None else 0.0

            # Update risk metrics cache
            await self.risk.metrics_cache.on_trade_closed(pnl)

            if pnl < 0:
                self.risk.record_loss()

            # Phase 9: release portfolio heat + update equity curve filter
            try:
                sl = float(trade.stop_loss) if trade.stop_loss is not None else 0.0
                entry = float(trade.entry_price) if trade.entry_price is not None else 0.0
                lot = float(trade.lot_size) if trade.lot_size is not None else 0.0
                risk_amount = abs(entry - sl) * lot
                account = await asyncio.wait_for(self.broker.get_account(), timeout=15)
                self.risk.on_position_closed(risk_amount, account.balance, account.balance)
            except Exception:
                logger.exception("on_position_closed update failed")

            reason = trade.close_reason or "unknown"
            duration_min = 0
            if trade.opened_at and trade.closed_at:
                duration_min = int((trade.closed_at - trade.opened_at).total_seconds() / 60)

            await self.notifications.notify_trade_closed(
                direction=trade.direction,
                entry=float(trade.entry_price),
                exit_price=float(trade.exit_price) if trade.exit_price else 0.0,
                pnl=pnl,
                reason=reason,
                duration_min=duration_min,
            )

        logger.info("Position closed: %s (P&L: %.2f)", deal_id, pnl)
