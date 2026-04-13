"""Unified AdvancedPositionSizer facade -- Phase 10 interface contract.

This module combines Kelly Criterion sizing with ATR-based volatility scaling
and confidence-tier adjustments into a single interface for signal consumers.

Phase 10 interface:
    from risk.position_sizer import get_position_size, init_position_sizer
    init_position_sizer(settings)
    lot = get_position_size(confidence=0.8, atr=3.0, account_balance=10000.0)

NOTE: risk/position_sizing.py (PositionSizer, used by RiskManager) is NOT
modified -- this file (risk/position_sizer.py) is a new, separate module.
"""

from __future__ import annotations

import logging
from typing import Optional

from risk.kelly_calculator import KellyCalculator
from risk.volatility_sizer import VolatilitySizer

logger = logging.getLogger(__name__)


class AdvancedPositionSizer:
    """Combined Kelly + ATR + confidence-tier position sizer.

    Args:
        base_risk_pct:  Fallback risk percentage (used when no trade history
                        available yet).  1.0 = risk 1% per trade.
        kelly_mode:     "full", "half", or "quarter" Kelly.  Defaults to "half"
                        (conservative -- common practice in live trading).
        baseline_atr:   XAUUSD ATR-14 considered 'normal'.  Default 3.0 for 5min.
        min_lot_size:   Hard floor on lot size.  Default 0.01.
        max_lot_size:   Hard ceiling on lot size.  Default 10.0.
    """

    def __init__(
        self,
        base_risk_pct: float = 1.0,
        kelly_mode: str = "half",
        baseline_atr: float = 3.0,
        min_lot_size: float = 0.01,
        max_lot_size: float = 10.0,
    ) -> None:
        self.base_risk_pct = base_risk_pct
        self.kelly_mode = kelly_mode
        self.min_lot_size = min_lot_size
        self.max_lot_size = max_lot_size

        self._kelly = KellyCalculator()
        self._vol_sizer = VolatilitySizer(baseline_atr=baseline_atr)

        # Kelly state (updated via set_trade_stats)
        self._kelly_fraction: float = 0.0
        self._win_rate: float = 0.0
        self._avg_win: float = 0.0
        self._avg_loss: float = 0.0

    # -------------------------------------------------------------------------
    # Public interface
    # -------------------------------------------------------------------------

    def set_trade_stats(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
    ) -> None:
        """Update the Kelly fraction from recent trade performance.

        Call this after loading trade history from the database so that
        position sizes reflect actual win rate and risk-reward ratio.

        Args:
            win_rate: Fraction of trades that are winners (0.0 -- 1.0).
            avg_win:  Average winning trade magnitude (pips or currency).
            avg_loss: Average losing trade magnitude (pips or currency, positive).
        """
        self._win_rate = win_rate
        self._avg_win = avg_win
        self._avg_loss = avg_loss

        # Calculate Kelly fraction based on selected mode
        if self.kelly_mode == "full":
            self._kelly_fraction = self._kelly.kelly_fraction(win_rate, avg_win, avg_loss)
        elif self.kelly_mode == "quarter":
            self._kelly_fraction = self._kelly.quarter_kelly(win_rate, avg_win, avg_loss)
        else:  # "half" (default)
            self._kelly_fraction = self._kelly.half_kelly(win_rate, avg_win, avg_loss)

        rrr = (avg_win / avg_loss) if avg_loss > 0 else 0.0
        logger.info(
            "Kelly updated: mode=%s, f*=%.4f, win_rate=%.2f, RRR=%.2f",
            self.kelly_mode,
            self._kelly_fraction,
            win_rate,
            rrr,
        )

    def get_position_size(
        self,
        confidence: float,
        atr: float,
        account_balance: float,
    ) -> dict:
        """Calculate position size for a potential trade.

        Combines three inputs:
          1. Kelly fraction from historical trade stats (or base_risk_pct fallback)
          2. Confidence tier (low/medium/high) further scales the Kelly fraction
          3. ATR-based volatility factor (high ATR => smaller position)

        Args:
            confidence:      ML model confidence score (0.0 -- 1.0).
            atr:             Current ATR-14 value.
            account_balance: Current account equity in base currency.

        Returns:
            dict with keys:
              - lot_size (float): Final clamped lot size
              - kelly_fraction (float): Internal Kelly fraction used
              - atr_factor (float): Volatility scaling factor
              - confidence_tier (str): "low" | "medium" | "high"
              - risk_pct (float): Effective risk percentage used
              - reasoning (str): Human-readable description of the calculation
        """
        # Guard: zero/negative balance
        if account_balance <= 0:
            logger.warning("get_position_size: account_balance=%.2f <= 0, returning 0", account_balance)
            return {
                "lot_size": 0.0,
                "kelly_fraction": self._kelly_fraction,
                "atr_factor": 1.0,
                "confidence_tier": "low",
                "risk_pct": 0.0,
                "reasoning": "Zero or negative account balance",
            }

        # Confidence tier mapping
        if confidence < 0.6:
            tier = "low"
            # Low confidence: use quarter_kelly on top of the stored fraction
            tier_multiplier = 0.25
        elif confidence <= 0.8:
            tier = "medium"
            tier_multiplier = 0.5
        else:
            tier = "high"
            tier_multiplier = 1.0

        # Determine risk percentage
        if self._kelly_fraction > 0.0:
            # Apply confidence tier multiplier to the stored Kelly fraction
            effective_fraction = self._kelly_fraction * tier_multiplier
            risk_pct = effective_fraction * 100.0
        else:
            # No Kelly data yet -- use base_risk_pct scaled by tier
            risk_pct = self.base_risk_pct * tier_multiplier

        # ATR factor from volatility sizer
        atr_factor = self._vol_sizer.calculate_atr_factor(atr)

        # Base lot size: risk a fraction of balance, SL at ~2 ATR
        sl_distance = max(atr * 2.0, 0.01)
        base_lot = (account_balance * risk_pct / 100.0) / sl_distance

        # Apply ATR scaling
        adjusted_lot = self._vol_sizer.adjust_lot_size(base_lot, atr, self.min_lot_size)

        # Final clamp to [min_lot_size, max_lot_size]
        lot_size = max(self.min_lot_size, min(self.max_lot_size, adjusted_lot))

        reasoning = (
            f"Kelly {self.kelly_mode}={self._kelly_fraction:.4f}, "
            f"ATR factor={atr_factor:.2f}, "
            f"confidence={tier}"
        )

        logger.info(
            "Position size: %.2f lots (Kelly=%.4f, ATR_factor=%.2f, tier=%s)",
            lot_size,
            self._kelly_fraction,
            atr_factor,
            tier,
        )

        return {
            "lot_size": lot_size,
            "kelly_fraction": self._kelly_fraction,
            "atr_factor": atr_factor,
            "confidence_tier": tier,
            "risk_pct": risk_pct,
            "reasoning": reasoning,
        }


