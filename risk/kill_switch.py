"""Kill Switch — emergency system to stop all trading and close positions."""

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

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def reason(self) -> str:
        return self._reason

    def activate(self, reason: str) -> None:
        """Activate kill switch. All trading stops immediately."""
        if self._active:
            return
        self._active = True
        self._activated_at = datetime.now(timezone.utc)
        self._reason = reason
        logger.critical("KILL SWITCH ACTIVATED: %s", reason)

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
        import datetime as _dt

        try:
            today = _dt.date.today()
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
