"""Performance metrics for the trading system."""

import math
from typing import Sequence


def win_rate(trades: Sequence[dict]) -> float:
    """Fraction of trades that were profitable.

    Args:
        trades: List of trade dicts with 'net_pnl' key.

    Returns:
        Win rate 0.0-1.0. Returns 0.0 if no closed trades.
    """
    closed = [t for t in trades if t.get("net_pnl") is not None]
    if not closed:
        return 0.0
    winners = sum(1 for t in closed if float(t["net_pnl"]) > 0)
    return round(winners / len(closed), 4)


def profit_factor(trades: Sequence[dict]) -> float:
    """Ratio of gross profit to gross loss.

    A profit factor > 1.0 means the system is profitable.
    Returns float('inf') if there are no losing trades.

    Args:
        trades: List of trade dicts with 'net_pnl' key.
    """
    closed = [t for t in trades if t.get("net_pnl") is not None]
    total_profit = sum(float(t["net_pnl"]) for t in closed if float(t["net_pnl"]) > 0)
    total_loss = sum(abs(float(t["net_pnl"])) for t in closed if float(t["net_pnl"]) < 0)
    if total_loss == 0:
        return float("inf") if total_profit > 0 else 0.0
    return round(total_profit / total_loss, 4)


def max_drawdown(equity_curve: Sequence[float]) -> float:
    """Maximum drawdown from peak to trough, as a percentage.

    Args:
        equity_curve: List of equity values over time.

    Returns:
        Max drawdown percentage (0.0-100.0). 0.0 if no drawdown.
    """
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        if peak > 0:
            dd = (peak - value) / peak * 100.0
            if dd > max_dd:
                max_dd = dd
    return round(max_dd, 4)


def sharpe_ratio(
    returns: Sequence[float],
    risk_free: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Annualised Sharpe ratio.

    Args:
        returns: Sequence of periodic returns (e.g. daily P&L / starting equity).
        risk_free: Risk-free rate per period (default 0.0).
        periods_per_year: Trading periods per year (252 for daily).

    Returns:
        Annualised Sharpe ratio. Returns 0.0 if insufficient data.
    """
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free for r in returns]
    mean = sum(excess) / len(excess)
    variance = sum((r - mean) ** 2 for r in excess) / (len(excess) - 1)
    std = math.sqrt(variance) if variance > 0 else 0.0
    if std == 0:
        return 0.0
    return round((mean / std) * math.sqrt(periods_per_year), 4)


def sortino_ratio(
    returns: Sequence[float],
    risk_free: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Annualised Sortino ratio (downside deviation only).

    Args:
        returns: Sequence of periodic returns.
        risk_free: Risk-free rate per period.
        periods_per_year: Trading periods per year.

    Returns:
        Annualised Sortino ratio. Returns 0.0 if insufficient data.
    """
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free for r in returns]
    mean = sum(excess) / len(excess)
    downside = [r for r in excess if r < 0]
    if not downside:
        return float("inf") if mean > 0 else 0.0
    downside_var = sum(r ** 2 for r in downside) / len(downside)
    downside_std = math.sqrt(downside_var)
    if downside_std == 0:
        return 0.0
    return round((mean / downside_std) * math.sqrt(periods_per_year), 4)


def average_win(trades: Sequence[dict]) -> float:
    """Average P&L of winning trades."""
    winners = [float(t["net_pnl"]) for t in trades
               if t.get("net_pnl") is not None and float(t["net_pnl"]) > 0]
    return round(sum(winners) / len(winners), 4) if winners else 0.0


def average_loss(trades: Sequence[dict]) -> float:
    """Average P&L of losing trades (returned as negative number)."""
    losers = [float(t["net_pnl"]) for t in trades
              if t.get("net_pnl") is not None and float(t["net_pnl"]) < 0]
    return round(sum(losers) / len(losers), 4) if losers else 0.0


def expectancy(trades: Sequence[dict]) -> float:
    """Expected P&L per trade.

    Expectancy = (win_rate * avg_win) + (loss_rate * avg_loss)
    Positive expectancy means the system is profitable on average.
    """
    wr = win_rate(trades)
    avg_w = average_win(trades)
    avg_l = average_loss(trades)
    return round(wr * avg_w + (1 - wr) * avg_l, 4)


def summary(trades: Sequence[dict], equity_curve: Sequence[float] | None = None) -> dict:
    """Return a dict with all key performance metrics."""
    returns = []
    if equity_curve and len(equity_curve) >= 2:
        start = equity_curve[0]
        if start > 0:
            returns = [(equity_curve[i] - equity_curve[i - 1]) / start
                       for i in range(1, len(equity_curve))]

    return {
        "total_trades": len(trades),
        "win_rate": win_rate(trades),
        "profit_factor": profit_factor(trades),
        "max_drawdown_pct": max_drawdown(equity_curve) if equity_curve else 0.0,
        "sharpe_ratio": sharpe_ratio(returns),
        "sortino_ratio": sortino_ratio(returns),
        "average_win": average_win(trades),
        "average_loss": average_loss(trades),
        "expectancy": expectancy(trades),
    }