# ---------------------------------------------------------------------------
# Module-level singleton and convenience functions (Phase 10 interface)
# ---------------------------------------------------------------------------

_instance: Optional[AdvancedPositionSizer] = None


def init_position_sizer(settings) -> AdvancedPositionSizer:
    """Create and store the global AdvancedPositionSizer singleton.

    Should be called once at application startup after loading Settings.

    Args:
        settings: Settings object with fields:
                  max_risk_per_trade_pct, kelly_mode, atr_baseline

    Returns:
        The newly created AdvancedPositionSizer instance.
    """
    global _instance
    _instance = AdvancedPositionSizer(
        base_risk_pct=settings.max_risk_per_trade_pct,
        kelly_mode=settings.kelly_mode,
        baseline_atr=settings.atr_baseline,
    )
    logger.info(
        "AdvancedPositionSizer initialized: risk_pct=%.2f, mode=%s, baseline_atr=%.1f",
        settings.max_risk_per_trade_pct,
        settings.kelly_mode,
        settings.atr_baseline,
    )
    return _instance


def get_portfolio_heat() -> float:
    """Phase 10 interface stub.

    The actual implementation routes through RiskManager.
    Use risk_manager.get_portfolio_heat() directly.

    Raises:
        RuntimeError: Always -- requires RiskManager instance.
    """
    raise RuntimeError(
        "get_portfolio_heat() requires RiskManager. "
        "Use risk_manager.get_portfolio_heat() directly."
    )


def is_trading_allowed() -> bool:
    """Phase 10 interface stub.

    The actual implementation routes through RiskManager.
    Use risk_manager.is_trading_allowed() directly.

    Raises:
        RuntimeError: Always -- requires RiskManager instance.
    """
    raise RuntimeError(
        "is_trading_allowed() requires RiskManager. "
        "Use risk_manager.is_trading_allowed() directly."
    )


def get_position_size(
    confidence: float,
    atr: float,
    account_balance: float,
) -> float:
    """Module-level convenience function returning just the lot_size float.

    Phase 10 callers import this function for clean, one-line position sizing.

    Args:
        confidence:      ML model confidence (0.0 -- 1.0).
        atr:             Current ATR-14 value.
        account_balance: Account equity.

    Returns:
        Lot size as float.

    Raises:
        RuntimeError: If init_position_sizer() has not been called.
    """
    if _instance is None:
        raise RuntimeError(
            "AdvancedPositionSizer not initialized. Call init_position_sizer() first."
        )
    result = _instance.get_position_size(confidence, atr, account_balance)
    return result["lot_size"]
