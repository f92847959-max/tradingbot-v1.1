"""Tests for runtime and env-alias helpers in scripts/train_ai.py."""

from __future__ import annotations

from scripts.train_ai import (
    apply_capital_env_aliases,
    pick_best_cycle,
    should_continue_training,
)


def test_apply_capital_env_aliases_maps_missing_keys(monkeypatch) -> None:
    monkeypatch.delenv("CAPITAL_EMAIL", raising=False)
    monkeypatch.delenv("CAPITAL_PASSWORD", raising=False)
    monkeypatch.delenv("CAPITAL_API_KEY", raising=False)
    monkeypatch.delenv("CAPITAL_DEMO", raising=False)

    monkeypatch.setenv("CAPITAL_COM_IDENTIFIER", "user@example.com")
    monkeypatch.setenv("CAPITAL_COM_PASSWORD", "secret")
    monkeypatch.setenv("CAPITAL_COM_API_KEY", "abc123")
    monkeypatch.setenv("CAPITAL_COM_DEMO", "true")

    applied = apply_capital_env_aliases()

    assert applied["CAPITAL_EMAIL"] == "CAPITAL_COM_IDENTIFIER"
    assert applied["CAPITAL_PASSWORD"] == "CAPITAL_COM_PASSWORD"
    assert applied["CAPITAL_API_KEY"] == "CAPITAL_COM_API_KEY"
    assert applied["CAPITAL_DEMO"] == "CAPITAL_COM_DEMO"


def test_should_continue_training_before_and_after_min_runtime() -> None:
    assert should_continue_training(
        elapsed_seconds=10.0,
        min_runtime_seconds=60.0,
        max_runtime_seconds=120.0,
        latest_acceptance="fail",
    )
    assert not should_continue_training(
        elapsed_seconds=61.0,
        min_runtime_seconds=60.0,
        max_runtime_seconds=None,
        latest_acceptance="fail",
    )
    assert not should_continue_training(
        elapsed_seconds=61.0,
        min_runtime_seconds=60.0,
        max_runtime_seconds=120.0,
        latest_acceptance="pass",
    )
    assert should_continue_training(
        elapsed_seconds=61.0,
        min_runtime_seconds=60.0,
        max_runtime_seconds=120.0,
        latest_acceptance="fail",
    )
    assert not should_continue_training(
        elapsed_seconds=120.0,
        min_runtime_seconds=60.0,
        max_runtime_seconds=120.0,
        latest_acceptance="fail",
    )


def test_pick_best_cycle_prefers_pass_over_higher_fail_pf() -> None:
    cycles = [
        {
            "cycle": 1,
            "acceptance": {"overall": "fail"},
            "best_metrics": {
                "best_trading": {"profit_factor": 3.0, "sharpe_ratio": 2.0},
                "backtest": {"max_drawdown_pct": 30.0},
            },
        },
        {
            "cycle": 2,
            "acceptance": {"overall": "pass"},
            "best_metrics": {
                "best_trading": {"profit_factor": 1.3, "sharpe_ratio": 1.0},
                "backtest": {"max_drawdown_pct": 12.0},
            },
        },
    ]
    best = pick_best_cycle(cycles)
    assert best["cycle"] == 2
