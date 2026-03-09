"""Risk Manager — central risk gate for all trade decisions."""

import asyncio
import logging
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, time, timezone

from .kill_switch import KillSwitch
from .position_sizing import PositionSizer
from .pre_trade_check import PreTradeChecker, CheckResult

logger = logging.getLogger(__name__)


@dataclass
class RiskMetricsCache:
    """In-memory cache for risk metrics to avoid DB queries on every tick.

    Updated only on trade open/close events, not every tick.
    DB reconciliation runs periodically (every 5 minutes).
    """

    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    consecutive_losses: int = 0
    open_position_count: int = 0
    trades_today: int = 0
    last_trade_time: datetime | None = None
    last_db_sync: float = 0.0  # monotonic timestamp
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # Reconciliation interval in seconds
    RECONCILE_INTERVAL: float = 300.0  # 5 minutes

    @property
    def needs_reconciliation(self) -> bool:
        """Check if cache is stale and needs DB reconciliation."""
        if self.last_db_sync == 0.0:
            return True
        return (_time.monotonic() - self.last_db_sync) > self.RECONCILE_INTERVAL

    async def load_from_db(self, session) -> None:
        """Load all metrics from database (called at startup and for reconciliation)."""
        from database.repositories.trade_repo import TradeRepository

        async with self._lock:
            repo = TradeRepository(session)
            self.trades_today = await repo.count_today()
            self.consecutive_losses = await repo.get_consecutive_losses()
            self.weekly_pnl = await repo.get_weekly_pnl()
            self.daily_pnl = await repo.get_today_pnl()

            open_trades = await repo.get_open_trades()
            self.open_position_count = len(open_trades)

            self.last_db_sync = _time.monotonic()
            logger.info(
                "Risk metrics cache loaded from DB: trades_today=%d, "
                "consecutive_losses=%d, daily_pnl=%.2f, weekly_pnl=%.2f",
                self.trades_today, self.consecutive_losses,
                self.daily_pnl, self.weekly_pnl,
            )

    async def on_trade_opened(self, pnl_so_far: float = 0.0) -> None:
        """Update cache when a new trade is opened."""
        async with self._lock:
            self.trades_today += 1
            self.open_position_count += 1
            self.last_trade_time = datetime.now(timezone.utc)

    async def on_trade_closed(self, net_pnl: float) -> None:
        """Update cache when a trade is closed."""
        async with self._lock:
            self.open_position_count = max(0, self.open_position_count - 1)
            self.daily_pnl += net_pnl
            self.weekly_pnl += net_pnl

            if net_pnl < 0:
                self.consecutive_losses += 1
            else:
                self.consecutive_losses = 0

    def summary(self) -> dict:
        """Return cache state for monitoring."""
        return {
            "trades_today": self.trades_today,
            "consecutive_losses": self.consecutive_losses,
            "daily_pnl": round(self.daily_pnl, 2),
            "weekly_pnl": round(self.weekly_pnl, 2),
            "open_positions": self.open_position_count,
            "cache_age_seconds": round(_time.monotonic() - self.last_db_sync, 1),
        }


@dataclass
class RiskApproval:
    approved: bool
    lot_size: float
    reason: str
    checks: list[CheckResult]

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


