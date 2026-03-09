"""Order Manager — orchestrates the full trade lifecycle."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from market_data.broker_client import CapitalComClient, Position, BrokerError
from database.connection import get_session
from database.repositories.trade_repo import TradeRepository, OrderLogRepository
from database.models import Trade, OrderLog
from shared.constants import TradeStatus

from .order_executor import OrderExecutor
from .position_monitor import PositionMonitor
from .trailing_stop import TrailingStopManager

logger = logging.getLogger(__name__)


class OrderManager:
    """Orchestrates the complete trade lifecycle:

    1. Open trade (via OrderExecutor)
    2. Track in DB
    3. Monitor positions (detect TP/SL hits)
    4. Manage trailing stops
    5. Close trades (manual or kill switch)
    """

    def __init__(
        self,
        broker_client: CapitalComClient,
        trailing_activation_pips: float = 10.0,
        trailing_distance_pips: float = 5.0,
    ) -> None:
        self.executor = OrderExecutor(broker_client)
        self.monitor = PositionMonitor(broker_client)
        self.trailing = TrailingStopManager(
            activation_pips=trailing_activation_pips,
            trail_distance_pips=trailing_distance_pips,
        )
        self.client = broker_client
        self._order_lock = asyncio.Lock()

    # Timeout for acquiring the order lock (seconds)
    LOCK_TIMEOUT: float = 10.0

    async def open_trade(
        self,
        direction: str,
        lot_size: float,
        stop_loss: float,
        take_profit: float,
        entry_price: float = 0.0,
        ai_confidence: float = 0.0,
        trade_score: int = 0,
        timeframe: str = "",
        reasoning: dict | None = None,
    ) -> Trade | None:
        """Execute a new trade and persist it.

        Returns Trade object if successful, None if failed.
        Uses async lock with timeout to prevent duplicate orders from concurrent
        ticks while avoiding deadlocks.
        """
        try:
            await asyncio.wait_for(self._order_lock.acquire(), timeout=self.LOCK_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(
                "Order lock timeout after %.1fs — trade aborted (another order in progress)",
                self.LOCK_TIMEOUT,
            )
            return None

        try:
            return await self._execute_trade(
                direction=direction,
                lot_size=lot_size,
                stop_loss=stop_loss,
                take_profit=take_profit,
                entry_price=entry_price,
                ai_confidence=ai_confidence,
                trade_score=trade_score,
                timeframe=timeframe,
                reasoning=reasoning,
            )
        finally:
            self._order_lock.release()

    async def _execute_trade(
        self,
        direction: str,
        lot_size: float,
        stop_loss: float,
        take_profit: float,
        entry_price: float = 0.0,
        ai_confidence: float = 0.0,
        trade_score: int = 0,
        timeframe: str = "",
        reasoning: dict | None = None,
    ) -> Trade | None:
        """Internal: execute trade under lock."""
        try:
            # Submit order
            result = await self.executor.execute_market_order(
                direction=direction,
                size=lot_size,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

            if result.status not in ("ACCEPTED", "OPEN", TradeStatus.OPEN):
                logger.warning("Order not accepted: status=%s, reason=%s",
                              result.status, result.reason)
                return None

            # Validate fill price
            if result.level is None or result.level <= 0:
                logger.warning(
                    "Broker returned invalid fill level: %s for deal %s",
                    result.level, result.deal_id,
                )

            # Calculate slippage against expected entry price
            expected = entry_price if entry_price > 0 else result.level
            try:
                slippage = await self.executor.measure_slippage(
                    expected_price=expected,
                    actual_price=result.level,
                    direction=direction,
                )
            except Exception as slip_err:
                logger.warning(
                    "Slippage measurement failed: %s — using default 0.30",
                    slip_err,
                )
                slippage = 0.30  # Default estimate for Gold

            # Get current spread
            spread = 0.0
            try:
                price = await self.client.get_current_price()
                spread = abs(price.get("ask", 0) - price.get("bid", 0))
            except BrokerError as e:
                logger.warning("Could not fetch spread at entry: %s", e)

            # Persist to database
            trade = Trade(
                deal_id=result.deal_id,
                opened_at=datetime.now(timezone.utc),
                direction=direction,
                entry_price=result.level,
                stop_loss=stop_loss,
                take_profit=take_profit,
                lot_size=lot_size,
                spread_at_entry=spread,
                slippage=slippage,
                ai_confidence=ai_confidence,
                trade_score=trade_score,
                timeframe=timeframe,
                reasoning=reasoning,
                status=TradeStatus.OPEN,
            )

            try:
                async with get_session() as session:
                    repo = TradeRepository(session)
                    trade = await repo.add(trade)

                    log_repo = OrderLogRepository(session)
                    await log_repo.log_action(
                        action="FILLED",
                        deal_id=result.deal_id,
                        details={
                            "direction": direction,
                            "size": lot_size,
                            "level": result.level,
                            "sl": stop_loss,
                            "tp": take_profit,
                        },
                    )
            except Exception as db_err:
                # CRITICAL: Broker order succeeded but DB insert failed.
                # The position is OPEN at the broker but not tracked in DB.
                logger.critical(
                    "ORPHANED TRADE: Broker order %s succeeded but DB insert failed: %s. "
                    "Position is OPEN at broker but NOT in database!",
                    result.deal_id, db_err,
                )
                # Try to save a minimal record so we can reconcile later
                try:
                    async with get_session() as session:
                        orphan = Trade(
                            deal_id=result.deal_id,
                            opened_at=datetime.now(timezone.utc),
                            direction=direction,
                            entry_price=result.level,
                            lot_size=lot_size,
                            stop_loss=stop_loss,
                            take_profit=take_profit,
                            status=TradeStatus.ORPHANED,
                        )
                        session.add(orphan)
                except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
                    raise
                except Exception:
                    logger.critical(
                        "Could not even save ORPHANED record for deal %s",
                        result.deal_id,
                    )

            # Track in position monitor (even if DB failed — broker has the position)
            pos = Position(
                deal_id=result.deal_id,
                direction=direction,
                size=lot_size,
                open_level=result.level,
                current_level=result.level,
                stop_level=stop_loss,
                limit_level=take_profit,
            )
            self.monitor.track_position(result.deal_id, pos)

            logger.info(
                "Trade opened: deal=%s, %s @ %.2f, lot=%.2f, SL=%.2f, TP=%.2f",
                result.deal_id, direction, result.level, lot_size, stop_loss, take_profit,
            )
            return trade

        except BrokerError as e:
            logger.error("Failed to open trade: %s", e)
            try:
                async with get_session() as session:
                    log_repo = OrderLogRepository(session)
                    await log_repo.log_action(
                        action="REJECTED",
                        details={"direction": direction, "size": lot_size, "error": str(e)},
                    )
            except Exception as log_err:
                logger.error("Failed to log rejected order: %s", log_err)
            return None

    async def close_trade(self, deal_id: str, reason: str = "MANUAL") -> bool:
        """Close a specific trade by deal_id.

        Uses a two-phase approach:
        1. Mark trade as CLOSING in DB
        2. Close at broker
        3. Mark as CLOSED with P&L (or CLOSE_FAILED on error)
        """
        # Phase 1: Mark as CLOSING in DB
        try:
            async with get_session() as session:
                repo = TradeRepository(session)
                trade = await repo.get_by_deal_id(deal_id)
                if trade and trade.status in ("OPEN", TradeStatus.OPEN):
                    from sqlalchemy import update as sql_update
                    from database.models import Trade as TradeModel
                    stmt = (
                        sql_update(TradeModel)
                        .where(TradeModel.id == trade.id)
                        .values(status=TradeStatus.CLOSING)
                    )
                    await session.execute(stmt)
        except Exception as e:
            logger.error("Failed to mark trade %s as CLOSING: %s", deal_id, e)
            # Continue anyway — try to close at broker

        # Phase 2: Close at broker
        try:
            result = await self.executor.close_position(deal_id)
        except BrokerError as e:
            logger.error("Failed to close trade %s at broker: %s", deal_id, e)
            # Mark as CLOSE_FAILED in DB
            try:
                async with get_session() as session:
                    repo = TradeRepository(session)
                    trade = await repo.get_by_deal_id(deal_id)
                    if trade:
                        from sqlalchemy import update as sql_update
                        from database.models import Trade as TradeModel
                        stmt = (
                            sql_update(TradeModel)
                            .where(TradeModel.id == trade.id)
                            .values(status=TradeStatus.CLOSE_FAILED, close_reason=f"BROKER_ERROR: {e}")
                        )
                        await session.execute(stmt)
            except Exception as db_err:
                logger.error("Failed to mark trade %s as CLOSE_FAILED: %s", deal_id, db_err)
            return False

        # Phase 3: Update DB with final status and P&L
        try:
            async with get_session() as session:
                repo = TradeRepository(session)
                trade = await repo.get_by_deal_id(deal_id)
                if trade:
                    exit_price = result.level if result.level is not None and result.level > 0 else 0
                    pnl = self._calc_pnl(trade, exit_price)
                    await repo.close_trade(
                        trade_id=trade.id,
                        exit_price=exit_price,
                        pnl_pips=pnl["pips"],
                        pnl_euros=pnl["euros"],
                        net_pnl=pnl["net"],
                        close_reason=reason,
                    )
                    log_repo = OrderLogRepository(session)
                    await log_repo.log_action(
                        action="CLOSED",
                        deal_id=deal_id,
                        details={"reason": reason, "pnl": pnl},
                    )
        except Exception as db_err:
            logger.critical(
                "Trade %s closed at broker but DB update failed: %s. "
                "Position is CLOSED at broker but may show CLOSING in DB.",
                deal_id, db_err,
            )

        self.trailing.remove_tracking(deal_id)
        self.monitor.untrack_position(deal_id)
        logger.info("Trade closed: deal=%s, reason=%s", deal_id, reason)
        return True

    async def close_all(self) -> int:
        """Emergency close all positions (kill switch). Returns count closed."""
        results = await self.executor.close_all()
        count = sum(1 for r in results if r.status != "REJECTED")
        logger.critical("Kill switch: closed %d/%d positions", count, len(results))

        # Persist closed status to DB for each successfully closed position
        for r in results:
            if r.status == "REJECTED" or not r.deal_id:
                continue
            try:
                async with get_session() as session:
                    repo = TradeRepository(session)
                    trade = await repo.get_by_deal_id(r.deal_id)
                    if trade and trade.status in ("OPEN", "CLOSING", TradeStatus.OPEN, TradeStatus.CLOSING):
                        exit_price = r.level if r.level is not None and r.level > 0 else 0
                        pnl = self._calc_pnl(trade, exit_price) if exit_price > 0 else {"pips": 0.0, "euros": 0.0, "net": 0.0}
                        await repo.close_trade(
                            trade_id=trade.id,
                            exit_price=exit_price,
                            pnl_pips=pnl["pips"],
                            pnl_euros=pnl["euros"],
                            net_pnl=pnl["net"],
                            close_reason="KILL_SWITCH",
                        )
            except Exception as db_err:
                logger.error("Failed to update DB for kill-switch close %s: %s", r.deal_id, db_err)

            self.trailing.remove_tracking(r.deal_id)
            self.monitor.untrack_position(r.deal_id)

        return count

    async def check_positions(self) -> dict:
        """Check position status and handle trailing stops.

        Call this every 30 seconds from the main loop.
        """
        # Check for closed positions
        status = await self.monitor.check()

        # Update trailing stops for open positions
        for deal_id, pos in self.monitor.get_open_positions().items():
            new_sl = self.trailing.calculate_new_sl(pos, pos.current_level)
            if new_sl is not None:
                try:
                    await self.executor.modify_position(deal_id, stop_loss=new_sl)
                except BrokerError as e:
                    logger.error("Failed to update trailing SL for %s: %s", deal_id, e)

        return status

    def _calc_pnl(self, trade: Trade, exit_price: float) -> dict:
        """Calculate P&L for a closed trade."""
        if exit_price <= 0 or trade.entry_price is None:
            return {"pips": 0.0, "euros": 0.0, "net": 0.0}

        entry = float(trade.entry_price)
        lot = float(trade.lot_size) if trade.lot_size is not None else 0.0
        from config.settings import get_settings
        pip_size = get_settings().instrument.pip_size

        if trade.direction == "BUY":
            pips = (exit_price - entry) / pip_size
        else:
            pips = (entry - exit_price) / pip_size

        # For Gold CFD: 1 lot = 1 Troy Ounce
        # P&L = price_movement_in_usd * lot_size
        price_diff = abs(exit_price - entry) if pips >= 0 else -abs(exit_price - entry)
        if trade.direction == "BUY":
            price_diff = exit_price - entry
        else:
            price_diff = entry - exit_price
        euros = price_diff * lot

        spread_cost = float(trade.spread_at_entry or 0) * lot
        net = euros - spread_cost

        return {"pips": round(pips, 2), "euros": round(euros, 2), "net": round(net, 2)}

    @property
    def position_monitor(self) -> PositionMonitor:
        """Access the position monitor (for startup recovery etc.)."""
        return self.monitor

    def get_open_count(self) -> int:
        return self.monitor.get_open_count()

    def has_position_in_direction(self, direction: str) -> bool:
        return self.monitor.has_position_in_direction(direction)
