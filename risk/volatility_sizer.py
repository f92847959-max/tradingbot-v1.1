"""Volatility-based position sizer using ATR normalization.

Adjusts lot size inversely proportional to market volatility:
    factor = baseline_atr / current_atr

High ATR  => smaller factor => smaller position (protect capital in volatile markets)
Low ATR   => larger factor  => larger position  (take full advantage of calm markets)

Factor is clamped to [min_scale, max_scale] to prevent extreme adjustments.
Pure calculation class -- no DB access, no async I/O.
"""

import logging

logger = logging.getLogger(__name__)


class VolatilitySizer:
    """ATR-based position size adjuster.

    Args:
        baseline_atr: 'Normal' ATR value for XAUUSD on 5-minute candles (~3.0).
                      Positions at this ATR are not scaled up or down.
        min_scale:    Minimum scaling factor (floor). Default 0.25 -- never
                      go below 25% of the base lot size.
        max_scale:    Maximum scaling factor (ceiling). Default 1.5 -- never
                      exceed 150% of the base lot size.
    """

    def __init__(
        self,
        baseline_atr: float = 3.0,
        min_scale: float = 0.25,
        max_scale: float = 1.5,
    ) -> None:
        self.baseline_atr = baseline_atr
        self.min_scale = min_scale
        self.max_scale = max_scale

    def calculate_atr_factor(self, atr: float) -> float:
        """Calculate the ATR scaling factor.

        factor = baseline_atr / max(atr, 0.01)
        Clamped to [min_scale, max_scale].

        Args:
            atr: Current ATR value (must be >= 0).

        Returns:
            Scaling factor in [min_scale, max_scale].
        """
        safe_atr = max(atr, 0.01)  # Avoid division by zero
        raw_factor = self.baseline_atr / safe_atr
        factor = max(self.min_scale, min(self.max_scale, raw_factor))

        logger.debug(
            "ATR factor: atr=%.4f, baseline=%.4f, raw=%.4f, clamped=%.4f",
            atr,
            self.baseline_atr,
            raw_factor,
            factor,
        )
        return factor

    def adjust_lot_size(
        self,
        base_lot: float,
        atr: float,
        min_lot_size: float = 0.01,
    ) -> float:
        """Apply ATR scaling to a base lot size.

        Args:
            base_lot:     Base lot size before volatility adjustment.
            atr:          Current ATR value.
            min_lot_size: Minimum allowed lot size (hard floor). Default 0.01.

        Returns:
            Adjusted lot size, rounded to 2 decimal places and >= min_lot_size.
        """
        factor = self.calculate_atr_factor(atr)
        adjusted = max(min_lot_size, round(base_lot * factor, 2))

        logger.debug(
            "Lot adjustment: base=%.4f, atr_factor=%.4f, adjusted=%.2f",
            base_lot,
            factor,
            adjusted,
        )
        return adjusted
