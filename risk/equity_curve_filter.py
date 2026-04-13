"""Equity Curve Filter -- Phase 9 Plan 03.

Stops new trades when the equity curve drops below its EMA.
This prevents trading during drawdown periods, reducing catastrophic losses.

No async, no database imports. Pure in-memory EMA calculation.
"""

import logging

logger = logging.getLogger(__name__)


class EquityCurveFilter:
    """EMA-based equity curve filter.

    Trading is allowed only when current equity >= EMA of recent equity.
    With insufficient data (<ema_period points), defaults to allowed=True.

    Args:
        ema_period: Lookback period for the EMA calculation (default 20).
        enabled:    If False, always returns is_allowed=True (disable filter).
    """

    def __init__(self, ema_period: int = 20, enabled: bool = True) -> None:
        self.ema_period = ema_period
        self.enabled = enabled
        self._equity_history: list = []
        self._ema: float = 0.0

    def update(self, equity: float) -> bool:
        """Add an equity data point, recalculate EMA, return is_trading_allowed.

        Args:
            equity: Current account equity value.

        Returns:
            True if trading is allowed after this update, False if blocked.
        """
        self._equity_history.append(equity)

        if len(self._equity_history) >= self.ema_period:
            # EMA multiplier
            k = 2.0 / (self.ema_period + 1)
            if self._ema == 0.0:
                # Seed EMA with SMA of first ema_period points
                self._ema = sum(self._equity_history[-self.ema_period:]) / self.ema_period
            else:
                self._ema = equity * k + self._ema * (1 - k)

        return self.is_trading_allowed()

    def is_trading_allowed(self) -> bool:
        """Check if trading is currently allowed based on equity vs EMA.

        Returns:
            True if trading is allowed, False if equity is below EMA.
            Always returns True when filter is disabled or insufficient data.
        """
        if not self.enabled:
            return True
        if len(self._equity_history) < self.ema_period:
            return True  # Insufficient data -- benefit of the doubt
        current_equity = self._equity_history[-1]
        allowed = current_equity >= self._ema
        if not allowed:
            logger.warning(
                "Equity curve filter: equity=%.2f < EMA=%.2f -- trading restricted",
                current_equity, self._ema,
            )
        return allowed

    def get_ema(self) -> float:
        """Return current EMA value (0.0 if not yet seeded)."""
        return self._ema

    def get_equity_vs_ema(self) -> str:
        """Return descriptive string of equity position relative to EMA.

        Returns:
            "above"             -- equity >= EMA (trading allowed)
            "below"             -- equity < EMA (trading restricted)
            "insufficient_data" -- fewer than ema_period points recorded
        """
        if len(self._equity_history) < self.ema_period:
            return "insufficient_data"
        return "above" if self._equity_history[-1] >= self._ema else "below"

    def reset(self) -> None:
        """Clear all history and reset EMA to 0 (call at session restart)."""
        self._equity_history.clear()
        self._ema = 0.0
        logger.info("Equity curve filter reset")
