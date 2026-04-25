"""Exit engine package for smart, regime-aware trade exit management."""

from exit_engine.dynamic_sl import calculate_dynamic_sl, find_swing_levels
from exit_engine.dynamic_tp import calculate_dynamic_tp, fibonacci_extensions, find_sr_levels
from exit_engine.exit_signals import check_exit_signals
from exit_engine.partial_close import (
    PartialCloseManager,
    evaluate_partial_close,
    tp1_reached,
)
from exit_engine.trailing_manager import (
    SmartTrailingManager,
    calculate_trailing_stop,
    profit_r_multiple,
)
from exit_engine.types import (
    ExitLevels,
    ExitSignal,
    PartialCloseAction,
    StopLossResult,
    StructureLevel,
    TakeProfitResult,
    TrailingResult,
)

__all__ = [
    "ExitLevels",
    "ExitSignal",
    "PartialCloseAction",
    "StopLossResult",
    "StructureLevel",
    "TakeProfitResult",
    "TrailingResult",
    "PartialCloseManager",
    "SmartTrailingManager",
    "calculate_dynamic_sl",
    "calculate_dynamic_tp",
    "calculate_trailing_stop",
    "check_exit_signals",
    "evaluate_partial_close",
    "fibonacci_extensions",
    "find_sr_levels",
    "find_swing_levels",
    "profit_r_multiple",
    "tp1_reached",
]
