"""Lifecycle mixin -- init, health check, start, stop, mode switching."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from typing import TYPE_CHECKING

from config.settings import Settings
from database.connection import close_db, init_db
from market_data.broker_client import CapitalComClient
from market_data.data_provider import DataProvider
from market_data.historical import download_historical_candles
from notifications.confirmation_handler import ConfirmationHandler
from notifications.notification_manager import NotificationManager
from order_management.order_manager import OrderManager
from risk.risk_manager import RiskManager
from strategy.strategy_manager import StrategyManager

if TYPE_CHECKING:
    from main import TradingSystem

logger = logging.getLogger("main")


class LifecycleMixin:
    """System lifecycle: init, health check, start, stop, mode switching."""

    def __init__(self: TradingSystem, settings: Settings) -> None:
        self.settings = settings
        self._running = False

        # Initialize components
        self.broker = CapitalComClient(
            email=settings.capital_email,
            password=settings.capital_password,
            api_key=settings.capital_api_key,
            demo=settings.capital_demo,
        )
        self.data = DataProvider(self.broker)
        self.risk = RiskManager(
            max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
            max_daily_loss_pct=settings.max_daily_loss_pct,
            max_weekly_loss_pct=settings.max_weekly_loss_pct,
            max_open_positions=settings.max_open_positions,
            max_trades_per_day=settings.max_trades_per_day,
            kill_switch_drawdown_pct=settings.kill_switch_drawdown_pct,
        )
        self.orders = OrderManager(
            self.broker,
            exit_ai_enabled=settings.exit_ai_enabled,
            exit_ai_saved_models_dir=settings.exit_ai_saved_models_dir,
        )
        self.notifications = NotificationManager(
            enabled=settings.notifications_enabled,
        )
        self.strategy = StrategyManager(
            min_score=settings.min_trade_score,
            min_confidence=settings.min_confidence,
        )
        self._ai_predictor = None  # Lazy-loaded
        self._confirmation_handler = None  # For semi-auto mode
        self._mirofish_client = None  # Lazy-loaded when mirofish_enabled (Phase 6)
        self._mirofish_task = None    # Background simulation loop asyncio.Task
        self._mirofish_disabled: bool = False  # Set True if MiroFish failed/crashed
        self._sentiment_service = None  # Lazy-loaded when sentiment_enabled (Phase 11)

        # Economic calendar (Phase 8) -- graceful when disabled
        self._event_service = None
        if settings.calendar_enabled:
            from calendar.event_service import EventService
            self._event_service = EventService(
                block_minutes_before=settings.calendar_block_minutes_before,
                cooldown_minutes_after=settings.calendar_cooldown_minutes_after,
                force_close_enabled=settings.calendar_force_close_on_extreme,
            )
        self._consecutive_errors: int = 0

        # Cache for account info and spread (refreshed every 5 minutes)
        self._cached_account = None
        self._cached_account_ts: float = 0.0
        self._cached_spread: float = 0.0
        self._cached_spread_ts: float = 0.0
        self._CACHE_TTL_SECONDS: float = 300.0  # 5 minutes

    def _on_mirofish_done(self: TradingSystem, task: asyncio.Task) -> None:
        """Done-callback for the MiroFish background task.

        Logs unexpected exceptions and marks the subsystem as degraded so
        monitoring/health endpoints know MiroFish is no longer producing
        signals. Cancellation during shutdown is treated as expected.
        """
        if task.cancelled():
            return
        exc = task.exception()
        if exc is None:
            # Loop exited cleanly -- still mark as not running so callers
            # don't expect signals from a stopped task.
            self._mirofish_disabled = True
            logger.warning("MiroFish background task exited cleanly (no longer producing signals)")
            return
        logger.error(
            "MiroFish background task crashed: %s", exc, exc_info=exc,
        )
        self._mirofish_disabled = True
        # Drop client reference so accidental usage fails fast.
        self._mirofish_client = None

    async def _calendar_refresh_loop(self: TradingSystem) -> None:
        """Background task: refresh economic calendar periodically."""
        if self._event_service is None:
            return  # Calendar disabled

        interval = self.settings.calendar_fetch_interval_minutes * 60
        while self._running:
            await asyncio.sleep(interval)
            try:
                await asyncio.wait_for(self._event_service.refresh(), timeout=60)
                logger.debug("Calendar refreshed (%d events)", self._event_service.cached_event_count)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Calendar refresh failed: %s", e)

    async def _health_check(self: TradingSystem) -> None:
        """Validate all critical components before starting the trading loop.

        Raises RuntimeError if a critical component is unavailable.
        """
        logger.info("Running startup health checks...")
        issues: list[str] = []

        # 1. Database
        try:
            await init_db()
            logger.info("[OK] Database initialized")
        except Exception as e:
            issues.append(f"Database: {e}")
            logger.critical("[FAIL] Database: %s", e)

        # 2. Broker authentication
        try:
            await self.broker.authenticate()
            mode_label = "DEMO" if self.settings.capital_demo else "LIVE"
            logger.info("[OK] Broker authenticated (%s)", mode_label)
        except Exception as e:
            err_str = str(e)
            if "401" in err_str or "Login failed" in err_str:
                msg = (
                    "API Key ungueltig -- prüfe CAPITAL_API_KEY und ob "
                    "Demo/Live (CAPITAL_DEMO) korrekt eingestellt ist"
                )
                issues.append(msg)
                logger.critical("[FAIL] Broker: %s", msg)
            else:
                issues.append(f"Broker authentication: {e}")
                logger.critical("[FAIL] Broker: %s", e)

        # 3. AI models (warning, not critical unless ALLOW_TRADING_WITHOUT_AI)
        models_dir = os.path.join("ai_engine", "saved_models")
        if os.path.isdir(models_dir) and os.listdir(models_dir):
            logger.info("[OK] AI model directory found (%s)", models_dir)
        else:
            logger.warning(
                "[WARN] AI models not found in %s -- bot will return HOLD for all signals",
                models_dir,
            )

        # 4. Twilio (optional)
        if self.settings.notifications_enabled:
            if self.settings.twilio_account_sid and self.settings.twilio_auth_token:
                logger.info("[OK] Twilio credentials configured")
            else:
                logger.warning(
                    "[WARN] Notifications enabled but Twilio credentials missing"
                )

        # Fail if critical issues
        if issues:
            msg = "Startup health check failed:\n" + "\n".join(f"  - {i}" for i in issues)
            logger.critical(msg)
            raise RuntimeError(msg)

        logger.info("All health checks passed")

    async def start(self: TradingSystem) -> None:
        """Initialize system and start trading loop."""
        mode_label = "DEMO" if self.settings.capital_demo else "LIVE"
        logger.info("=" * 60)
        logger.info("GOLD INTRADAY TRADING SYSTEM v2.0")
        logger.info("Mode: %s | Trading: %s", mode_label, self.settings.trading_mode.upper())
        logger.info("Risk: %.1f%% pro Trade | Timeframes: %s",
                     self.settings.max_risk_per_trade_pct,
                     ", ".join(self.settings.timeframes))
        logger.info("=" * 60)

        # Run health checks (DB + Broker + AI + Twilio)
        await self._health_check()

        # Get account info and set risk baseline
        account = await asyncio.wait_for(self.broker.get_account(), timeout=15)
        self.risk.set_initial_equity(account.balance)
        logger.info(
            "Account: balance=%.2f %s, available=%.2f",
            account.balance, account.currency, account.available,
        )

        # Load risk metrics cache from DB
        from database.connection import get_session

        async with get_session() as session:
            await self.risk.metrics_cache.load_from_db(session)

        # Download initial historical data
        logger.info("Downloading historical data...")
        await asyncio.wait_for(
            download_historical_candles(
                self.broker, self.settings.timeframes, max_candles=500,
            ),
            timeout=120,
        )
        logger.info("Historical data ready")

        # Recover open positions from database
        from database.repositories.trade_repo import TradeRepository

        async with get_session() as session:
            trade_repo = TradeRepository(session)
            open_trades = await trade_repo.get_open_trades()
            if open_trades:
                recovered = await asyncio.wait_for(
                    self.orders.position_monitor.recover_from_db(open_trades),
                    timeout=30,
                )
                # Sync with broker to detect positions closed while bot was offline
                sync_result = await asyncio.wait_for(
                    self.orders.position_monitor.sync_with_broker(),
                    timeout=30,
                )
                orphaned = sync_result.get("orphaned", [])
                if orphaned:
                    for deal_id in orphaned:
                        logger.warning(
                            "Orphaned position %s (closed at broker while bot was offline) "
                            "-- marking as CLOSED_BY_BROKER",
                            deal_id,
                        )
                        trade = await trade_repo.get_by_deal_id(deal_id)
                        if trade:
                            await trade_repo.close_trade(
                                trade_id=trade.id,
                                exit_price=float(trade.entry_price),  # approximate
                                pnl_pips=0.0,
                                pnl_euros=0.0,
                                net_pnl=0.0,
                                close_reason="CLOSED_BY_BROKER",
                            )
                        self.orders.position_monitor.untrack_position(deal_id)
                logger.info(
                    "Position recovery: %d from DB, %d synced, %d orphaned",
                    recovered,
                    len(sync_result.get("synced", [])),
                    len(orphaned),
                )
            else:
                logger.info("No open positions to recover")

        # Initialize semi-auto mode if configured
        if self.settings.trading_mode == "semi_auto":
            self._confirmation_handler = ConfirmationHandler(
                notification_manager=self.notifications,
                timeout_seconds=self.settings.confirmation_timeout_seconds,
            )
            logger.info(
                "Semi-auto mode active (timeout: %ds)",
                self.settings.confirmation_timeout_seconds,
            )

        # Start news sentiment polling and MiroFish seed refresh (Phase 11)
        if self.settings.sentiment_enabled:
            try:
                from sentiment import SentimentService

                self._sentiment_service = SentimentService(self.settings)
                await self._sentiment_service.start()
                logger.info("News sentiment analysis ENABLED")
            except Exception as e:
                logger.exception(
                    "Sentiment service startup failed (trading continues without it): %s", e
                )
                self._sentiment_service = None

        # Start MiroFish background simulation loop (Phase 6)
        if self.settings.mirofish_enabled:
            try:
                from ai_engine.mirofish_client import MiroFishClient, run_simulation_loop
                self._mirofish_client = MiroFishClient(
                    base_url=self.settings.mirofish_url,
                    timeout_seconds=self.settings.mirofish_simulation_timeout_seconds,
                    cache_ttl_seconds=self.settings.mirofish_cache_ttl_seconds,
                    max_simulations_per_day=self.settings.mirofish_max_sims_per_day,
                    token_budget_per_day=self.settings.mirofish_token_budget_per_day,
                    max_rounds=self.settings.mirofish_max_rounds,
                )
                self._mirofish_task = asyncio.create_task(
                    run_simulation_loop(
                        self._mirofish_client,
                        interval_seconds=self.settings.mirofish_poll_interval_seconds,
                    ),
                    name="mirofish_simulation_loop",
                )
                # Surface background-task crashes instead of swallowing them.
                self._mirofish_task.add_done_callback(self._on_mirofish_done)
                logger.info("MiroFish swarm intelligence ENABLED (poll every %ds)", self.settings.mirofish_poll_interval_seconds)
            except Exception as e:
                # Use logger.exception to capture full traceback for monitoring.
                logger.exception(
                    "MiroFish startup failed (trading continues without it): %s", e
                )
                self._mirofish_client = None
                self._mirofish_task = None
                self._mirofish_disabled = True

        # Initial calendar refresh (Phase 8)
        if self._event_service is not None:
            try:
                count = await asyncio.wait_for(self._event_service.refresh(), timeout=30)
                logger.info("[OK] Economic calendar: %d Gold-relevant events loaded", self._event_service.cached_event_count)
            except Exception as e:
                logger.warning("[WARN] Economic calendar refresh failed (trading continues): %s", e)

        # Start the loops
        self._running = True
        logger.info(
            "Starting trading loop (interval: %ds)...",
            self.settings.trading_interval_seconds,
        )

        await asyncio.gather(
            self._trading_loop(),
            self._position_monitor_loop(),
            self._daily_cleanup_loop(),
            self._calendar_refresh_loop(),  # Phase 8
        )

    async def stop(self: TradingSystem) -> None:
        """Gracefully shutdown with position reconciliation.

        Shutdown sequence:
        1. Stop trading loop (no new trades)
        2. Kill-switch close if active
        3. Position reconciliation (DB vs broker)
        4. Report open positions
        5. Close broker and DB connections
        """
        logger.info("Shutting down...")
        self._running = False

        # Stop news sentiment service (Phase 11)
        if self._sentiment_service is not None:
            await self._sentiment_service.stop()
            self._sentiment_service = None

        # Cancel MiroFish background task (Phase 6)
        if self._mirofish_task is not None:
            self._mirofish_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._mirofish_task
            logger.info("MiroFish background task stopped")

        try:
            # Kill switch: close all positions
            if self.risk.kill_switch.is_active:
                logger.warning("Kill switch active -- closing all positions on shutdown")
                count = await self.orders.close_all()
                self.notifications.notify_kill_switch(
                    reason=self.risk.kill_switch.reason,
                    drawdown_pct=self.risk.get_drawdown_pct(0),
                    positions_closed=count,
                )

            # Position reconciliation
            open_count = self.orders.get_open_count()
            if open_count > 0:
                logger.info(
                    "Reconciling %d open position(s) with broker...", open_count,
                )
                try:
                    sync = await asyncio.wait_for(
                        self.orders.position_monitor.sync_with_broker(),
                        timeout=15.0,
                    )
                    orphaned = sync.get("orphaned", [])
                    if orphaned:
                        logger.warning(
                            "Found %d position(s) closed at broker during shutdown",
                            len(orphaned),
                        )
                    logger.info(
                        "Shutdown position report: %d still open at broker",
                        len(sync.get("synced", [])),
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Position reconciliation timed out -- %d position(s) may be untracked",
                        open_count,
                    )
            else:
                logger.info("No open positions at shutdown")

        except Exception as e:
            logger.error("Error during shutdown cleanup: %s", e, exc_info=True)

        # Close connections
        try:
            await self.broker.close()
        except Exception as e:
            logger.error("Error closing broker connection: %s", e)

        try:
            await close_db()
        except Exception as e:
            logger.error("Error closing database connection: %s", e)
        logger.info("Shutdown complete")

    def set_trading_mode(self: TradingSystem, mode: str) -> None:
        """Switch between auto and semi_auto at runtime."""
        if mode not in ("auto", "semi_auto"):
            raise ValueError(f"Invalid mode: {mode}")
        self.settings.trading_mode = mode
        logger.info("Trading mode changed to: %s", mode)
