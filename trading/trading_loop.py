"""Trading loop mixin -- main loop, tick, multi-timeframe fetch."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any

from database.connection import get_session
from database.repositories.governance_repo import GovernanceDecisionRepository
from market_data.broker_client import BrokerError
from shared.constants import TIMEFRAME_CANDLE_COUNTS
from shared.exceptions import (
    DataError,
    PredictionError,
    classify_error,
    ErrorCategory,
)

if TYPE_CHECKING:
    from main import TradingSystem

logger = logging.getLogger("main")


class TradingLoopMixin:
    """Main trading loop, tick execution, and multi-timeframe data fetch."""

    async def _trading_loop(self: TradingSystem) -> None:
        """Main trading loop -- runs every N seconds."""
        while self._running:
            try:
                await self._trading_tick()
                self._consecutive_errors = 0
            except asyncio.CancelledError:
                raise
            except (BrokerError, DataError, PredictionError) as e:
                self._consecutive_errors += 1
                category = classify_error(e)
                logger.error(
                    "Trading loop error [%s] (consecutive: %d): %s",
                    category.value, self._consecutive_errors, e,
                )
                if category == ErrorCategory.PERMANENT:
                    logger.critical(
                        "Permanent error detected -- consider stopping the bot: %s", e,
                    )
                if self._consecutive_errors >= 10:
                    logger.critical(
                        "10 consecutive errors -- activating kill switch",
                    )
                    self.risk.force_kill_switch(
                        f"10 consecutive errors, last: {e}"
                    )
                    try:
                        await self.notifications.notify_kill_switch(
                            reason=f"10 consecutive errors, last: {e}",
                            drawdown_pct=0,
                            positions_closed=0,
                        )
                    except Exception:
                        logger.exception("Kill-switch notification failed")
            except Exception as e:
                # Unexpected errors: log and alert, but do NOT auto-activate kill-switch immediately.
                self._consecutive_errors += 1
                logger.exception("UNEXPECTED trading loop error (count=%d): %s", self._consecutive_errors, e)

                try:
                    # Non-blocking alert (best-effort, awaited so retries/backoff
                    # don't block the loop via time.sleep).
                    await self.notifications.notify_warning(
                        f"Unexpected error in trading loop: {e}"
                    )
                except Exception as notify_err:
                    logger.exception(
                        "Notification failed: %s", notify_err, exc_info=True,
                    )

                # If many unexpected errors accumulate, stop for manual review (threshold lower)
                if self._consecutive_errors >= 5:
                    logger.critical("%d unexpected errors — deactivating trading loop for manual review", self._consecutive_errors)
                    self._running = False

            # Exponential backoff on errors, normal interval on success
            if self._consecutive_errors > 0:
                backoff = min(
                    self.settings.trading_interval_seconds * 2 ** min(self._consecutive_errors, 5),
                    300,
                )
                await asyncio.sleep(backoff)
            else:
                await asyncio.sleep(self.settings.trading_interval_seconds)

    async def _trading_tick(self: TradingSystem) -> None:
        """Single iteration of the trading loop."""
        # Sync kill switch with database
        async with get_session() as session:
            await self.risk.sync_kill_switch(session)

        if self.risk.kill_switch.is_active:
            return

        # Phase 8: Force-close on extreme events
        if self._event_service is not None and self._event_service.should_force_close():
            event = self._event_service.get_blocking_event()
            event_name = event.title if event else "extreme event"
            open_count = self.orders.get_open_count()
            if open_count > 0:
                logger.warning(
                    "FORCE CLOSE: %d position(s) due to imminent extreme event '%s'",
                    open_count, event_name,
                )
                closed = await self.orders.close_all()
                logger.info("Force-closed %d position(s) before '%s'", closed, event_name)
            return  # Skip tick entirely during extreme events

        # Optional: log during high-impact calendar windows (Phase 8)
        _calendar_high_impact = False
        try:
            from calendar.event_service import is_high_impact_window
            _calendar_high_impact = is_high_impact_window()
        except ImportError:
            pass  # Phase 8 not installed yet -- skip
        if _calendar_high_impact:
            logger.warning(
                "High-impact calendar window active -- position sizing will be conservative"
            )

        # Phase 8: Block new trades during high-impact window
        if self._event_service is not None and self._event_service.is_high_impact_window():
            event = self._event_service.get_blocking_event()
            event_name = event.title if event else "high-impact event"
            logger.info("Trade blocked: high-impact event window ('%s')", event_name)
            return

        # 1. Get market data
        df = await asyncio.wait_for(
            self.data.get_candles_df(timeframe="5m", count=5000), timeout=60,
        )
        if df.empty or len(df) < 50:
            logger.debug("Insufficient data, skipping tick")
            return

        # 2. Fetch multi-timeframe data ONCE (shared between AI and Strategy)
        mtf_data = None
        try:
            mtf_data = await self._fetch_mtf_parallel()
        except (BrokerError, DataError) as e:
            logger.debug("Multi-TF data unavailable: %s", e)

        # 3. Generate AI signal (Ensemble only)
        raw_signal = await self._generate_signal(df, mtf_data=mtf_data)
        if raw_signal is None or raw_signal.get("action") == "HOLD":
            if raw_signal is not None:
                await self._persist_governance_decision(
                    raw_signal,
                    executed=False,
                    rejection_reason="AI_HOLD",
                )
            return

        signal = self.strategy.evaluate(raw_signal, mtf_data=mtf_data)
        if signal is None:
            logger.debug("Signal filtered by StrategyManager")
            await self._persist_governance_decision(
                raw_signal,
                executed=False,
                rejection_reason="STRATEGY_FILTERED",
            )
            return

        # 4. Extract signal values (FIX BUG #1: confidence was undefined)
        direction = signal.get("action", "HOLD")
        confidence = signal.get("confidence", 0.0)
        entry_price = signal.get("entry_price", float(df.iloc[-1]["close"]))
        stop_loss = signal.get(
            "stop_loss",
            entry_price - 3.0 if direction == "BUY" else entry_price + 3.0,
        )
        take_profit = signal.get(
            "take_profit",
            entry_price + 6.0 if direction == "BUY" else entry_price - 6.0,
        )

        # 5. Get account state for risk checks (cached, refreshed every 5 min)
        now_mono = time.monotonic()
        if self._cached_account is None or (now_mono - self._cached_account_ts) >= self._CACHE_TTL_SECONDS:
            self._cached_account = await asyncio.wait_for(self.broker.get_account(), timeout=15)
            self._cached_account_ts = now_mono
        account = self._cached_account
        open_positions = self.orders.get_open_count()

        # Use cached risk metrics (reconcile with DB periodically)
        cache = self.risk.metrics_cache
        if cache.needs_reconciliation:
            async with get_session() as session:
                await cache.load_from_db(session)

        trades_today = cache.trades_today
        consecutive_losses = cache.consecutive_losses
        weekly_pnl = cache.weekly_pnl

        # Calculate weekly loss percentage
        weekly_loss_pct = 0.0
        if account.balance > 0 and weekly_pnl < 0:
            weekly_loss_pct = abs(weekly_pnl / account.balance) * 100.0

        # Get current spread (cached, refreshed every 5 min)
        if (now_mono - self._cached_spread_ts) >= self._CACHE_TTL_SECONDS:
            try:
                price_data = await asyncio.wait_for(
                    self.broker.get_current_price(), timeout=15,
                )
                self._cached_spread = abs(price_data.get("ask", 0) - price_data.get("bid", 0))
                self._cached_spread_ts = now_mono
            except BrokerError as e:
                logger.warning("Spread fetch failed: %s", e)
        current_spread = self._cached_spread

        # Extract ATR from latest candle data (feature engineering adds atr_14 column)
        current_atr = float(df.iloc[-1]["atr_14"]) if "atr_14" in df.columns else 3.0

        # 6. Risk check (11 pre-trade checks + portfolio heat + equity curve filter)
        approval = await self.risk.approve_trade(
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            current_equity=account.balance,
            available_margin=account.available,
            open_positions=open_positions,
            trades_today=trades_today,
            consecutive_losses=consecutive_losses,
            current_spread=current_spread,
            has_open_same_direction=self.orders.has_position_in_direction(direction),
            weekly_loss_pct=weekly_loss_pct,
            confidence=confidence,
            atr=current_atr,
        )

        if not approval.approved:
            logger.info("Trade rejected by risk: %s", approval.reason)
            await self._persist_governance_decision(
                signal,
                executed=False,
                rejection_reason=approval.reason,
            )
            await self._save_signal(signal, executed=False, rejection_reason=approval.reason)
            return

        # 7. Semi-auto mode: ask for WhatsApp confirmation
        if self.settings.trading_mode == "semi_auto" and self._confirmation_handler:
            approved, reason = await self._confirmation_handler.request_confirmation(signal)
            if not approved:
                logger.info("Trade rejected by user: %s", reason)
                await self._persist_governance_decision(
                    signal,
                    executed=False,
                    rejection_reason=reason,
                )
                await self._save_signal(signal, executed=False, rejection_reason=reason)
                return

        # 8. Execute trade (protected by async lock in OrderManager)
        logger.info(
            "EXECUTING: %s @ %.2f, lot=%.4f, SL=%.2f, TP=%.2f",
            direction, entry_price, approval.lot_size, stop_loss, take_profit,
        )

        trade = await self.orders.open_trade(
            direction=direction,
            lot_size=approval.lot_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_price=entry_price,
            ai_confidence=confidence,
            trade_score=signal.get("trade_score", 0),
            timeframe="5m",
            reasoning=signal.get("reasoning"),
        )

        if trade:
            await self._persist_governance_decision(signal, executed=True)
            await self._save_signal(signal, executed=True)
            await self.risk.metrics_cache.on_trade_opened()
            # Track portfolio heat for new position (use actual fill price, not intended)
            actual_entry = float(trade.entry_price) if trade.entry_price else entry_price
            risk_amount = abs(actual_entry - stop_loss) * approval.lot_size
            self.risk.on_position_opened(risk_amount, account.balance)
            logger.info("Trade #%s opened successfully", trade.deal_id)
            try:
                await self.notifications.notify_trade_opened(
                    direction=direction,
                    price=float(trade.entry_price),
                    lot_size=float(trade.lot_size),
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    score=signal.get("trade_score", 0),
                    confidence=confidence,
                )
            except Exception:
                logger.exception("Trade-opened notification failed")
        else:
            logger.warning("Trade execution failed (broker error or lock timeout)")
            await self._persist_governance_decision(
                signal,
                executed=False,
                rejection_reason="BROKER_FAILED: Order execution returned None",
            )
            await self._save_signal(
                signal, executed=False,
                rejection_reason="BROKER_FAILED: Order execution returned None",
            )

    def _extract_governance_audit(self: TradingSystem, signal: dict[str, Any]) -> dict[str, Any]:
        final_aggregation = signal.get("final_aggregation") or {}
        audit = final_aggregation.get("decision_audit") or signal.get("decision_audit") or {}
        final_action = str(audit.get("final_action") or signal.get("action") or "HOLD")
        preliminary_action = str(audit.get("preliminary_action") or final_action)
        gate_reasons = audit.get("gate_reasons") or final_aggregation.get("gate_reasons") or []
        return {
            "preliminary_action": preliminary_action,
            "final_action": final_action,
            "gate_decision": str(
                audit.get("gate_decision")
                or final_aggregation.get("gate_decision")
                or ("pass" if final_action != "HOLD" else "block")
            ),
            "regime": str(
                audit.get("regime")
                or final_aggregation.get("regime")
                or signal.get("regime")
                or "ranging"
            ),
            "gate_reasons": list(gate_reasons),
            "threshold_source": str(
                audit.get("threshold_source")
                or final_aggregation.get("threshold_source")
                or "defaults"
            ),
            "threshold_confidence": float(
                audit.get("threshold_confidence", signal.get("confidence", 0.0))
            ),
            "threshold_margin": float(audit.get("threshold_margin", 0.0)),
            "conflict_ratio": float(
                audit.get("conflict_ratio", final_aggregation.get("conflict_ratio", 0.0))
            ),
            "confidence_before": float(
                audit.get("confidence_before", signal.get("confidence", 0.0))
            ),
            "final_confidence": float(
                audit.get("final_confidence", signal.get("confidence", 0.0))
            ),
            "global_score": float(
                audit.get("global_score", final_aggregation.get("global_score", 0.0))
            ),
        }

    def _resolve_governance_artifact_version(self: TradingSystem) -> str | None:
        override = getattr(self, "_governance_artifact_version_override", None)
        if override:
            return str(override)

        predictor = getattr(self, "_ai_predictor", None)
        ensemble = getattr(predictor, "_predictor", None)
        saved_models_dir = getattr(
            ensemble,
            "saved_models_dir",
            os.path.join("ai_engine", "saved_models"),
        )

        production_path = os.path.join(saved_models_dir, "production.json")
        if os.path.exists(production_path):
            try:
                with open(production_path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                version_dir = payload.get("version_dir")
                if version_dir:
                    return str(version_dir)
                model_path = payload.get("path")
                if model_path:
                    return str(model_path)
            except (OSError, TypeError, ValueError):
                logger.debug("Failed to load governance production pointer", exc_info=True)

        return None

    async def _persist_governance_decision(
        self: TradingSystem,
        signal: dict[str, Any] | None,
        *,
        executed: bool,
        rejection_reason: str | None = None,
        evaluation_summary: dict[str, Any] | None = None,
    ) -> None:
        if not signal:
            return

        try:
            audit = self._extract_governance_audit(signal)
            async with get_session() as session:
                repo = GovernanceDecisionRepository(session)
                await repo.add_decision(
                    audit=audit,
                    was_executed=executed,
                    rejection_reason=rejection_reason,
                    artifact_version=self._resolve_governance_artifact_version(),
                    evaluation_summary=evaluation_summary,
                )
        except Exception as exc:
            logger.error("Failed to save governance decision to DB: %s", exc)

    async def _fetch_mtf_parallel(self: TradingSystem) -> dict:
        """Fetch multi-timeframe data in parallel using asyncio.gather."""
        timeframes = self.settings.timeframes

        async def _fetch_one(tf: str):
            count = TIMEFRAME_CANDLE_COUNTS.get(tf, 200)
            return tf, await self.data.get_candles_df(tf, count=count, with_indicators=True)

        results = await asyncio.gather(
            *[_fetch_one(tf) for tf in timeframes],
            return_exceptions=True,
        )

        mtf = {}
        for r in results:
            if isinstance(r, Exception):
                logger.warning("MTF fetch failed for one timeframe: %s", r)
                continue
            tf, df = r
            mtf[tf] = df

        return mtf

