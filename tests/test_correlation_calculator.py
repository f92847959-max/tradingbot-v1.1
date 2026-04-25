"""Unit tests for correlation calculation helpers and snapshot assembly."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from correlation.correlation_calculator import (
    compute_snapshot,
    divergence_score,
    lead_lag,
    regime,
    rolling_corr,
)
from correlation.snapshot import CorrelationSnapshot


def _make_closes_df(rows: int = 200) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=rows, freq="D")
    base = np.linspace(0.0, 4.0 * np.pi, rows)
    rng = np.random.default_rng(42)
    gold = 2000.0 + np.sin(base) * 15.0 + rng.normal(0.0, 0.4, rows)
    return pd.DataFrame(
        {
            "dxy": 105.0 - np.sin(base) * 0.8 + rng.normal(0.0, 0.03, rows),
            "us10y": 4.2 - np.sin(base) * 0.05 + rng.normal(0.0, 0.01, rows),
            "silver": 30.0 + np.sin(base) * 1.6 + rng.normal(0.0, 0.08, rows),
            "vix": 18.0 - np.sin(base) * 0.5 + rng.normal(0.0, 0.05, rows),
            "sp500": 5800.0 + np.sin(base) * 25.0 + rng.normal(0.0, 1.5, rows),
            "gold": gold,
        },
        index=index,
    )


def test_rolling_corr() -> None:
    rng = np.random.default_rng(7)
    a = pd.Series(np.linspace(0.0, 10.0, 100))
    b = pd.Series(a + rng.normal(0.0, 0.05, len(a)))
    c = pd.Series(-a)

    assert rolling_corr(a, b, window=20) >= 0.95
    assert rolling_corr(a, c, window=20) <= -0.95


def test_insufficient_data() -> None:
    df_50 = _make_closes_df(rows=50)

    snap = compute_snapshot(df_50)

    assert isinstance(snap, CorrelationSnapshot)
    assert snap.corr_dxy_120 == 0.0
    assert snap.corr_us10y_120 == 0.0
    assert -1.0 <= snap.corr_dxy_20 <= 1.0


def test_regime_detection() -> None:
    assert regime(current_corr=0.0, recent_corrs=pd.Series([-0.8] * 30)) == 1.0
    assert regime(current_corr=-0.9, recent_corrs=pd.Series([-0.85] * 30)) == 0.0
    assert regime(current_corr=0.8, recent_corrs=pd.Series([-0.8] * 30)) == -1.0


def test_divergence_score() -> None:
    a = pd.Series(np.arange(101, dtype=float))
    b_same = pd.Series(np.arange(0, 202, 2, dtype=float))
    b_opposite = pd.Series(np.arange(200, 99, -1, dtype=float))
    b_mixed = b_opposite.copy()
    b_mixed.iloc[-10:] = b_same.iloc[-10:]

    assert divergence_score(a, b_same, lookback=20) == pytest.approx(0.0)
    assert divergence_score(a, b_opposite, lookback=20) == pytest.approx(1.0)
    assert 0.0 <= divergence_score(a, b_mixed, lookback=20) <= 1.0


def test_lead_lag() -> None:
    a = pd.Series(np.sin(np.linspace(0.0, 10.0 * np.pi, 200)))
    b = a.shift(3).fillna(0.0)
    c = a.shift(-3).fillna(0.0)

    assert lead_lag(a, b, max_lag=10) == pytest.approx(-0.3, abs=0.15)
    assert lead_lag(a, c, max_lag=10) == pytest.approx(0.3, abs=0.15)
