"""Kelly Criterion position sizing calculator.

Provides kelly_fraction, half_kelly, quarter_kelly, and compute_from_trades.
All methods are pure functions (no DB access, no async).

Kelly formula:  f* = win_rate - (1 - win_rate) / (avg_win / avg_loss)
Result is clamped to [0.0, MAX_KELLY] where MAX_KELLY = 0.3 (30% max risk).

Note on MAX_KELLY: The standard Kelly Criterion can suggest very large position
sizes that are impractical.  We cap at 0.3 (30%) as a conservative hard limit.
This matches the plan spec where kelly_fraction(0.6, 2.0, 1.0) == 0.3.
"""

import logging
from typing import Sequence

logger = logging.getLogger(__name__)

# Hard cap on Kelly fraction -- never risk more than 30% of account per trade.
MAX_KELLY: float = 0.3


class KellyCalculator:
    """Kelly Criterion calculator for optimal position sizing.

    All methods are stateless and pure -- no DB access, no async I/O.
    """

    # -------------------------------------------------------------------------
    # Core Kelly fraction methods
    # -------------------------------------------------------------------------

    def kelly_fraction(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
    ) -> float:
        """Calculate the full Kelly fraction.

        Formula: f* = win_rate - (1 - win_rate) / (avg_win / avg_loss)

        Args:
            win_rate:  Fraction of trades that are winners (0.0 to 1.0).
            avg_win:   Average winning trade size (pips or currency units).
            avg_loss:  Average losing trade size (pips or currency units, positive).

        Returns:
            Kelly fraction in [0.0, MAX_KELLY].  Returns 0.0 for degenerate
            inputs or when there is no positive edge.
        """
        if win_rate <= 0.0 or avg_loss <= 0.0:
            logger.debug(
                "Kelly degenerate input: win_rate=%.4f, avg_loss=%.4f -- returning 0.0",
                win_rate,
                avg_loss,
            )
            return 0.0

        loss_rate = 1.0 - win_rate
        reward_risk_ratio = avg_win / avg_loss
        raw_fraction = win_rate - loss_rate / reward_risk_ratio

        # Clamp to [0.0, MAX_KELLY]
        fraction = max(0.0, min(MAX_KELLY, raw_fraction))

        logger.debug(
            "Kelly fraction: win_rate=%.4f, avg_win=%.4f, avg_loss=%.4f, "
            "R=%.4f, raw=%.4f, clamped=%.4f",
            win_rate,
            avg_win,
            avg_loss,
            reward_risk_ratio,
            raw_fraction,
            fraction,
        )
        return fraction

    def half_kelly(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
    ) -> float:
        """Return 50% of the full Kelly fraction (conservative sizing).

        Args:
            win_rate: Fraction of winning trades.
            avg_win:  Average winning trade magnitude.
            avg_loss: Average losing trade magnitude.

        Returns:
            Half-Kelly fraction in [0.0, MAX_KELLY / 2].
        """
        fraction = self.kelly_fraction(win_rate, avg_win, avg_loss) * 0.5
        logger.debug("Half-Kelly: %.4f", fraction)
        return fraction

    def quarter_kelly(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
    ) -> float:
        """Return 25% of the full Kelly fraction (very conservative sizing).

        Args:
            win_rate: Fraction of winning trades.
            avg_win:  Average winning trade magnitude.
            avg_loss: Average losing trade magnitude.

        Returns:
            Quarter-Kelly fraction in [0.0, MAX_KELLY / 4].
        """
        fraction = self.kelly_fraction(win_rate, avg_win, avg_loss) * 0.25
        logger.debug("Quarter-Kelly: %.4f", fraction)
        return fraction

    # -------------------------------------------------------------------------
    # Trade history analysis
    # -------------------------------------------------------------------------

    def compute_from_trades(self, trades: list) -> float:
        """Compute half-Kelly fraction from a list of trade dicts.

        Each trade dict must have keys:
          - "net_pnl": float  (positive = win, negative = loss)
          - "pnl_pips": float (pip-level P&L, used for avg_win/avg_loss calc)

        Requires at least 30 trades for statistical reliability.

        Args:
            trades: List of trade dictionaries.

        Returns:
            Half-Kelly fraction, or 0.0 if insufficient data.
        """
        if len(trades) < 30:
            logger.info(
                "compute_from_trades: only %d trades (need >= 30) -- returning 0.0",
                len(trades),
            )
            return 0.0

        wins = [t for t in trades if t.get("net_pnl", 0.0) > 0]
        losses = [t for t in trades if t.get("net_pnl", 0.0) < 0]

        if not wins or not losses:
            logger.info(
                "compute_from_trades: no wins (%d) or no losses (%d) -- returning 0.0",
                len(wins),
                len(losses),
            )
            return 0.0

        total = len(trades)
        win_rate = len(wins) / total
        avg_win = sum(abs(t.get("pnl_pips", 0.0)) for t in wins) / len(wins)
        avg_loss = sum(abs(t.get("pnl_pips", 0.0)) for t in losses) / len(losses)

        if avg_loss <= 0:
            return 0.0

        fraction = self.half_kelly(win_rate, avg_win, avg_loss)
        logger.info(
            "compute_from_trades: %d trades, win_rate=%.4f, avg_win=%.4f, "
            "avg_loss=%.4f, half_kelly=%.4f",
            total,
            win_rate,
            avg_win,
            avg_loss,
            fraction,
        )
        return fraction
