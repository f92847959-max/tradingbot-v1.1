"""Portfolio Heat Manager -- Phase 9 Plan 03.

Tracks total open risk across all positions and enforces a maximum heat limit.
'Portfolio heat' = total open risk as a percentage of account balance.

No async, no database imports. Pure in-memory tracking.
"""

import logging

logger = logging.getLogger(__name__)


class PortfolioHeatManager:
    """Track and enforce portfolio-wide heat (total open risk percentage).

    Args:
        max_heat_pct: Maximum allowed portfolio heat as percentage (default 5.0%).
                      Example: 5.0 means max 5% of account balance at risk at once.
    """

    def __init__(self, max_heat_pct: float = 5.0) -> None:
        self.max_heat_pct = max_heat_pct
        self._open_risk_total: float = 0.0  # Sum of all open position risk amounts

    def add_position(self, risk_amount: float, account_balance: float) -> None:
        """Register a newly opened position's risk amount.

        Args:
            risk_amount:     Dollar risk of the new position (entry - SL) * lot_size.
            account_balance: Current account balance for heat calculation.
        """
        self._open_risk_total += risk_amount
        heat = self.get_heat(account_balance)
        logger.info(
            "Position added: risk=%.2f, heat=%.2f%% / %.2f%%",
            risk_amount, heat, self.max_heat_pct,
        )

    def remove_position(self, risk_amount: float, account_balance: float) -> None:
        """Deregister a closed position's risk amount.

        Clamps to 0 -- never goes negative even if remove > current total.

        Args:
            risk_amount:     Dollar risk of the closed position.
            account_balance: Current account balance for heat calculation.
        """
        self._open_risk_total = max(0.0, self._open_risk_total - risk_amount)
        logger.info(
            "Position removed: risk=%.2f, heat=%.2f%%",
            risk_amount, self.get_heat(account_balance),
        )

    def get_heat(self, account_balance: float) -> float:
        """Return current portfolio heat as percentage.

        Args:
            account_balance: Current account balance.

        Returns:
            Heat percentage (0.0 when balance is 0 or no positions open).
        """
        if account_balance <= 0:
            return 0.0
        return (self._open_risk_total / account_balance) * 100.0

    def can_add_position(self, risk_amount: float, account_balance: float) -> bool:
        """Check if adding a new position would stay within the heat limit.

        Args:
            risk_amount:     Dollar risk of the proposed position.
            account_balance: Current account balance.

        Returns:
            True if trade is allowed, False if it would breach max_heat_pct.
        """
        if account_balance <= 0:
            return False
        projected = ((self._open_risk_total + risk_amount) / account_balance) * 100.0
        return projected <= self.max_heat_pct

    def get_remaining_heat(self, account_balance: float) -> float:
        """Return dollar amount of risk capacity remaining before max heat.

        Args:
            account_balance: Current account balance.

        Returns:
            Dollar amount available to risk (0.0 if at or above max heat).
        """
        max_risk = account_balance * (self.max_heat_pct / 100.0)
        return max(0.0, max_risk - self._open_risk_total)

    def reset(self) -> None:
        """Clear all tracked positions to 0 (call at session start or after liquidation)."""
        self._open_risk_total = 0.0
        logger.info("Portfolio heat reset to 0")
