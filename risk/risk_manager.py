"""Risk Manager — central risk gate for all trade decisions."""

import asyncio
import logging
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, time, timezone

from .kill_switch import KillSwitch
from .position_sizing import PositionSizer
from .pre_trade_check import PreTradeChecker, CheckResult
from .portfolio_heat import PortfolioHeatManager
from .equity_curve_filter import EquityCurveFilter
from .position_sizer import AdvancedPositionSizer

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
        """Load all metrics from database (called at startup and for reconciliation).

        DB queries run OUTSIDE the lock so we never block other tasks behind I/O.
        Only the cache mutation is performed under the lock.
        """
        from database.repositories.trade_repo import TradeRepository

        repo = TradeRepository(session)
        # All async DB I/O happens lock-free.
        trades_today = await repo.count_today()
        consecutive_losses = await repo.get_consecutive_losses()
        weekly_pnl = await repo.get_weekly_pnl()
        daily_pnl = await repo.get_today_pnl()
        open_trades = await repo.get_open_trades()
        open_position_count = len(open_trades)
        sync_ts = _time.monotonic()

        # Critical section: only the in-memory mutation is guarded.
        async with self._lock:
            self.trades_today = trades_today
            self.consecutive_losses = consecutive_losses
            self.weekly_pnl = weekly_pnl
            self.daily_pnl = daily_pnl
            self.open_position_count = open_position_count
            self.last_db_sync = sync_ts

        logger.info(
            "Risk metrics cache loaded from DB: trades_today=%d, "
            "consecutive_losses=%d, daily_pnl=%.2f, weekly_pnl=%.2f",
            trades_today, consecutive_losses, daily_pnl, weekly_pnl,
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

    async def reset_daily(self) -> None:
        """Reset daily counters (daily_pnl, trades_today). Call at UTC midnight."""
        async with self._lock:
            self.daily_pnl = 0.0
            self.trades_today = 0
            logger.info("Risk metrics cache: daily counters reset")

    async def reset_weekly(self) -> None:
        """Reset weekly P&L. Call at Monday 00:00 UTC."""
        async with self._lock:
            self.weekly_pnl = 0.0
            logger.info("Risk metrics cache: weekly_pnl reset")

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
        max_leverage: float = 10.0,
        trading_start: time = time(8, 0),
        trading_end: time = time(22, 0),
        # Advanced risk components (Phase 9 -- all optional with safe defaults)
        kelly_mode: str = "half",
        atr_baseline: float = 3.0,
        max_portfolio_heat_pct: float = 5.0,
        equity_curve_ema_period: int = 20,
        equity_curve_filter_enabled: bool = True,
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
            max_leverage=max_leverage,
            trading_start=trading_start,
            trading_end=trading_end,
        )

        # State tracking
        self._equity_start: float = 0.0
        self._equity_peak: float = 0.0
        self._last_loss_time: datetime | None = None
        # Boundary tracking for daily/weekly resets (UTC)
        self._last_boundary_date: datetime | None = None

        # In-memory risk metrics cache (reduces DB queries per tick)
        self.metrics_cache = RiskMetricsCache()

        # Advanced risk components (Phase 9)
        self.advanced_sizer = AdvancedPositionSizer(
            base_risk_pct=max_risk_per_trade_pct,
            kelly_mode=kelly_mode,
            baseline_atr=atr_baseline,
            min_lot_size=min_lot_size,
            max_lot_size=max_lot_size,
        )
        self.portfolio_heat = PortfolioHeatManager(max_heat_pct=max_portfolio_heat_pct)
        self.equity_filter = EquityCurveFilter(
            ema_period=equity_curve_ema_period,
            enabled=equity_curve_filter_enabled,
        )

    def set_initial_equity(self, equity: float) -> None:
        """Set starting equity for the day (call at startup)."""
        self._equity_start = equity
        self._equity_peak = equity
        self._last_boundary_date = datetime.now(timezone.utc).date()
        logger.info("Risk manager initialized: equity=%.2f", equity)

    def reset_daily_peak(self, current_equity: float) -> None:
        """Reset the daily equity anchor (start + peak) to current equity.

        Should be called at the UTC day boundary so that daily-loss and
        drawdown limits do not leak across trading days.
        """
        self._equity_start = current_equity
        self._equity_peak = current_equity
        logger.info(
            "Daily equity anchor reset: start=%.2f, peak=%.2f",
            current_equity, current_equity,
        )

    async def on_day_boundary(self, current_equity: float) -> None:
        """Handle a UTC day boundary crossing.

        - Resets the daily equity anchor (start / peak)
        - Resets daily cache counters (trades_today, daily_pnl)
        - On Monday, additionally resets the weekly P&L

        Safe to call every tick — internally guarded by last-seen date so
        the work only runs once per UTC day.
        """
        today = datetime.now(timezone.utc).date()
        if self._last_boundary_date is not None and today <= self._last_boundary_date:
            return

        previous = self._last_boundary_date
        self._last_boundary_date = today

        self.reset_daily_peak(current_equity)
        await self.metrics_cache.reset_daily()

        # Monday == weekday 0 in Python. Reset weekly P&L at the first tick
        # of a new UTC week (or whenever we cross into a Monday).
        if today.weekday() == 0 and (previous is None or previous.weekday() != 0):
            await self.metrics_cache.reset_weekly()

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

    # -------------------------------------------------------------------------
    # Advanced risk methods (Phase 9)
    # -------------------------------------------------------------------------

    def update_trade_stats(self, win_rate: float, avg_win: float, avg_loss: float) -> None:
        """Update Kelly fraction from recent trade performance. Call periodically.

        Args:
            win_rate: Fraction of trades that are winners (0.0 to 1.0).
            avg_win:  Average winning trade magnitude (pips or currency).
            avg_loss: Average losing trade magnitude (positive).
        """
        self.advanced_sizer.set_trade_stats(win_rate, avg_win, avg_loss)
        logger.info(
            "Trade stats updated: win_rate=%.2f, avg_win=%.2f, avg_loss=%.2f",
            win_rate, avg_win, avg_loss,
        )

    def get_portfolio_heat(self) -> float:
        """Phase 10 interface: current portfolio heat percentage."""
        return self.portfolio_heat.get_heat(self._equity_peak or 10000.0)

    def is_trading_allowed(self) -> bool:
        """Phase 10 interface: False if equity curve filter blocks trading or kill switch active."""
        if self.kill_switch.is_active:
            return False
        return self.equity_filter.is_trading_allowed()

    def on_position_opened(self, risk_amount: float, account_balance: float) -> None:
        """Track new position for portfolio heat.

        Args:
            risk_amount:     Dollar risk of the new position (SL distance * lot_size).
            account_balance: Current account balance.
        """
        self.portfolio_heat.add_position(risk_amount, account_balance)

    def on_position_closed(self, risk_amount: float, account_balance: float, equity: float) -> None:
        """Update heat and equity curve on close.

        Args:
            risk_amount:     Dollar risk of the closed position.
            account_balance: Current account balance.
            equity:          Current equity (used for equity curve filter).
        """
        self.portfolio_heat.remove_position(risk_amount, account_balance)
        self.equity_filter.update(equity)

    # -------------------------------------------------------------------------
    # Core approve_trade method (extended with advanced checks)
    # -------------------------------------------------------------------------

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
        confidence: float = 0.7,
        atr: float = 3.0,
    ) -> RiskApproval:
        """Evaluate whether a trade should be executed.

        This is the SINGLE GATE that every trade must pass through.
        All 11 core checks plus 2 advanced checks (heat + equity curve) must pass.

        Args:
            direction:              Trade direction ("BUY" or "SELL").
            entry_price:            Planned entry price.
            stop_loss:              Planned stop loss price.
            current_equity:         Current account balance.
            available_margin:       Available margin.
            open_positions:         Count of currently open positions.
            trades_today:           Count of trades placed today.
            consecutive_losses:     Number of consecutive losing trades.
            current_spread:         Current market spread.
            has_open_same_direction: True if a position in same direction is open.
            weekly_loss_pct:        Current weekly loss as percentage.
            confidence:             ML model confidence (0.0--1.0) for Kelly tier.
            atr:                    Current ATR for volatility-based sizing.
        """
        now = datetime.now(timezone.utc)

        # Daily / weekly rollover (idempotent — runs once per UTC day)
        await self.on_day_boundary(current_equity)

        # Update drawdown tracking
        self.update_equity_peak(current_equity)
        current_drawdown = self.get_drawdown_pct(current_equity)
        daily_loss = self.get_daily_loss_pct(current_equity)

        # Check if kill switch should trigger
        self.kill_switch.check_drawdown(current_drawdown)

        # Calculate the FINAL lot size first — the margin/leverage checks must
        # validate the actual trade we will place, not an intermediate estimate
        # (was a circular dependency: margin computed from a lot_size that was
        # then recomputed further down).
        lot_size = self.sizer.calculate(current_equity, entry_price, stop_loss)
        estimated_margin = entry_price * lot_size * 0.05  # ~5% margin for Gold CFD
        notional_value = entry_price * lot_size

        # Run all 11 pre-trade checks (now includes leverage cap)
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
            notional_value=notional_value,
            equity=current_equity,
        )

        # Evaluate results of 11 checks
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

        # Check 12: Portfolio heat limit
        sl_distance = abs(entry_price - stop_loss)
        estimated_risk = sl_distance * lot_size
        if not self.portfolio_heat.can_add_position(estimated_risk, current_equity):
            current_heat = self.portfolio_heat.get_heat(current_equity)
            heat_msg = (
                f"[portfolio_heat] Heat {current_heat:.1f}% would exceed "
                f"{self.portfolio_heat.max_heat_pct:.1f}% limit"
            )
            logger.warning("Trade REJECTED: %s", heat_msg)
            heat_check = CheckResult(
                check_name="portfolio_heat",
                passed=False,
                message=heat_msg,
            )
            return RiskApproval(
                approved=False,
                lot_size=0.0,
                reason=heat_msg,
                checks=checks + [heat_check],
            )

        # Check 13: Equity curve filter
        if not self.equity_filter.is_trading_allowed():
            equity_vs_ema = self.equity_filter.get_equity_vs_ema()
            equity_msg = (
                f"[equity_curve_filter] Trading blocked: equity {equity_vs_ema} EMA"
            )
            logger.warning("Trade REJECTED: %s", equity_msg)
            equity_check = CheckResult(
                check_name="equity_curve_filter",
                passed=False,
                message=equity_msg,
            )
            return RiskApproval(
                approved=False,
                lot_size=0.0,
                reason=equity_msg,
                checks=checks + [equity_check],
            )

        # Use advanced sizer if Kelly fraction has been set (trade history available)
        sizing_reasoning = f"fixed_fractional risk={self.sizer.risk_per_trade_pct:.1f}%"
        if self.advanced_sizer._kelly_fraction > 0.0:
            sizing_result = self.advanced_sizer.get_position_size(
                confidence=confidence,
                atr=atr,
                account_balance=current_equity,
            )
            lot_size = sizing_result["lot_size"]
            sizing_reasoning = sizing_result["reasoning"]
            logger.info(
                "Advanced sizing applied: lot=%.2f, kelly=%.4f, tier=%s, atr_factor=%.2f",
                lot_size,
                sizing_result["kelly_fraction"],
                sizing_result["confidence_tier"],
                sizing_result["atr_factor"],
            )
        else:
            logger.info(
                "No Kelly data yet -- using fixed fractional sizing: lot=%.2f",
                lot_size,
            )

        logger.info(
            "Trade APPROVED: %s @ %.2f, SL=%.2f, lot=%.2f [%s]",
            direction, entry_price, stop_loss, lot_size, sizing_reasoning,
        )

        return RiskApproval(
            approved=True,
            lot_size=lot_size,
            reason=f"All 13 checks passed. Sizing: {sizing_reasoning}",
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
            "portfolio_heat": self.portfolio_heat.get_heat(self._equity_peak or 10000.0),
            "equity_curve_filter": self.equity_filter.get_equity_vs_ema(),
            "kelly_fraction": self.advanced_sizer._kelly_fraction,
        }
