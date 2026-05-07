"""Tests for training quick-win changes."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from ai_engine.features.market_structure_liquidity import (
    MarketStructureLiquidityFeatures,
)
from ai_engine.models.lightgbm_model import LightGBMModel
from ai_engine.models.xgboost_model import XGBoostModel
from ai_engine.training.label_generator import LabelGenerator
from ai_engine.training.shap_importance import save_training_diagnostic_charts


def test_class_weight_power_increases_minority_penalty() -> None:
    y = np.array([0] * 90 + [1] * 9 + [2])

    base = XGBoostModel._compute_sample_weights(
        y,
        len(y),
        use_class_weight=True,
        use_recency_weight=False,
        class_weight_power=1.0,
    )
    strong = XGBoostModel._compute_sample_weights(
        y,
        len(y),
        use_class_weight=True,
        use_recency_weight=False,
        class_weight_power=1.5,
    )

    assert strong[y == 2].mean() / strong[y == 0].mean() > base[y == 2].mean() / base[y == 0].mean()

    lgb_strong = LightGBMModel._compute_sample_weights(
        y,
        len(y),
        use_recency_weight=False,
        class_weight_power=1.5,
    )
    assert lgb_strong[y == 2].mean() > lgb_strong[y == 0].mean()


def test_exit_aware_labels_demote_adverse_trade_to_hold() -> None:
    idx = pd.date_range("2026-01-01", periods=8, freq="4h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0] * 8,
            "high": [100.1, 100.3, 100.4, 102.2, 102.3, 102.3, 102.3, 102.3],
            "low": [99.9, 99.2, 99.4, 100.0, 100.0, 100.0, 100.0, 100.0],
            "close": [100.0, 99.6, 100.2, 102.1, 102.1, 102.1, 102.1, 102.1],
            "atr_14": [1.0] * 8,
        },
        index=idx,
    )
    plain = LabelGenerator(
        tp_pips=2,
        sl_pips=1,
        max_candles=5,
        pip_size=1.0,
        spread_pips=0,
        slippage_pips=0,
        exit_aware=False,
    ).generate_labels(df)
    aware = LabelGenerator(
        tp_pips=2,
        sl_pips=1,
        max_candles=5,
        pip_size=1.0,
        spread_pips=0,
        slippage_pips=0,
        exit_aware=True,
    ).generate_labels(df)

    assert int(plain.iloc[0]) == 1
    assert int(aware.iloc[0]) == 0


def test_market_structure_stride_forward_fills_specialist_features() -> None:
    idx = pd.date_range("2026-01-01", periods=80, freq="5min", tz="UTC")
    close = np.linspace(100.0, 110.0, len(idx))
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "atr_14": np.ones(len(idx)),
        },
        index=idx,
    )
    features = MarketStructureLiquidityFeatures(stride=12)
    out = features.calculate(df)

    assert set(features.FEATURE_NAMES).issubset(out.columns)
    assert out[features.FEATURE_NAMES].isna().sum().sum() == 0
    pd.testing.assert_series_equal(
        out.loc[idx[1], features.FEATURE_NAMES],
        out.loc[idx[0], features.FEATURE_NAMES],
        check_names=False,
    )


def test_training_diagnostic_charts_writes_eight_pngs(tmp_path) -> None:
    report = {
        "per_window": [
            {
                "window_id": 0,
                "xgboost": {"profit_factor": 1.1, "win_rate": 0.4, "expectancy": 10, "n_trades": 5},
                "lightgbm": {"profit_factor": 1.2, "win_rate": 0.45, "expectancy": 15, "n_trades": 6},
                "feature_pruning": {"kept_count": 10, "pruned_count": 2},
            }
        ],
        "aggregate": {
            "xgboost": {"profit_factor": 1.1, "sharpe": 0.5},
            "lightgbm": {"profit_factor": 1.2, "sharpe": 0.8},
        },
    }
    paths = save_training_diagnostic_charts(
        report,
        {"sell": 2, "hold": 3, "buy": 4},
        str(tmp_path),
    )

    assert len(paths) == 8
    assert all(os.path.exists(path) and os.path.getsize(path) > 0 for path in paths)
