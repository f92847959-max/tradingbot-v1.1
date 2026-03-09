"""WhatsApp message templates for trade events."""


def trade_opened(
    direction: str,
    price: float,
    lot_size: float,
    stop_loss: float,
    take_profit: float,
    score: int,
    confidence: float,
) -> str:
    return (
        f"TRADE EROEFFNET\n"
        f"{direction} GOLD @ ${price:.2f}\n"
        f"Lot: {lot_size:.2f} | Score: {score}\n"
        f"SL: ${stop_loss:.2f} | TP: ${take_profit:.2f}\n"
        f"Confidence: {confidence*100:.0f}%"
    )


def trade_closed(
    direction: str,
    entry: float,
    exit_price: float,
    pnl: float,
    reason: str,
    duration_min: int,
) -> str:
    emoji = "+" if pnl >= 0 else ""
    return (
        f"TRADE GESCHLOSSEN\n"
        f"{direction} @ ${entry:.2f} -> ${exit_price:.2f}\n"
        f"P&L: {emoji}{pnl:.2f} EUR | {reason}\n"
        f"Dauer: {duration_min} min"
    )


def kill_switch_activated(
    reason: str,
    drawdown_pct: float,
    positions_closed: int,
) -> str:
    return (
        f"KILL SWITCH AKTIVIERT\n"
        f"Grund: {reason}\n"
        f"Drawdown: {drawdown_pct:.1f}%\n"
        f"Positionen geschlossen: {positions_closed}"
    )


def daily_summary(
    date: str,
    trades_total: int,
    trades_won: int,
    trades_lost: int,
    net_pnl: float,
    win_rate: float,
    equity: float,
) -> str:
    emoji = "+" if net_pnl >= 0 else ""
    return (
        f"TAGES-SUMMARY {date}\n"
        f"Trades: {trades_total} ({trades_won}W/{trades_lost}L)\n"
        f"Win Rate: {win_rate:.0f}%\n"
        f"P&L: {emoji}{net_pnl:.2f} EUR\n"
        f"Equity: {equity:.2f} EUR"
    )


def system_warning(message: str) -> str:
    return f"SYSTEM-WARNUNG\n{message}"
