"""Entry calculator — computes SL/TP and validates risk/reward ratio."""

from typing import TYPE_CHECKING

from shared.constants import (
    SL_ATR_MULTIPLIER,
    TP_ATR_MULTIPLIER,
    MIN_RR_RATIO,
)
from risk.position_sizing import PositionSizer

if TYPE_CHECKING:
    from strategy.regime_detector import MarketRegime


def calculate_sl_tp(
    direction: str,
    entry: float,
    atr: float,
    sl_multiplier: float = SL_ATR_MULTIPLIER,
    tp_multiplier: float = TP_ATR_MULTIPLIER,
) -> tuple[float, float]:
    """Calculate stop loss and take profit based on ATR.

    Args:
        direction: "BUY" or "SELL"
        entry: Entry price
        atr: Average True Range value
        sl_multiplier: ATR multiplier for stop loss (default 1.5)
        tp_multiplier: ATR multiplier for take profit (default 2.0)

    Returns:
        (stop_loss, take_profit) as rounded price levels
    """
    if direction == "BUY":
        sl = entry - (sl_multiplier * atr)
        tp = entry + (tp_multiplier * atr)
    else:
        sl = entry + (sl_multiplier * atr)
        tp = entry - (tp_multiplier * atr)

    return round(sl, 2), round(tp, 2)


def calculate_lot_size(
    equity: float,
    risk_pct: float,
    entry: float,
    stop_loss: float,
    min_lot: float = 0.01,
    max_lot: float = 10.0,
) -> float:
    """Calculate lot size using fixed fractional risk.

    Delegates to PositionSizer to avoid duplicate logic.

    Args:
        equity: Account equity in base currency
        risk_pct: Percentage of equity to risk (e.g. 1.0 = 1%)
        entry: Entry price
        stop_loss: Stop loss price
        min_lot: Minimum allowed lot size
        max_lot: Maximum allowed lot size

    Returns:
        Lot size rounded to 2 decimal places
    """
    sizer = PositionSizer(
        risk_per_trade_pct=risk_pct,
        min_lot_size=min_lot,
        max_lot_size=max_lot,
    )
    return sizer.calculate(equity=equity, entry_price=entry, stop_loss=stop_loss)


def risk_reward_ratio(entry: float, stop_loss: float, take_profit: float) -> float:
    """Return the risk/reward ratio (TP distance / SL distance)."""
    sl_dist = abs(entry - stop_loss)
    tp_dist = abs(entry - take_profit)
    if sl_dist <= 0:
        return 0.0
    return round(tp_dist / sl_dist, 2)


def is_valid_rr(
    entry: float,
    stop_loss: float,
    take_profit: float,
    min_rr: float = MIN_RR_RATIO,
) -> bool:
    """Return True if risk/reward ratio meets the minimum threshold."""
    return risk_reward_ratio(entry, stop_loss, take_profit) >= min_rr


def calculate_sl_tp_for_regime(
    direction: str,
    entry: float,
    atr: float,
    regime: "MarketRegime",
) -> tuple[float, float]:
    """Calculate SL/TP using regime-specific ATR multipliers.

    Args:
        direction: "BUY" or "SELL"
        entry: Entry price
        atr: Current ATR value
        regime: Current market regime

    Returns:
        (stop_loss, take_profit)
    """
    from strategy.regime_params import get_regime_params

    params = get_regime_params(regime)
    return calculate_sl_tp(
        direction=direction,
        entry=entry,
        atr=atr,
        sl_multiplier=params["sl_atr_multiplier"],
        tp_multiplier=params["tp_atr_multiplier"],
    )


def is_valid_rr_for_regime(
    entry: float,
    stop_loss: float,
    take_profit: float,
    regime: "MarketRegime",
) -> bool:
    """Check R:R against regime-specific minimum.

    Args:
        entry: Entry price
        stop_loss: Stop loss price
        take_profit: Take profit price
        regime: Current market regime

    Returns:
        True if R:R meets the regime-specific minimum
    """
    from strategy.regime_params import get_regime_params

    params = get_regime_params(regime)
    return risk_reward_ratio(entry, stop_loss, take_profit) >= params["rr_min"]
