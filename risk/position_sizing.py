"""Position sizing — calculate lot size based on risk parameters."""

import logging

logger = logging.getLogger(__name__)


class PositionSizer:
    """Fixed fractional position sizing.

    Risk a fixed percentage of equity per trade.
    Lot size = (equity * risk_pct) / (SL distance in price * pip_value)
    """

    def __init__(
        self,
        risk_per_trade_pct: float = 1.0,
        min_lot_size: float = 0.01,
        max_lot_size: float = 10.0,
    ) -> None:
        self.risk_per_trade_pct = risk_per_trade_pct
        self.min_lot_size = min_lot_size
        self.max_lot_size = max_lot_size

    def calculate(
        self,
        equity: float,
        entry_price: float,
        stop_loss: float,
    ) -> float:
        """Calculate lot size for a trade.

        Args:
            equity: Current account equity in EUR
            entry_price: Planned entry price
            stop_loss: Planned stop loss price

        Returns:
            Lot size (clamped to min/max)
        """
        sl_distance = abs(entry_price - stop_loss)

        if sl_distance <= 0:
            logger.warning("SL distance is zero, using minimum lot size")
            return self.min_lot_size

        # Risk amount in EUR
        risk_amount = equity * (self.risk_per_trade_pct / 100.0)

        # For Gold CFD: 1 lot = 1 oz, price movement of $1 = $1 per lot
        # SL distance in USD (Gold is priced in USD)
        lot_size = risk_amount / sl_distance

        # Clamp to bounds
        lot_size = max(self.min_lot_size, min(self.max_lot_size, lot_size))

        # Round to 2 decimal places
        lot_size = round(lot_size, 2)

        logger.debug(
            "Position sizing: equity=%.2f, risk=%.2f%%, sl_dist=%.2f, lot=%.2f",
            equity, self.risk_per_trade_pct, sl_distance, lot_size,
        )
        return lot_size

    def calculate_with_atr_guard(
        self,
        equity: float,
        entry_price: float,
        stop_loss: float,
        atr: float,
        max_atr_for_trading: float = 5.0,
    ) -> float:
        """Position sizing with ATR guard for extreme volatility.

        When ATR exceeds max_atr_for_trading, returns minimum lot size
        instead of calculated size. This prevents large positions during
        extreme market events.

        Args:
            equity: Account equity
            entry_price: Planned entry price
            stop_loss: Planned stop loss price
            atr: Current ATR-14 value
            max_atr_for_trading: Maximum ATR threshold (default 5.0 for Gold)

        Returns:
            Lot size (minimum if ATR exceeds guard)
        """
        if atr > max_atr_for_trading:
            logger.warning(
                "ATR %.2f exceeds max %.2f -- using minimum lot size",
                atr, max_atr_for_trading,
            )
            return self.min_lot_size

        return self.calculate(equity, entry_price, stop_loss)
