"""Order Manager — orchestrates the full trade lifecycle."""

from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from market_data.broker_client import CapitalComClient, Position, BrokerError
from shared.constants import TradeStatus, PIP_SIZE

from exit_engine.partial_close import PartialCloseManager
from .order_executor import OrderExecutor
from .position_monitor import PositionMonitor
from .trailing_stop import TrailingStopManager

if TYPE_CHECKING:
    from database.models import Trade

logger = logging.getLogger(__name__)

# Number of attempts for DB writes that MUST succeed after a broker
# side-effect (open/close) has already occurred.
_DB_PERSIST_RETRIES: int = 3
_DB_PERSIST_BACKOFF_SECONDS: float = 0.5


def _get_db_dependencies():
    """Load SQLAlchemy-backed repositories only when order persistence is needed."""
    from database.connection import get_session
    from database.models import Trade
    from database.repositories.trade_repo import OrderLogRepository, TradeRepository

    return get_session, Trade, TradeRepository, OrderLogRepository


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
        exit_ai_enabled: bool = False,
        exit_ai_saved_models_dir: str = "ai_engine/saved_models",
    ) -> None:
        self.executor = OrderExecutor(broker_client)
        self.monitor = PositionMonitor(broker_client)
        self.trailing = TrailingStopManager(
            activation_pips=trailing_activation_pips,
            trail_distance_pips=trailing_distance_pips,
        )
        self.client = broker_client
        self._order_lock = asyncio.Lock()
        # Reconciliation queues for trades whose broker state has diverged
        # from the DB and must be retried by a background reconciler.
        # Each entry is a dict describing the pending operation.
        self.orphan_open_queue: list[dict[str, Any]] = []
        self.orphan_close_queue: list[dict[str, Any]] = []
        self._exit_ai_enabled = bool(exit_ai_enabled)
        self._exit_ai_saved_models_dir = exit_ai_saved_models_dir
        self._exit_ai_audit_log: list[dict[str, Any]] = []
        self._exit_ai_partial_close = PartialCloseManager()
        self._exit_ai_advisor = None
        if self._exit_ai_enabled:
            try:
                from ai_engine.prediction.exit_ai_advisor import ExitAIAdvisor

                self._exit_ai_advisor = ExitAIAdvisor(
                    saved_models_dir=exit_ai_saved_models_dir,
                    enabled=True,
                )
            except Exception as exc:
                logger.warning("Exit-AI advisor unavailable: %s", exc)
                self._exit_ai_advisor = None

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
        client_order_id: str | None = None,
    ) -> Trade | None:
        """Execute a new trade and persist it.

        Returns Trade object if successful, None if failed.
        Uses async lock with timeout to prevent duplicate orders from concurrent
        ticks while avoiding deadlocks.

        Args:
            client_order_id: Optional idempotency key. If the caller retries
                with the same key, the executor will return the cached result
                from the first submission rather than placing a duplicate
                order at the broker. If None, a fresh key is generated.
        """
        if client_order_id is None:
            client_order_id = OrderExecutor.generate_client_order_id()

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
                client_order_id=client_order_id,
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
        client_order_id: str | None = None,
    ) -> Trade | None:
        """Internal: execute trade under lock."""
        try:
            # Submit order
            result = await self.executor.execute_market_order(
                direction=direction,
                size=lot_size,
                stop_loss=stop_loss,
                take_profit=take_profit,
                client_order_id=client_order_id,
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

            # Preserve R:R after unfavorable slippage: shift SL/TP by fill gap so
            # distances from actual entry match the originally-planned distances.
            # Triggers only if unfavorable slippage > 10% of planned SL distance.
            sl_distance = abs(expected - stop_loss) if expected > 0 else 0.0
            if slippage > 0 and sl_distance > 0 and slippage > sl_distance * 0.1:
                if direction == "BUY":
                    new_sl = stop_loss + slippage
                    new_tp = take_profit + slippage
                else:
                    new_sl = stop_loss - slippage
                    new_tp = take_profit - slippage
                logger.warning(
                    "Adjusting SL/TP for slippage=%.2f: SL %.2f->%.2f, TP %.2f->%.2f",
                    slippage, stop_loss, new_sl, take_profit, new_tp,
                )
                try:
                    await self.executor.modify_position(
                        deal_id=result.deal_id,
                        stop_loss=new_sl,
                        take_profit=new_tp,
                    )
                    stop_loss = new_sl
                    take_profit = new_tp
                except Exception as mod_err:
                    logger.warning(
                        "Slippage SL/TP adjust failed, using original levels: %s",
                        mod_err,
                    )

            # Get current spread
            spread = 0.0
            try:
                price = await self.client.get_current_price()
                spread = abs(price.get("ask", 0) - price.get("bid", 0))
            except BrokerError as e:
                logger.warning("Could not fetch spread at entry: %s", e)

            # Persist to database
            get_session, Trade, TradeRepository, OrderLogRepository = _get_db_dependencies()
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

            persisted_trade: Trade | None = None
            last_db_err: Exception | None = None
            for attempt in range(1, _DB_PERSIST_RETRIES + 1):
                try:
                    async with get_session() as session:
                        repo = TradeRepository(session)
                        persisted_trade = await repo.add(trade)

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
                                "client_order_id": client_order_id,
                            },
                        )
                    last_db_err = None
                    break
                except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
                    raise
                except Exception as db_err:
                    last_db_err = db_err
                    logger.warning(
                        "DB insert attempt %d/%d failed for deal %s: %s",
                        attempt, _DB_PERSIST_RETRIES, result.deal_id, db_err,
                    )
                    if attempt < _DB_PERSIST_RETRIES:
                        await asyncio.sleep(_DB_PERSIST_BACKOFF_SECONDS * attempt)

            if persisted_trade is not None:
                trade = persisted_trade
            else:
                # CRITICAL: Broker order succeeded but DB insert failed after
                # all retries. Position is OPEN at the broker but not in DB.
                # Policy: immediately close at broker to avoid an unsupervised
                # position; if the emergency close also fails, store the deal
                # in the reconciliation queue for a later retry.
                logger.critical(
                    "ORPHANED TRADE: Broker order %s succeeded but DB insert failed "
                    "after %d retries: %s. Attempting emergency broker close.",
                    result.deal_id, _DB_PERSIST_RETRIES, last_db_err,
                )
                emergency_closed = False
                try:
                    await self.executor.close_position(result.deal_id)
                    emergency_closed = True
                    logger.critical(
                        "ORPHANED TRADE: deal %s closed at broker as emergency recovery",
                        result.deal_id,
                    )
                except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
                    raise
                except Exception as close_err:
                    logger.critical(
                        "ORPHANED TRADE: emergency close failed for deal %s: %s — "
                        "queuing for reconciliation",
                        result.deal_id, close_err,
                    )

                # Try once more to persist an ORPHANED marker row so the
                # reconciler has a durable record. Best effort only.
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
                        orphan_repo = TradeRepository(session)
                        await orphan_repo.add(orphan)
                except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
                    raise
                except Exception:
                    logger.critical(
                        "Could not even save ORPHANED record for deal %s — "
                        "only in-memory reconciliation queue will track it",
                        result.deal_id,
                    )

                self.orphan_open_queue.append({
                    "deal_id": result.deal_id,
                    "client_order_id": client_order_id,
                    "direction": direction,
                    "lot_size": lot_size,
                    "entry_price": result.level,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "broker_closed": emergency_closed,
                    "queued_at": datetime.now(timezone.utc),
                    "last_error": str(last_db_err) if last_db_err else None,
                })

                if emergency_closed:
                    # Nothing else to track; the broker has no position and
                    # the reconciliation queue has the audit trail.
                    self.trailing.remove_tracking(result.deal_id)
                    return None

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
                get_session, _, _, OrderLogRepository = _get_db_dependencies()
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
        get_session, _, TradeRepository, OrderLogRepository = _get_db_dependencies()

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

        # Phase 3: Update DB with final status and P&L. Broker close has
        # already succeeded, so this DB write MUST eventually succeed —
        # retry aggressively, then push to the reconciliation queue.
        db_updated = False
        last_db_err: Exception | None = None
        exit_price_final = result.level if result.level is not None and result.level > 0 else 0
        pnl_final: dict[str, float] | None = None
        for attempt in range(1, _DB_PERSIST_RETRIES + 1):
            try:
                async with get_session() as session:
                    repo = TradeRepository(session)
                    trade = await repo.get_by_deal_id(deal_id)
                    if trade:
                        pnl_final = self._calc_pnl(trade, exit_price_final)
                        await repo.close_trade(
                            trade_id=trade.id,
                            exit_price=exit_price_final,
                            pnl_pips=pnl_final["pips"],
                            pnl_euros=pnl_final["euros"],
                            net_pnl=pnl_final["net"],
                            close_reason=reason,
                        )
                        log_repo = OrderLogRepository(session)
                        await log_repo.log_action(
                            action="CLOSED",
                            deal_id=deal_id,
                            details={"reason": reason, "pnl": pnl_final},
                        )
                db_updated = True
                last_db_err = None
                break
            except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
                raise
            except Exception as db_err:
                last_db_err = db_err
                logger.warning(
                    "DB close-update attempt %d/%d failed for deal %s: %s",
                    attempt, _DB_PERSIST_RETRIES, deal_id, db_err,
                )
                if attempt < _DB_PERSIST_RETRIES:
                    await asyncio.sleep(_DB_PERSIST_BACKOFF_SECONDS * attempt)

        if not db_updated:
            logger.critical(
                "Trade %s closed at broker but DB update failed after %d retries: %s. "
                "Queuing for reconciliation — DB row still shows CLOSING.",
                deal_id, _DB_PERSIST_RETRIES, last_db_err,
            )
            self.orphan_close_queue.append({
                "deal_id": deal_id,
                "exit_price": exit_price_final,
                "close_reason": reason,
                "pnl": pnl_final,
                "queued_at": datetime.now(timezone.utc),
                "last_error": str(last_db_err) if last_db_err else None,
            })

        self.trailing.remove_tracking(deal_id)
        self.monitor.untrack_position(deal_id)
        logger.info("Trade closed: deal=%s, reason=%s", deal_id, reason)
        return True

    async def close_all(self) -> int:
        """Emergency close all positions (kill switch). Returns count closed."""
        results = await self.executor.close_all()
        count = sum(1 for r in results if r.status != "REJECTED")
        logger.critical("Kill switch: closed %d/%d positions", count, len(results))
        get_session, _, TradeRepository, _ = _get_db_dependencies()

        # Persist closed status to DB for each successfully closed position
        for r in results:
            if r.status == "REJECTED" or not r.deal_id:
                continue
            db_updated = False
            last_db_err: Exception | None = None
            pnl: dict[str, float] | None = None
            exit_price = r.level if r.level is not None and r.level > 0 else 0
            try:
                for attempt in range(1, _DB_PERSIST_RETRIES + 1):
                    try:
                        async with get_session() as session:
                            repo = TradeRepository(session)
                            trade = await repo.get_by_deal_id(r.deal_id)
                            if trade and trade.status in ("OPEN", "CLOSING", TradeStatus.OPEN, TradeStatus.CLOSING):
                                pnl = self._calc_pnl(trade, exit_price) if exit_price > 0 else {
                                    "pips": 0.0,
                                    "euros": 0.0,
                                    "net": 0.0,
                                }
                                await repo.close_trade(
                                    trade_id=trade.id,
                                    exit_price=exit_price,
                                    pnl_pips=pnl["pips"],
                                    pnl_euros=pnl["euros"],
                                    net_pnl=pnl["net"],
                                    close_reason="KILL_SWITCH",
                                )
                            db_updated = True
                            last_db_err = None
                            break
                    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
                        raise
                    except Exception as db_err:
                        last_db_err = db_err
                        logger.warning(
                            "Kill-switch DB close-update attempt %d/%d failed for deal %s: %s",
                            attempt,
                            _DB_PERSIST_RETRIES,
                            r.deal_id,
                            db_err,
                        )
                        if attempt < _DB_PERSIST_RETRIES:
                            await asyncio.sleep(_DB_PERSIST_BACKOFF_SECONDS * attempt)
            except Exception as db_err:
                last_db_err = db_err

            if not db_updated:
                logger.critical(
                    "Trade %s closed by kill switch but DB update failed after %d retries: %s. "
                    "Keeping tracking and queuing reconciliation.",
                    r.deal_id,
                    _DB_PERSIST_RETRIES,
                    last_db_err,
                )
                self.orphan_close_queue.append({
                    "deal_id": r.deal_id,
                    "exit_price": exit_price,
                    "close_reason": "KILL_SWITCH",
                    "pnl": pnl,
                    "queued_at": datetime.now(timezone.utc),
                    "last_error": str(last_db_err) if last_db_err else None,
                })
                continue

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
                    pos.stop_level = new_sl
                except BrokerError as e:
                    logger.error("Failed to update trailing SL for %s: %s", deal_id, e)
                    # Invalidate cached trailing level so the next iteration
                    # recomputes from broker truth instead of falsely
                    # believing the SL was already advanced. Without this,
                    # the monotonicity guard would suppress every retry.
                    self.trailing.remove_tracking(deal_id)

            if self._exit_ai_enabled and self._exit_ai_advisor is not None:
                snapshot = self._build_exit_ai_snapshot(deal_id, pos)
                recommendation = self._exit_ai_advisor.recommend(snapshot)
                await self._apply_exit_ai_recommendation(
                    deal_id,
                    pos,
                    recommendation,
                )

        return status

    def _build_exit_ai_snapshot(self, deal_id: str, pos: Position) -> dict[str, Any]:
        current_stop = float(pos.stop_level) if pos.stop_level is not None else float(pos.open_level)
        risk_distance = max(abs(float(pos.open_level) - current_stop), 0.5)
        take_profit = (
            float(pos.limit_level)
            if pos.limit_level is not None
            else (
                float(pos.open_level) + (risk_distance * 3.0)
                if pos.direction == "BUY"
                else float(pos.open_level) - (risk_distance * 3.0)
            )
        )
        tp1 = (
            float(pos.open_level) + (abs(take_profit - float(pos.open_level)) * 0.5)
            if pos.direction == "BUY"
            else float(pos.open_level) - (abs(take_profit - float(pos.open_level)) * 0.5)
        )
        return {
            "deal_id": deal_id,
            "direction": pos.direction,
            "regime": "RANGING",
            "entry_price": float(pos.open_level),
            "current_price": float(pos.current_level),
            "current_stop_loss": current_stop,
            "initial_stop_loss": current_stop,
            "take_profit": take_profit,
            "tp1": tp1,
            "atr": max(risk_distance * 0.75, 0.25),
            "hours_open": 0.0,
            "volume_ratio": 1.0,
            "spread_pips": 0.0,
        }

    async def _apply_exit_ai_recommendation(
        self,
        deal_id: str,
        pos: Position,
        recommendation: Any,
    ) -> bool:
        rec_dict = (
            recommendation.to_dict()
            if hasattr(recommendation, "to_dict")
            else dict(recommendation)
        )
        context = {
            "deal_id": deal_id,
            "baseline_context": rec_dict.get("baseline_context", {}),
            "recommendation": rec_dict,
        }
        self.monitor.set_runtime_context(deal_id, context)

        if rec_dict.get("no_op") or rec_dict.get("action") == "HOLD":
            self._record_exit_ai_event(
                deal_id=deal_id,
                status="skipped",
                recommendation=rec_dict,
                applied_action="HOLD",
                reconciliation_context=context,
            )
            return False

        action = str(rec_dict["action"])
        try:
            if action == "TIGHTEN_SL":
                proposed_stop = rec_dict.get("proposed_stop_loss")
                modify_result = self.executor.modify_position(
                    deal_id,
                    stop_loss=float(proposed_stop),
                )
                if inspect.isawaitable(modify_result):
                    await modify_result
                pos.stop_level = float(proposed_stop)
                self._record_exit_ai_event(
                    deal_id=deal_id,
                    status="applied",
                    recommendation=rec_dict,
                    applied_action="modify_position",
                    reconciliation_context=context,
                )
                return True

            if action == "PARTIAL_CLOSE":
                partial_close = getattr(self.executor, "partial_close_position", None)
                if self._exit_ai_partial_close.was_tp1_closed(deal_id):
                    self._record_exit_ai_event(
                        deal_id=deal_id,
                        status="skipped",
                        recommendation=rec_dict,
                        applied_action="duplicate_partial_close",
                        reconciliation_context=context,
                    )
                    return False
                if not callable(partial_close):
                    self._record_exit_ai_event(
                        deal_id=deal_id,
                        status="skipped",
                        recommendation=rec_dict,
                        applied_action="partial_close_unsupported",
                        reconciliation_context=context,
                    )
                    return False
                partial_result = partial_close(
                    deal_id,
                    float(rec_dict.get("close_fraction", 0.5)),
                )
                if inspect.isawaitable(partial_result):
                    await partial_result
                self._exit_ai_partial_close.evaluate(
                    deal_id,
                    pos.direction,
                    float(pos.current_level),
                    float(pos.current_level),
                )
                self._record_exit_ai_event(
                    deal_id=deal_id,
                    status="applied",
                    recommendation=rec_dict,
                    applied_action="partial_close",
                    reconciliation_context=context,
                )
                return True

            if action == "FULL_EXIT":
                closed = await self.close_trade(deal_id, reason="EXIT_AI_FULL_EXIT")
                self._record_exit_ai_event(
                    deal_id=deal_id,
                    status="applied" if closed else "rejected",
                    recommendation=rec_dict,
                    applied_action="close_trade",
                    reconciliation_context=context,
                )
                return bool(closed)
        except BrokerError as exc:
            self._record_exit_ai_event(
                deal_id=deal_id,
                status="rejected",
                recommendation=rec_dict,
                applied_action=action.lower(),
                error=str(exc),
                reconciliation_context=context,
            )
            return False

        self._record_exit_ai_event(
            deal_id=deal_id,
            status="skipped",
            recommendation=rec_dict,
            applied_action="unsupported_action",
            reconciliation_context=context,
        )
        return False

    def _record_exit_ai_event(
        self,
        *,
        deal_id: str,
        status: str,
        recommendation: dict[str, Any],
        applied_action: str,
        reconciliation_context: dict[str, Any],
        error: str | None = None,
    ) -> None:
        self._exit_ai_audit_log.append(
            {
                "deal_id": deal_id,
                "status": status,
                "applied_action": applied_action,
                "baseline_context": recommendation.get("baseline_context", {}),
                "recommendation": recommendation,
                "confidence": recommendation.get("confidence", 0.0),
                "reason": recommendation.get("reason", ""),
                "error": error,
                "reconciliation_context": reconciliation_context,
            }
        )

    @property
    def exit_ai_audit_log(self) -> list[dict[str, Any]]:
        return list(self._exit_ai_audit_log)

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
        if trade.direction == "BUY":
            price_diff = exit_price - entry
        else:
            price_diff = entry - exit_price
        euros = price_diff * lot

        # spread_at_entry is stored as an absolute price difference
        # (ask - bid) in quote-currency units (USD/oz for Gold CFD), NOT in
        # pips. Multiplying by lot size (ounces) therefore yields the spread
        # cost directly in USD. If spread_at_entry is ever reinterpreted as
        # pips, convert here via `* PIP_SIZE` — PIP_SIZE imported for that
        # reason so the conversion site is obvious.
        _ = PIP_SIZE  # unit reference — see comment above
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
