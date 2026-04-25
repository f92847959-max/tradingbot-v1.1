"""Partial-close decision logic for smart exits."""

from __future__ import annotations

from exit_engine.types import PartialCloseAction


def tp1_reached(direction: str, current_price: float, tp1: float) -> bool:
    """Return whether price has reached the first partial-close target."""
    if direction == "BUY":
        return current_price >= tp1
    if direction == "SELL":
        return current_price <= tp1
    raise ValueError("direction must be BUY or SELL")


def evaluate_partial_close(
    direction: str,
    current_price: float,
    tp1: float | None,
    close_fraction: float = 0.5,
    already_closed: bool = False,
) -> PartialCloseAction:
    """Return a partial-close action when TP1 is reached exactly once."""
    if close_fraction <= 0 or close_fraction >= 1:
        raise ValueError("close_fraction must be between 0 and 1")
    if tp1 is None:
        return PartialCloseAction(
            close_fraction=0.0,
            reason="tp1 not configured",
            target_hit="none",
        )
    if already_closed:
        return PartialCloseAction(
            close_fraction=0.0,
            reason="tp1 already closed",
            target_hit="tp1",
        )
    if not tp1_reached(direction, current_price, tp1):
        return PartialCloseAction(
            close_fraction=0.0,
            reason="tp1 not reached",
            target_hit="none",
        )

    return PartialCloseAction(
        close_fraction=close_fraction,
        reason="tp1 reached",
        target_hit="tp1",
    )


class PartialCloseManager:
    """Track TP1 partial closes so a position is closed only once at TP1."""

    def __init__(self, close_fraction: float = 0.5) -> None:
        if close_fraction <= 0 or close_fraction >= 1:
            raise ValueError("close_fraction must be between 0 and 1")
        self.close_fraction = close_fraction
        self._closed_tp1: set[str] = set()

    def evaluate(
        self,
        deal_id: str,
        direction: str,
        current_price: float,
        tp1: float | None,
    ) -> PartialCloseAction:
        """Return a TP1 partial-close action and mark it consumed when fired."""
        action = evaluate_partial_close(
            direction=direction,
            current_price=current_price,
            tp1=tp1,
            close_fraction=self.close_fraction,
            already_closed=deal_id in self._closed_tp1,
        )
        if action.close_fraction > 0:
            self._closed_tp1.add(deal_id)
        return action

    def remove_tracking(self, deal_id: str) -> None:
        self._closed_tp1.discard(deal_id)

    def was_tp1_closed(self, deal_id: str) -> bool:
        return deal_id in self._closed_tp1
