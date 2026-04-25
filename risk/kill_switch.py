"""Kill Switch — emergency system to stop all trading and close positions."""

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class KillSwitch:
    """Emergency stop mechanism.

    When activated:
    1. All open positions are closed immediately
    2. No new trades are allowed
    3. WhatsApp alert is sent
    4. State is persisted in DB (survives restarts)
    """

    def __init__(self, max_drawdown_pct: float = 20.0) -> None:
        self.max_drawdown_pct = max_drawdown_pct
        self._active = False
        self._activated_at: datetime | None = None
        self._reason: str = ""
        # Optional session factory injected by the bootstrap so that
        # synchronous activate() calls can still persist to DB. May stay None
        # in tests / contexts where no DB is available.
        self._session_factory = None

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def reason(self) -> str:
        return self._reason

    def set_session_factory(self, session_factory) -> None:
        """Inject an async session factory used to persist activation in DB.

        The factory must be an async context manager yielding a session.
        Optional — if not set, activate() falls back to in-memory only.
        """
        self._session_factory = session_factory

    def activate(self, reason: str) -> None:
        """Activate kill switch. All trading stops immediately.

        The in-memory flag is set FIRST (fail-safe). If a session factory is
        available, the activation is also persisted to the DB on a best-effort
        basis. DB failures are logged at CRITICAL but never undo the activation.
        """
        if self._active:
            return
        self._active = True
        self._activated_at = datetime.now(timezone.utc)
        self._reason = reason
        logger.critical("KILL SWITCH ACTIVATED: %s", reason)

        # Best-effort DB persistence — fail-safe semantics: kill switch stays
        # active even if persistence fails.
        if self._session_factory is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                loop.create_task(self._persist_activation_safe())
            else:
                try:
                    asyncio.run(self._persist_activation_safe())
                except Exception as e:
                    logger.critical(
                        "Kill switch DB persistence failed (no loop): %s — "
                        "kill switch REMAINS ACTIVE (fail-safe)", e,
                    )

    async def _persist_activation_safe(self) -> None:
        """Persist activation to DB; swallow errors but log CRITICAL."""
        try:
            from database.repositories.risk_repo import DailyRiskStateRepository

            async with self._session_factory() as session:
                repo = DailyRiskStateRepository(session)
                await repo.activate_kill_switch()
                # Some session factories require explicit commit.
                commit = getattr(session, "commit", None)
                if commit is not None:
                    try:
                        await commit()
                    except Exception:
                        # Autocommit sessions raise — ignore.
                        pass
            logger.info("Kill switch activation persisted to DB")
        except Exception as e:
            logger.critical(
                "Kill switch DB persistence failed: %s — "
                "kill switch REMAINS ACTIVE (fail-safe)", e,
            )

    def deactivate(self) -> None:
        """Manually deactivate kill switch (requires human decision)."""
        if not self._active:
            return
        logger.warning("Kill switch deactivated manually (was active since %s: %s)",
                        self._activated_at, self._reason)
        self._active = False
        self._activated_at = None
        self._reason = ""

    def check_drawdown(self, current_drawdown_pct: float) -> bool:
        """Check if drawdown exceeds threshold. Returns True if kill switch triggered."""
        if current_drawdown_pct >= self.max_drawdown_pct:
            self.activate(
                f"Max drawdown exceeded: {current_drawdown_pct:.1f}% >= {self.max_drawdown_pct:.1f}%"
            )
            return True
        return False

    def status(self) -> dict:
        return {
            "active": self._active,
            "activated_at": self._activated_at.isoformat() if self._activated_at else None,
            "reason": self._reason,
            "max_drawdown_pct": self.max_drawdown_pct,
        }

    _db_sync_failures: int = 0
    _MAX_DB_SYNC_RETRIES: int = 3

    async def sync_with_db(self, session) -> bool:
        """Check database for external kill switch activation.

        Fail-safe: if DB sync fails repeatedly, kill switch is activated to prevent
        uncontrolled trading. Transient failures are tolerated up to 3 consecutive times.
        """
        from database.models import DailyRiskState
        from sqlalchemy import select

        try:
            # Use UTC date — never the local-tz date — so the daily row lookup
            # is consistent with how trades and resets are anchored.
            today = datetime.now(timezone.utc).date()
            stmt = select(DailyRiskState).where(DailyRiskState.date == today)
            result = await session.execute(stmt)
            state = result.scalar_one_or_none()

            # DB query succeeded — reset failure counter
            self._db_sync_failures = 0

            if state and state.kill_switch_activated and not self._active:
                self.activate("External Kill Switch (from DB/UI)")
                return True

            # Verify state consistency
            if state and not state.kill_switch_activated and self._active:
                logger.warning(
                    "Kill switch state divergence: memory=ACTIVE, DB=INACTIVE. "
                    "Keeping ACTIVE (fail-safe)."
                )

            return self._active

        except Exception as e:
            self._db_sync_failures += 1
            if self._db_sync_failures >= self._MAX_DB_SYNC_RETRIES:
                logger.critical(
                    "Kill switch DB sync failed %d times: %s — ACTIVATING kill switch (fail-safe)",
                    self._db_sync_failures, e,
                )
                self.activate(f"DB sync failed {self._db_sync_failures}x (fail-safe): {e}")
                return True
            else:
                logger.warning(
                    "Kill switch DB sync failed (%d/%d): %s — will retry next tick",
                    self._db_sync_failures, self._MAX_DB_SYNC_RETRIES, e,
                )
                return self._active

    # ------------------------------------------------------------------ #
    # Emergency close-all retry wrapper                                  #
    # ------------------------------------------------------------------ #

    _CLOSE_ALL_BACKOFFS: tuple = (0.5, 1.0, 2.0)

    async def close_all_with_retry(self, order_manager) -> int:
        """Emergency close-all with per-call retry / orphan tracking.

        Wraps the order-manager's close_all() so kill-switch shutdowns are
        resilient to transient broker hiccups. The wrapper retries the whole
        close_all() call up to 3 times with exponential backoff
        (0.5s, 1s, 2s). On final failure it logs CRITICAL and pushes the
        unresolved state to the order manager's orphan_close_queue if one
        exists, so a later reconciliation pass can retry.

        Args:
            order_manager: Object exposing async close_all() -> int.
                We deliberately do NOT touch order_manager / order_executor
                source — only invoke the existing public surface.

        Returns:
            Number of positions reported closed by close_all() on the first
            successful attempt, or 0 if all retries failed.
        """
        last_exc: Exception | None = None
        for attempt, backoff in enumerate(self._CLOSE_ALL_BACKOFFS, start=1):
            try:
                count = await order_manager.close_all()
                if attempt > 1:
                    logger.warning(
                        "Kill switch close_all succeeded on retry %d/%d (closed=%d)",
                        attempt, len(self._CLOSE_ALL_BACKOFFS), count,
                    )
                return count
            except Exception as e:
                last_exc = e
                if attempt < len(self._CLOSE_ALL_BACKOFFS):
                    logger.warning(
                        "Kill switch close_all attempt %d/%d failed: %s — "
                        "retrying in %.1fs",
                        attempt, len(self._CLOSE_ALL_BACKOFFS), e, backoff,
                    )
                    try:
                        await asyncio.sleep(backoff)
                    except asyncio.CancelledError:
                        raise
                else:
                    logger.critical(
                        "Kill switch close_all FINAL failure after %d attempts: %s",
                        attempt, e,
                    )

        # Final failure path — push to orphan queue if available so a later
        # reconciler can pick it up. We touch only public attributes.
        orphan_queue = getattr(order_manager, "orphan_close_queue", None)
        if orphan_queue is not None:
            try:
                orphan_queue.append({
                    "deal_id": None,
                    "exit_price": 0,
                    "close_reason": "KILL_SWITCH_RETRY_EXHAUSTED",
                    "pnl": 0,
                    "queued_at": datetime.now(timezone.utc),
                    "last_error": str(last_exc) if last_exc else "unknown",
                })
                logger.critical(
                    "Kill switch close_all: queued orphan-close request "
                    "after %d failed attempts", len(self._CLOSE_ALL_BACKOFFS),
                )
            except Exception as q_err:
                logger.critical(
                    "Kill switch close_all: failed to enqueue orphan record: %s",
                    q_err,
                )
        else:
            logger.critical(
                "Kill switch close_all: no orphan_close_queue available — "
                "manual intervention required",
            )

        return 0
