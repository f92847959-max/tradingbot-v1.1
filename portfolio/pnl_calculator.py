"""P&L calculator for Gold CFD trades."""

from shared.constants import PIP_SIZE, CONTRACT_SIZE


def gross_pnl(
    direction: str,
    entry: float,
    exit_price: float,
    lot_size: float,
) -> float:
    """Calculate gross P&L before spread/commission costs.

    Args:
        direction: "BUY" or "SELL"
        entry: Entry price
        exit_price: Exit price
        lot_size: Position size in lots (1 lot = 1 oz Gold)

    Returns:
        Gross P&L in USD
    """
    if direction == "BUY":
        price_diff = exit_price - entry
    else:
        price_diff = entry - exit_price
    return round(price_diff * lot_size * CONTRACT_SIZE, 4)


def net_pnl(
    gross: float,
    spread_cost: float = 0.0,
    commission: float = 0.0,
) -> float:
    """Calculate net P&L after costs.

    Args:
        gross: Gross P&L in USD
        spread_cost: Cost of spread at entry (half-spread * lot_size)
        commission: Any broker commission

    Returns:
        Net P&L in USD
    """
    return round(gross - spread_cost - commission, 4)


def spread_cost(spread_pips: float, lot_size: float) -> float:
    """Calculate the cost of the spread for a given position.

    Args:
        spread_pips: Spread in pips at time of entry
        lot_size: Position size in lots

    Returns:
        Spread cost in USD
    """
    return round(spread_pips * PIP_SIZE * lot_size * CONTRACT_SIZE, 4)


def pips(direction: str, entry: float, exit_price: float) -> float:
    """Return P&L in pips."""
    if direction == "BUY":
        return round((exit_price - entry) / PIP_SIZE, 1)
    return round((entry - exit_price) / PIP_SIZE, 1)


def breakeven_price(direction: str, entry: float, spread_pips: float) -> float:
    """Return the price at which the trade breaks even (accounting for spread)."""
    spread_price = spread_pips * PIP_SIZE
    if direction == "BUY":
        return round(entry + spread_price, 2)
    return round(entry - spread_price, 2)
