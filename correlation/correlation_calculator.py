"""Pure correlation calculations for Phase 12 (CORR-02, CORR-03)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from correlation.snapshot import CorrelationSnapshot


WINDOWS = [20, 60, 120]
ASSETS_VS_GOLD = ["dxy", "us10y", "silver", "vix", "sp500"]


def rolling_corr(a: pd.Series, b: pd.Series, window: int) -> float:
    """Return the latest rolling Pearson correlation for two aligned series."""
    aligned = pd.concat([a, b], axis=1).dropna()
    if len(aligned) < window:
        return 0.0

    value = aligned.iloc[:, 0].rolling(window).corr(aligned.iloc[:, 1]).iloc[-1]
    if pd.isna(value):
        return 0.0
    return float(np.clip(value, -1.0, 1.0))


def divergence_score(a: pd.Series, b: pd.Series, lookback: int = 20) -> float:
    """Return the share of recent bars where returns moved in opposite directions."""
    aligned = pd.concat([a, b], axis=1).dropna()
    if len(aligned) < lookback + 1:
        return 0.0

    returns = aligned.pct_change().dropna().tail(lookback)
    if returns.empty:
        return 0.0

    same_sign = (
        np.sign(returns.iloc[:, 0].to_numpy()) == np.sign(returns.iloc[:, 1].to_numpy())
    ).astype(float)
    return float(np.clip(1.0 - same_sign.mean(), 0.0, 1.0))


def lead_lag(a: pd.Series, b: pd.Series, max_lag: int = 10) -> float:
    """Return normalized lead-lag score in [-1, 1].

    Negative means ``a`` leads ``b``. Positive means ``b`` leads ``a``.
    """
    aligned = pd.concat([a, b], axis=1).dropna()
    if len(aligned) < (2 * max_lag + 1):
        return 0.0

    a_values = aligned.iloc[:, 0].to_numpy(dtype=float)
    b_values = aligned.iloc[:, 1].to_numpy(dtype=float)

    a_norm = (a_values - a_values.mean()) / (a_values.std() + 1e-12)
    b_norm = (b_values - b_values.mean()) / (b_values.std() + 1e-12)

    xcorr = np.correlate(a_norm, b_norm, mode="full")
    center = len(a_norm) - 1
    window = xcorr[center - max_lag: center + max_lag + 1]
    best_lag = int(np.argmax(np.abs(window))) - max_lag
    return float(np.clip(best_lag / max_lag, -1.0, 1.0))


def regime(current_corr: float, recent_corrs: pd.Series) -> float:
    """Classify the current correlation versus recent history."""
    recent = pd.Series(recent_corrs, dtype=float).dropna()
    if len(recent) < 10:
        return 0.0

    mean = float(recent.mean())
    std = float(recent.std())

    # Sign-flips against a stable historical relationship indicate inversion.
    if current_corr * mean < 0 and abs(current_corr) >= 0.5 and abs(mean) >= 0.5:
        return -1.0

    # Flat history still needs graceful classification.
    if std < 1e-9:
        return 1.0 if abs(current_corr - mean) >= 0.5 else 0.0

    z_score = (current_corr - mean) / std
    if abs(z_score) > 2.0:
        return 1.0
    return 0.0


def compute_snapshot(closes: pd.DataFrame) -> CorrelationSnapshot:
    """Transform aligned close prices into a CorrelationSnapshot."""
    if closes is None or closes.empty or "gold" not in closes.columns:
        return CorrelationSnapshot()

    gold = closes["gold"]
    fields: dict[str, float] = {}

    for asset in ASSETS_VS_GOLD:
        if asset not in closes.columns:
            for window in WINDOWS:
                fields[f"corr_{asset}_{window}"] = 0.0
            continue
        for window in WINDOWS:
            fields[f"corr_{asset}_{window}"] = rolling_corr(gold, closes[asset], window)

    for asset in ["dxy", "us10y"]:
        fields[f"divergence_{asset}"] = (
            divergence_score(gold, closes[asset]) if asset in closes.columns else 0.0
        )

    dxy_corr_series = pd.Series(dtype=float)
    if "dxy" in closes.columns:
        aligned = pd.concat([gold, closes["dxy"]], axis=1).dropna()
        if len(aligned) >= 60:
            dxy_corr_series = aligned.iloc[:, 0].rolling(60).corr(aligned.iloc[:, 1]).dropna()

    if dxy_corr_series.empty:
        fields["corr_regime"] = 0.0
    else:
        fields["corr_regime"] = regime(
            current_corr=float(dxy_corr_series.iloc[-1]),
            recent_corrs=dxy_corr_series.tail(30),
        )

    for asset in ["silver", "dxy"]:
        fields[f"lead_lag_{asset}"] = lead_lag(gold, closes[asset]) if asset in closes.columns else 0.0

    return CorrelationSnapshot(**fields)


__all__ = [
    "ASSETS_VS_GOLD",
    "WINDOWS",
    "compute_snapshot",
    "divergence_score",
    "lead_lag",
    "regime",
    "rolling_corr",
]
