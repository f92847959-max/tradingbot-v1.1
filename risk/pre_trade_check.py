"""Pre-trade checks — 11 safety checks before any trade is executed."""

import logging
from dataclasses import dataclass
from datetime import datetime, time

from shared.utils import is_trading_hours

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    passed: bool
    check_name: str
    message: str


class PreTradeChecker:
    """Runs all 11 pre-trade checks before a trade is approved.

    All checks must pass for a trade to be executed.
    """

    def __init__(
        self,
        max_daily_loss_pct: float = 5.0,
        max_weekly_loss_pct: float = 10.0,
        max_open_positions: int = 3,
        max_trades_per_day: int = 80,
        max_consecutive_losses: int = 5,
        cooldown_minutes: int = 30,
        max_spread: float = 5.0,
        kill_switch_drawdown_pct: float = 20.0,
        trading_start: time = time(8, 0),
        trading_end: time = time(22, 0),
    ) -> None:
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_weekly_loss_pct = max_weekly_loss_pct
        self.max_open_positions = max_open_positions
        self.max_trades_per_day = max_trades_per_day
        self.max_consecutive_losses = max_consecutive_losses
        self.cooldown_minutes = cooldown_minutes
        self.max_spread = max_spread
        self.kill_switch_drawdown_pct = kill_switch_drawdown_pct
        self.trading_start = trading_start
        self.trading_end = trading_end

    def run_all(
        self,
        kill_switch_active: bool,
        current_time: datetime,
        daily_loss_pct: float,
        weekly_loss_pct: float,
        open_positions: int,
        trades_today: int,
        consecutive_losses: int,
        last_loss_time: datetime | None,
        current_spread: float,
        available_margin: float,
        required_margin: float,
        has_open_same_direction: bool,
        current_drawdown_pct: float,
    ) -> list[CheckResult]:
        """Run all 11 pre-trade checks. Returns list of results."""
        results = []

        # 1. Kill Switch
        results.append(self._check_kill_switch(kill_switch_active))

        # 2. Trading Hours
        results.append(self._check_trading_hours(current_time))

        # 3. Daily Loss Limit
        results.append(self._check_daily_loss(daily_loss_pct))

        # 4. Weekly Loss Limit
        results.append(self._check_weekly_loss(weekly_loss_pct))

        # 5. Max Open Positions
        results.append(self._check_max_positions(open_positions))

        # 6. Max Trades Per Day
        results.append(self._check_max_trades_today(trades_today))

        # 7. Loss Streak + Cooldown
        results.append(self._check_loss_streak(consecutive_losses, last_loss_time, current_time))

        # 8. Spread
        results.append(self._check_spread(current_spread))

        # 9. Margin
        results.append(self._check_margin(available_margin, required_margin))

        # 10. Duplicate Direction
        results.append(self._check_duplicate(has_open_same_direction))

        # 11. Drawdown
        results.append(self._check_drawdown(current_drawdown_pct))

        return results

    def _check_kill_switch(self, active: bool) -> CheckResult:
        if active:
            return CheckResult(False, "kill_switch", "Kill switch is active — no trading allowed")
        return CheckResult(True, "kill_switch", "OK")

    def _check_trading_hours(self, now: datetime) -> CheckResult:
        if not is_trading_hours(now):
            if now.weekday() >= 5:
                return CheckResult(False, "trading_hours", f"Weekend — no trading (day={now.strftime('%A')})")
            return CheckResult(
                False, "trading_hours",
                f"Outside trading hours, current: {now.strftime('%H:%M')}"
            )
        return CheckResult(True, "trading_hours", "OK")

    def _check_daily_loss(self, daily_loss_pct: float) -> CheckResult:
        if daily_loss_pct >= self.max_daily_loss_pct:
            return CheckResult(
                False, "daily_loss",
                f"Daily loss limit reached: {daily_loss_pct:.1f}% >= {self.max_daily_loss_pct:.1f}%"
            )
        return CheckResult(True, "daily_loss", f"OK ({daily_loss_pct:.1f}% / {self.max_daily_loss_pct:.1f}%)")

    def _check_weekly_loss(self, weekly_loss_pct: float) -> CheckResult:
        if weekly_loss_pct >= self.max_weekly_loss_pct:
            return CheckResult(
                False, "weekly_loss",
                f"Weekly loss limit reached: {weekly_loss_pct:.1f}% >= {self.max_weekly_loss_pct:.1f}%"
            )
        return CheckResult(True, "weekly_loss", f"OK ({weekly_loss_pct:.1f}% / {self.max_weekly_loss_pct:.1f}%)")

    def _check_max_positions(self, open_positions: int) -> CheckResult:
        if open_positions >= self.max_open_positions:
            return CheckResult(
                False, "max_positions",
                f"Max open positions reached: {open_positions} >= {self.max_open_positions}"
            )
        return CheckResult(True, "max_positions", f"OK ({open_positions} / {self.max_open_positions})")

    def _check_max_trades_today(self, trades_today: int) -> CheckResult:
        if trades_today >= self.max_trades_per_day:
            return CheckResult(
                False, "max_trades_today",
                f"Max daily trades reached: {trades_today} >= {self.max_trades_per_day}"
            )
        return CheckResult(True, "max_trades_today", f"OK ({trades_today} / {self.max_trades_per_day})")

    def _check_loss_streak(
        self, consecutive_losses: int, last_loss_time: datetime | None, now: datetime
    ) -> CheckResult:
        if consecutive_losses >= self.max_consecutive_losses:
            # Check if cooldown has passed
            if last_loss_time:
                elapsed = (now - last_loss_time).total_seconds() / 60
                if elapsed < self.cooldown_minutes:
                    remaining = self.cooldown_minutes - elapsed
                    return CheckResult(
                        False, "loss_streak",
                        f"Loss streak cooldown: {consecutive_losses} losses, {remaining:.0f}min remaining"
                    )
            # Cooldown passed — allow trading again
            return CheckResult(True, "loss_streak", f"Cooldown passed after {consecutive_losses} losses")

        return CheckResult(True, "loss_streak", f"OK ({consecutive_losses} / {self.max_consecutive_losses})")

    def _check_spread(self, current_spread: float) -> CheckResult:
        if current_spread > self.max_spread:
            return CheckResult(
                False, "spread",
                f"Spread too high: {current_spread:.1f} > {self.max_spread:.1f}"
            )
        return CheckResult(True, "spread", f"OK ({current_spread:.1f} / {self.max_spread:.1f})")

    def _check_margin(self, available: float, required: float) -> CheckResult:
        if available < required:
            return CheckResult(
                False, "margin",
                f"Insufficient margin: {available:.2f} < {required:.2f}"
            )
        return CheckResult(True, "margin", f"OK (available: {available:.2f})")

    def _check_duplicate(self, has_open_same_direction: bool) -> CheckResult:
        if has_open_same_direction:
            return CheckResult(
                False, "duplicate",
                "Already have an open position in the same direction"
            )
        return CheckResult(True, "duplicate", "OK")

    def _check_drawdown(self, current_drawdown_pct: float) -> CheckResult:
        if current_drawdown_pct >= self.kill_switch_drawdown_pct:
            return CheckResult(
                False, "drawdown",
                f"Drawdown at kill switch level: {current_drawdown_pct:.1f}% >= {self.kill_switch_drawdown_pct:.1f}%"
            )
        return CheckResult(True, "drawdown", f"OK ({current_drawdown_pct:.1f}% / {self.kill_switch_drawdown_pct:.1f}%)")
