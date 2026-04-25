"""ATR-based trailing stop management for smart exits."""

from __future__ import annotations

from exit_engine.types import TrailingResult
from shared.constants import PIP_SIZE


def profit_r_multiple(
    direction: str,
    entry_price: float,
    current_price: float,
    initial_stop_loss: float,
) -> float:
    """Return current profit in R multiples based on the original risk."""
    risk = abs(entry_price - initial_stop_loss)
    if risk <= 0:
        raise ValueError("initial_stop_loss must differ from entry_price")

    if direction == "BUY":
        profit = current_price - entry_price
    elif direction == "SELL":
        profit = entry_price - current_price
    else:
        raise ValueError("direction must be BUY or SELL")

    return profit / risk


def calculate_trailing_stop(
    direction: str,
    entry_price: float,
    current_price: float,
    initial_stop_loss: float,
    atr: float,
    current_stop_loss: float | None = None,
    activation_r: float = 1.0,
    trail_atr_multiplier: float = 1.0,
    breakeven_buffer_pips: float = 0.0,
    pip_size: float = PIP_SIZE,
) -> TrailingResult:
    """Calculate a monotonic ATR trailing stop after profit reaches activation R.

    For BUY, SL only moves up. For SELL, SL only moves down. Once active, the
    stop is at least breakeven and then trails by ``ATR * trail_atr_multiplier``.
    """
    if atr is None or atr <= 0:
        raise ValueError(f"ATR must be positive, got: {atr}")
    if activation_r <= 0:
        raise ValueError("activation_r must be positive")
    if trail_atr_multiplier <= 0:
        raise ValueError("trail_atr_multiplier must be positive")

    profit_r = profit_r_multiple(
        direction=direction,
        entry_price=entry_price,
        current_price=current_price,
        initial_stop_loss=initial_stop_loss,
    )

    if profit_r < activation_r:
        return TrailingResult(
            new_sl=None,
            activated=False,
            profit_r=round(profit_r, 4),
            reason=f"profit below activation ({profit_r:.2f}R < {activation_r:.2f}R)",
        )

    trail_distance = atr * trail_atr_multiplier
    buffer = breakeven_buffer_pips * pip_size

    if direction == "BUY":
        breakeven_sl = entry_price + buffer
        atr_trail_sl = current_price - trail_distance
        candidate = max(breakeven_sl, atr_trail_sl)
        if current_stop_loss is not None and candidate <= current_stop_loss:
            return TrailingResult(
                new_sl=None,
                activated=True,
                profit_r=round(profit_r, 4),
                reason="no favorable SL improvement",
            )
    elif direction == "SELL":
        breakeven_sl = entry_price - buffer
        atr_trail_sl = current_price + trail_distance
        candidate = min(breakeven_sl, atr_trail_sl)
        if current_stop_loss is not None and candidate >= current_stop_loss:
            return TrailingResult(
                new_sl=None,
                activated=True,
                profit_r=round(profit_r, 4),
                reason="no favorable SL improvement",
            )
    else:
        raise ValueError("direction must be BUY or SELL")

    reason = "breakeven" if abs(candidate - breakeven_sl) < 1e-9 else "atr_trail"
    return TrailingResult(
        new_sl=round(candidate, 2),
        activated=True,
        profit_r=round(profit_r, 4),
        reason=reason,
    )


class SmartTrailingManager:
    """Stateful facade for per-position ATR trailing decisions."""

    def __init__(
        self,
        activation_r: float = 1.0,
        trail_atr_multiplier: float = 1.0,
        breakeven_buffer_pips: float = 0.0,
        pip_size: float = PIP_SIZE,
    ) -> None:
        self.activation_r = activation_r
        self.trail_atr_multiplier = trail_atr_multiplier
        self.breakeven_buffer_pips = breakeven_buffer_pips
        self.pip_size = pip_size
        self._last_stop_loss: dict[str, float] = {}

    def evaluate(
        self,
        deal_id: str,
        direction: str,
        entry_price: float,
        current_price: float,
        initial_stop_loss: float,
        atr: float,
        current_stop_loss: float | None = None,
    ) -> TrailingResult:
        """Evaluate trailing SL and remember accepted levels per deal."""
        effective_sl = self._last_stop_loss.get(deal_id, current_stop_loss)
        result = calculate_trailing_stop(
            direction=direction,
            entry_price=entry_price,
            current_price=current_price,
            initial_stop_loss=initial_stop_loss,
            atr=atr,
            current_stop_loss=effective_sl,
            activation_r=self.activation_r,
            trail_atr_multiplier=self.trail_atr_multiplier,
            breakeven_buffer_pips=self.breakeven_buffer_pips,
            pip_size=self.pip_size,
        )
        if result.new_sl is not None:
            self._last_stop_loss[deal_id] = result.new_sl
        return result

    def remove_tracking(self, deal_id: str) -> None:
        self._last_stop_loss.pop(deal_id, None)

    def is_trailing_active(self, deal_id: str) -> bool:
        return deal_id in self._last_stop_loss
