"""Trading loop mixin -- main loop, tick, multi-timeframe fetch."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from database.connection import get_session
from market_data.broker_client import BrokerError
from shared.exceptions import (
    BrokerError as _BrokerError,
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
                    self.notifications.notify_kill_switch(
                        reason=f"10 consecutive errors, last: {e}",
                        drawdown_pct=0,
                        positions_closed=0,
                    )
            except Exception as e:
                self._consecutive_errors += 1
                category = classify_error(e)
                logger.error(
                    "Unexpected trading loop error [%s] (consecutive: %d): %s",
                    category.value, self._consecutive_errors, e, exc_info=True,
                )
                if category == ErrorCategory.UNKNOWN:
                    logger.critical(
                        "Unknown error -- activating kill switch as fail-safe: %s", e,
                    )
                    self.risk.force_kill_switch(f"Unknown error in trading loop: {e}")
                if self._consecutive_errors >= 10:
                    logger.critical(
                        "10 consecutive errors -- activating kill switch",
                    )
                    self.risk.force_kill_switch(
                        f"10 consecutive errors, last: {e}"
                    )
                    self.notifications.notify_kill_switch(
                        reason=f"10 consecutive errors, last: {e}",
                        drawdown_pct=0,
                        positions_closed=0,
                    )

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

        # 1. Get market data
        df = await asyncio.wait_for(
            self.data.get_candles_df(timeframe="5m", count=200), timeout=30,
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
            return

        signal = self.strategy.evaluate(raw_signal, mtf_data=mtf_data)
        if signal is None:
            logger.debug("Signal filtered by StrategyManager")
            return

        # 4. Extract signal values (FIX BUG #1: confidence was undefined)
        direction = signal["action"]
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
            except BrokerError:
                pass
        current_spread = self._cached_spread

        # 6. Risk check (11 pre-trade checks)
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
        )

        if not approval.approved:
            logger.info("Trade rejected by risk: %s", approval.reason)
            await self._save_signal(signal, executed=False, rejection_reason=approval.reason)
            return

        # 7. Semi-auto mode: ask for WhatsApp confirmation
        if self.settings.trading_mode == "semi_auto" and self._confirmation_handler:
            approved, reason = await self._confirmation_handler.request_confirmation(signal)
            if not approved:
                logger.info("Trade rejected by user: %s", reason)
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
            await self._save_signal(signal, executed=True)
            await self.risk.metrics_cache.on_trade_opened()
            logger.info("Trade #%s opened successfully", trade.deal_id)
            self.notifications.notify_trade_opened(
                direction=direction,
                price=float(trade.entry_price),
                lot_size=float(trade.lot_size),
                stop_loss=stop_loss,
                take_profit=take_profit,
                score=signal.get("trade_score", 0),
                confidence=confidence,
            )
        else:
            logger.warning("Trade execution failed (broker error or lock timeout)")
            await self._save_signal(
                signal, executed=False,
                rejection_reason="BROKER_FAILED: Order execution returned None",
            )

    async def _fetch_mtf_parallel(self: TradingSystem) -> dict:
        """Fetch multi-timeframe data in parallel using asyncio.gather."""
        timeframes = self.settings.timeframes

        async def _fetch_one(tf: str):
            return tf, await self.data.get_candles_df(tf, count=200, with_indicators=True)

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
