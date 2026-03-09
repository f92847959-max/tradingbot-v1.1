"""Tests fuer Acceptance-Gate in scripts/train_ai.py."""

from __future__ import annotations

from scripts.train_ai import AcceptanceThresholds, evaluate_acceptance


def test_acceptance_pass() -> None:
    best_metrics = {
        "best_trading": {"profit_factor": 1.35, "sharpe_ratio": 1.1},
        "backtest": {"max_drawdown_pct": 12.0},
    }
    thresholds = AcceptanceThresholds(
        min_profit_factor=1.2,
        min_sharpe=0.9,
        max_drawdown_pct=18.0,
    )
    result = evaluate_acceptance(best_metrics, thresholds)
    assert result["overall"] == "pass"


def test_acceptance_borderline() -> None:
    best_metrics = {
        "best_trading": {"profit_factor": 1.25, "sharpe_ratio": 0.5},
        "backtest": {"max_drawdown_pct": 15.0},
    }
    thresholds = AcceptanceThresholds(
        min_profit_factor=1.2,
        min_sharpe=0.9,
        max_drawdown_pct=18.0,
    )
    result = evaluate_acceptance(best_metrics, thresholds)
    assert result["overall"] == "borderline"


def test_acceptance_fail() -> None:
    best_metrics = {
        "best_trading": {"profit_factor": 0.9, "sharpe_ratio": 0.3},
        "backtest": {"max_drawdown_pct": 27.0},
    }
    thresholds = AcceptanceThresholds(
        min_profit_factor=1.2,
        min_sharpe=0.9,
        max_drawdown_pct=18.0,
    )
    result = evaluate_acceptance(best_metrics, thresholds)
    assert result["overall"] == "fail"


def test_acceptance_zero_drawdown_is_not_treated_as_missing() -> None:
    best_metrics = {
        "best_trading": {"profit_factor": 1.5, "sharpe_ratio": 0.0},
        "backtest": {"max_drawdown_pct": 0.0},
    }
    thresholds = AcceptanceThresholds(
        min_profit_factor=1.2,
        min_sharpe=0.9,
        max_drawdown_pct=18.0,
    )
    result = evaluate_acceptance(best_metrics, thresholds)
    assert result["checks"]["max_drawdown_pct"]["value"] == 0.0
    assert result["overall"] == "borderline"