class RiskManager:
    """Central risk management — must approve every trade before execution.

    Coordinates:
    - 11 pre-trade checks
    - Position sizing (fixed fractional)
    - Kill switch (emergency stop)
    - Drawdown monitoring
    """

    def __init__(
        self,
        max_risk_per_trade_pct: float = 1.0,
        max_daily_loss_pct: float = 5.0,
        max_weekly_loss_pct: float = 10.0,
        max_open_positions: int = 3,
        max_trades_per_day: int = 80,
        max_consecutive_losses: int = 5,
        cooldown_minutes: int = 30,
        max_spread: float = 5.0,
        kill_switch_drawdown_pct: float = 20.0,
        min_lot_size: float = 0.01,
        max_lot_size: float = 10.0,
        trading_start: time = time(8, 0),
        trading_end: time = time(22, 0),
    ) -> None:
        self.kill_switch = KillSwitch(max_drawdown_pct=kill_switch_drawdown_pct)
        self.sizer = PositionSizer(
            risk_per_trade_pct=max_risk_per_trade_pct,
            min_lot_size=min_lot_size,
            max_lot_size=max_lot_size,
        )
        self.checker = PreTradeChecker(
            max_daily_loss_pct=max_daily_loss_pct,
            max_weekly_loss_pct=max_weekly_loss_pct,
            max_open_positions=max_open_positions,
            max_trades_per_day=max_trades_per_day,
            max_consecutive_losses=max_consecutive_losses,
            cooldown_minutes=cooldown_minutes,
            max_spread=max_spread,
            kill_switch_drawdown_pct=kill_switch_drawdown_pct,
            trading_start=trading_start,
            trading_end=trading_end,
        )

        # State tracking
        self._equity_start: float = 0.0
        self._equity_peak: float = 0.0
        self._last_loss_time: datetime | None = None

        # In-memory risk metrics cache (reduces DB queries per tick)
        self.metrics_cache = RiskMetricsCache()

    def set_initial_equity(self, equity: float) -> None:
        """Set starting equity for the day (call at startup)."""
        self._equity_start = equity
        self._equity_peak = max(self._equity_peak, equity)
        logger.info("Risk manager initialized: equity=%.2f", equity)

    def update_equity_peak(self, current_equity: float) -> None:
        """Update equity peak for drawdown calculation."""
        if current_equity > self._equity_peak:
            self._equity_peak = current_equity

    def record_loss(self) -> None:
        """Record a losing trade (for cooldown tracking)."""
        self._last_loss_time = datetime.now(timezone.utc)

    def get_drawdown_pct(self, current_equity: float) -> float:
        """Calculate current drawdown from peak."""
        if self._equity_peak <= 0:
            return 0.0
        return ((self._equity_peak - current_equity) / self._equity_peak) * 100.0

    def get_daily_loss_pct(self, current_equity: float) -> float:
        """Calculate today's loss percentage from start."""
        if self._equity_start <= 0:
            return 0.0
        pnl = current_equity - self._equity_start
        if pnl >= 0:
            return 0.0
        return abs(pnl / self._equity_start) * 100.0

    async def approve_trade(
        self,
        direction: str,
        entry_price: float,
        stop_loss: float,
        current_equity: float,
        available_margin: float,
        open_positions: int,
        trades_today: int,
        consecutive_losses: int,
        current_spread: float,
        has_open_same_direction: bool,
        weekly_loss_pct: float = 0.0,
    ) -> RiskApproval:
        """Evaluate whether a trade should be executed.

        This is the SINGLE GATE that every trade must pass through.
        All 11 checks must pass for a trade to be approved.
        """
        now = datetime.now(timezone.utc)

        # Update drawdown tracking
        self.update_equity_peak(current_equity)
        current_drawdown = self.get_drawdown_pct(current_equity)
        daily_loss = self.get_daily_loss_pct(current_equity)

        # Check if kill switch should trigger
        self.kill_switch.check_drawdown(current_drawdown)

        # Estimate required margin (rough: entry_price * lot_size * margin_factor)
        # For now, use a simplified check
        preliminary_lot = self.sizer.calculate(current_equity, entry_price, stop_loss)
        estimated_margin = entry_price * preliminary_lot * 0.05  # ~5% margin for Gold CFD

        # Run all 11 pre-trade checks
        checks = self.checker.run_all(
            kill_switch_active=self.kill_switch.is_active,
            current_time=now,
            daily_loss_pct=daily_loss,
            weekly_loss_pct=weekly_loss_pct,
            open_positions=open_positions,
            trades_today=trades_today,
            consecutive_losses=consecutive_losses,
            last_loss_time=self._last_loss_time,
            current_spread=current_spread,
            available_margin=available_margin,
            required_margin=estimated_margin,
            has_open_same_direction=has_open_same_direction,
            current_drawdown_pct=current_drawdown,
        )

        # Evaluate results
        failed = [c for c in checks if not c.passed]

        if failed:
            reasons = "; ".join(f"[{c.check_name}] {c.message}" for c in failed)
            logger.warning("Trade REJECTED (%d check(s) failed): %s", len(failed), reasons)
            return RiskApproval(
                approved=False,
                lot_size=0.0,
                reason=reasons,
                checks=checks,
            )

        # All checks passed — calculate final lot size
        lot_size = self.sizer.calculate(current_equity, entry_price, stop_loss)

        logger.info(
            "Trade APPROVED: %s @ %.2f, SL=%.2f, lot=%.2f (risk=%.1f%%)",
            direction, entry_price, stop_loss, lot_size,
            self.sizer.risk_per_trade_pct,
        )

        return RiskApproval(
            approved=True,
            lot_size=lot_size,
            reason="All 11 checks passed",
            checks=checks,
        )

    async def sync_kill_switch(self, session) -> bool:
        """Synchronize the internal kill switch state with the database.

        Fail-safe: if sync fails, kill switch activates.
        """
        return await self.kill_switch.sync_with_db(session)

    def force_kill_switch(self, reason: str) -> None:
        """Force-activate the kill switch (no DB required)."""
        self.kill_switch.activate(reason)

    def status(self) -> dict:
        """Get current risk status summary."""
        return {
            "kill_switch": self.kill_switch.status(),
            "equity_start": self._equity_start,
            "equity_peak": self._equity_peak,
            "last_loss_time": self._last_loss_time.isoformat() if self._last_loss_time else None,
            "metrics_cache": self.metrics_cache.summary(),
        }
