"""CorrelationSnapshot dataclass (Phase 12, CORR-01).

Carries the 20 inter-market correlation features consumed by the ML feature engineer.

Field value ranges:
- corr_*_{20,60,120}: Pearson rolling correlation in [-1, 1]
- divergence_dxy, divergence_us10y: normalised divergence score in [0, 1]
- corr_regime: discrete in {-1, 0, 1} (1=breakdown, 0=normal, -1=inversion)
- lead_lag_silver, lead_lag_dxy: lead/lag correlation strength in [-1, 1]
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class CorrelationSnapshot:
    """Immutable snapshot of inter-market correlation features for gold (XAUUSD).

    All fields default to 0.0 so that an empty snapshot represents a neutral,
    no-information state suitable for graceful fallback when correlation_enabled=False.
    """

    corr_dxy_20: float = 0.0
    corr_dxy_60: float = 0.0
    corr_dxy_120: float = 0.0
    corr_us10y_20: float = 0.0
    corr_us10y_60: float = 0.0
    corr_us10y_120: float = 0.0
    corr_silver_20: float = 0.0
    corr_silver_60: float = 0.0
    corr_silver_120: float = 0.0
    corr_vix_20: float = 0.0
    corr_vix_60: float = 0.0
    corr_vix_120: float = 0.0
    corr_sp500_20: float = 0.0
    corr_sp500_60: float = 0.0
    corr_sp500_120: float = 0.0
    divergence_dxy: float = 0.0
    divergence_us10y: float = 0.0
    corr_regime: float = 0.0      # 0=normal, 1=breakdown, -1=inversion
    lead_lag_silver: float = 0.0
    lead_lag_dxy: float = 0.0
