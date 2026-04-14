"""Shared dataclasses for the exit engine package.

Defines the core data contracts used across dynamic_sl, dynamic_tp,
trailing_manager, partial_close, and exit_signals modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StructureLevel:
    """A support or resistance price level identified from swing points."""

    price: float          # The support/resistance price
    level_type: str       # "support" or "resistance"
    strength: int         # Number of touches (1-5+)
    source: str           # "swing_low", "swing_high", "fib_level"


@dataclass
class ExitLevels:
    """Computed stop-loss and take-profit levels for a trade."""

    stop_loss: float
    take_profit: float
    tp1: float | None = None   # First partial TP target (50% close)
    sl_reason: str = ""        # "atr", "structure", "atr+structure"
    tp_reason: str = ""        # "fibonacci", "sr_zone", "atr_multiple"


@dataclass
class TrailingResult:
    """Result from ATR-based trailing stop calculation."""

    new_sl: float | None       # None = no update needed
    activated: bool            # Whether trailing is now active
    profit_r: float            # Current profit in R multiples
    reason: str = ""


@dataclass
class PartialCloseAction:
    """Instruction to partially close an open position."""

    close_fraction: float      # 0.0-1.0, e.g. 0.5 for 50%
    reason: str
    target_hit: str            # "tp1", "tp2"


@dataclass
class ExitSignal:
    """Signal indicating whether an open position should be closed."""

    should_exit: bool
    signal_type: str           # "reversal_candle", "momentum_divergence", "time_exit", "force_close", "none"
    confidence: float          # 0.0-1.0
    reason: str
