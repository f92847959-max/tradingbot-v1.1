"""
Tests for backtest runner, backtest report, and commission support.
"""

import json
import os

import numpy as np
import pytest

from ai_engine.training.backtester import Backtester
from ai_engine.training.backtest_report import (
    check_consistency,
    generate_backtest_report,
    print_backtest_report,
)


# ---------------------------------------------------------------------------
# Commission tests (Task 1)
# ---------------------------------------------------------------------------

class TestBacktesterCommission:
    def test_commission_included_in_total_cost(self):
        """Backtester with commission deducts extra pips per trade."""
        bt = Backtester(
            spread_pips=2.5,
            slippage_pips=0.5,
            commission_per_trade_pips=1.0,
        )
        assert bt.total_cost_pips == pytest.approx(4.0)

    def test_default_commission_zero(self):
        """Default commission is 0.0 — backward compatible."""
        bt = Backtester(spread_pips=2.5, slippage_pips=0.5)
        assert bt.commission_per_trade_pips == 0.0
        assert bt.total_cost_pips == pytest.approx(3.0)

    def test_commission_affects_run_simple(self):
        """Commission produces lower net profit per winning trade."""
        np.random.seed(42)
        n = 50
        # 100% win scenario: predictions perfectly match labels
        preds = np.array([1] * n)
        labels = np.array([1] * n)

        bt_no_comm = Backtester(
            tp_pips=50.0, sl_pips=30.0,
            spread_pips=2.5, slippage_pips=0.5,
            commission_per_trade_pips=0.0,
        )
        bt_with_comm = Backtester(
            tp_pips=50.0, sl_pips=30.0,
            spread_pips=2.5, slippage_pips=0.5,
            commission_per_trade_pips=2.0,
        )

        report_no = bt_no_comm.run_simple(preds, labels)
        report_with = bt_with_comm.run_simple(preds, labels)

        # With commission, total pips should be lower
        assert report_with["total_pips"] < report_no["total_pips"]
        # Difference should be exactly n * commission pips
        diff = report_no["total_pips"] - report_with["total_pips"]
        assert diff == pytest.approx(n * 2.0)

    def test_commission_increases_loss_on_losing_trades(self):
        """Commission makes losing trades even worse."""
        preds = np.array([1, 1])
        labels = np.array([-1, -1])  # all wrong

        bt_no = Backtester(
            tp_pips=50.0, sl_pips=30.0,
            spread_pips=2.5, slippage_pips=0.5,
            commission_per_trade_pips=0.0,
        )
        bt_with = Backtester(
            tp_pips=50.0, sl_pips=30.0,
            spread_pips=2.5, slippage_pips=0.5,
            commission_per_trade_pips=1.5,
        )

        report_no = bt_no.run_simple(preds, labels)
        report_with = bt_with.run_simple(preds, labels)

        # With commission, loss should be greater (more negative)
        assert report_with["total_pips"] < report_no["total_pips"]


# ---------------------------------------------------------------------------
# Consistency check tests
# ---------------------------------------------------------------------------

def _make_window_result(
    window_id: int,
    n_trades: int,
    total_pips: float,
    max_drawdown_pct: float = 5.0,
    win_rate: float = 0.5,
    profit_factor: float = 1.0,
    sharpe_ratio: float = 0.5,
    grade: str = "* ACCEPTABLE",
) -> dict:
    """Helper to create a mock per-window result dict."""
    trades = []
    if n_trades > 0 and total_pips > 0:
        per_trade = total_pips / max(n_trades, 1)
        trades = [{"pnl_pips": per_trade}] * n_trades
    elif n_trades > 0 and total_pips <= 0:
        per_trade = total_pips / max(n_trades, 1)
        trades = [{"pnl_pips": per_trade}] * n_trades

    return {
        "window_id": window_id,
        "n_trades": n_trades,
        "total_pips": total_pips,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown_pct": max_drawdown_pct,
        "grade": grade,
        "trades": trades,
        "gross_profit": max(total_pips, 0),
        "gross_loss": abs(min(total_pips, 0)),
    }


class TestCheckConsistency:
    def test_passes_when_above_60pct(self):
        """check_consistency passes with >60% positive windows."""
        results = [
            _make_window_result(0, 20, 50.0, 5.0),   # +
            _make_window_result(1, 15, 30.0, 3.0),   # +
            _make_window_result(2, 18, -10.0, 8.0),  # -
            _make_window_result(3, 22, 45.0, 4.0),   # +
            _make_window_result(4, 16, 20.0, 6.0),   # +
        ]
        c = check_consistency(results)
        assert c["passes_60pct"] is True
        assert c["positive_pct"] == pytest.approx(0.8)

    def test_fails_below_60pct(self):
        """check_consistency fails with <=60% positive windows."""
        results = [
            _make_window_result(0, 20, 50.0, 5.0),   # +
            _make_window_result(1, 15, -30.0, 3.0),  # -
            _make_window_result(2, 18, -10.0, 8.0),  # -
            _make_window_result(3, 22, -45.0, 4.0),  # -
            _make_window_result(4, 16, 20.0, 6.0),   # +
        ]
        c = check_consistency(results)
        assert c["passes_60pct"] is False
        assert c["positive_pct"] == pytest.approx(0.4)

    def test_fails_with_dd_violation(self):
        """check_consistency fails when any window exceeds 20% drawdown."""
        results = [
            _make_window_result(0, 20, 50.0, 5.0),
            _make_window_result(1, 15, 30.0, 3.0),
            _make_window_result(2, 18, 10.0, 25.0),  # DD violation!
            _make_window_result(3, 22, 45.0, 4.0),
            _make_window_result(4, 16, 20.0, 6.0),
        ]
        c = check_consistency(results)
        assert c["passes_20pct_dd"] is False
        assert c["dd_violations"] == 1
        assert c["overall_pass"] is False

    def test_zero_trade_windows_excluded(self):
        """Zero-trade windows excluded from 60% positive calculation."""
        results = [
            _make_window_result(0, 20, 50.0, 5.0),   # + (has trades)
            _make_window_result(1, 0, 0.0, 0.0),     # zero trades
            _make_window_result(2, 0, 0.0, 0.0),     # zero trades
            _make_window_result(3, 22, 45.0, 4.0),   # + (has trades)
            _make_window_result(4, 16, -20.0, 6.0),  # - (has trades)
        ]
        c = check_consistency(results)
        # 2 out of 3 windows-with-trades are positive = 66.7%
        assert c["windows_with_trades"] == 3
        assert c["zero_trade_windows"] == 2
        assert c["positive_windows"] == 2
        assert c["passes_60pct"] is True

    def test_overall_pass_requires_both(self):
        """overall_pass needs both 60% positive AND no DD violations."""
        results = [
            _make_window_result(0, 20, 50.0, 5.0),
            _make_window_result(1, 15, 30.0, 3.0),
            _make_window_result(2, 18, 10.0, 3.0),
            _make_window_result(3, 22, 45.0, 4.0),
            _make_window_result(4, 16, 20.0, 6.0),
        ]
        c = check_consistency(results)
        assert c["overall_pass"] is True

    def test_empty_results(self):
        """Empty results should not pass."""
        c = check_consistency([])
        assert c["overall_pass"] is False
        assert c["n_windows"] == 0


# ---------------------------------------------------------------------------
# Report generation tests
# ---------------------------------------------------------------------------

class TestGenerateBacktestReport:
    def test_produces_json_serializable_report(self):
        """Report must be JSON-serializable."""
        results = [
            _make_window_result(0, 10, 30.0, 3.0),
            _make_window_result(1, 8, -5.0, 2.0),
        ]
        report = generate_backtest_report(results, {"version": "v001"})
        # Must not raise
        json.dumps(report)

    def test_report_has_required_sections(self):
        """Report must have per_window and aggregate sections."""
        results = [
            _make_window_result(0, 10, 30.0, 3.0),
        ]
        report = generate_backtest_report(results, {"version": "v001"})
        assert "per_window" in report
        assert "aggregate" in report
        assert "report_date" in report

    def test_aggregate_pf_from_totals(self):
        """Aggregate PF is total gross_profit / total gross_loss."""
        # Window 0: 5 trades, each +10 pips = 50 gross profit
        w0 = _make_window_result(0, 5, 50.0, 3.0)
        w0["trades"] = [{"pnl_pips": 10.0}] * 5

        # Window 1: 3 trades, each -5 pips = 15 gross loss
        w1 = _make_window_result(1, 3, -15.0, 2.0)
        w1["trades"] = [{"pnl_pips": -5.0}] * 3

        report = generate_backtest_report([w0, w1], {})
        agg = report["aggregate"]
        # PF = 50 / 15 = 3.33...
        assert agg["profit_factor"] == pytest.approx(50.0 / 15.0, rel=0.01)

    def test_per_window_entries(self):
        """Per-window entries have all required metrics."""
        results = [
            _make_window_result(0, 10, 30.0, 3.0, 0.6, 1.5, 1.2, "** GOOD"),
        ]
        report = generate_backtest_report(results, {})
        pw = report["per_window"][0]
        assert pw["window_id"] == 0
        assert pw["n_trades"] == 10
        assert pw["total_pips"] == pytest.approx(30.0)
        assert pw["win_rate"] == pytest.approx(0.6)
        assert pw["profit_factor"] == pytest.approx(1.5)
        assert pw["sharpe_ratio"] == pytest.approx(1.2)
        assert pw["max_drawdown_pct"] == pytest.approx(3.0)
        assert pw["grade"] == "** GOOD"


class TestPrintBacktestReport:
    def test_print_does_not_raise(self, caplog):
        """print_backtest_report should not raise."""
        results = [
            _make_window_result(0, 10, 30.0, 3.0),
            _make_window_result(1, 8, -5.0, 2.0),
        ]
        report = generate_backtest_report(results, {"version": "v001"})
        consistency = check_consistency(results)

        import logging
        with caplog.at_level(logging.INFO):
            print_backtest_report(report, consistency)

        # Should have produced some output
        assert "BACKTEST REPORT" in caplog.text


# ---------------------------------------------------------------------------
# BacktestRunner tests
# ---------------------------------------------------------------------------

class TestBacktestRunnerInit:
    def test_init_loads_version_json(self, tmp_path):
        """BacktestRunner loads version.json on init."""
        # Create mock version directory
        version_info = {
            "feature_names": ["f1", "f2", "f3"],
            "label_params": {
                "use_dynamic_atr": False,
                "tp_pips": 50.0,
                "sl_pips": 30.0,
                "spread_pips": 2.5,
                "slippage_pips": 0.5,
            },
            "xgboost_trade_min_confidence": 0.45,
            "xgboost_trade_min_margin": 0.08,
            "walk_forward": {
                "n_windows": 3,
                "windows": [
                    {"window_id": 0, "test_start": 100, "test_end": 200},
                    {"window_id": 1, "test_start": 300, "test_end": 400},
                    {"window_id": 2, "test_start": 500, "test_end": 600},
                ],
            },
        }

        version_dir = str(tmp_path / "v001")
        os.makedirs(version_dir, exist_ok=True)

        with open(os.path.join(version_dir, "version.json"), "w") as f:
            json.dump(version_info, f)

        # We can't fully init without model/scaler pkls,
        # so we test the version.json loading path
        with pytest.raises(FileNotFoundError, match="xgboost_gold.pkl"):
            from ai_engine.training.backtest_runner import BacktestRunner
            BacktestRunner(version_dir)

    def test_missing_version_json_raises(self, tmp_path):
        """Missing version.json raises FileNotFoundError."""
        from ai_engine.training.backtest_runner import BacktestRunner
        with pytest.raises(FileNotFoundError, match="version.json"):
            BacktestRunner(str(tmp_path))

    def test_window_boundaries_from_version_json(self, tmp_path):
        """Stored window boundaries are read from version.json."""
        version_info = {
            "feature_names": ["f1", "f2"],
            "label_params": {},
            "walk_forward": {
                "windows": [
                    {"window_id": 0, "test_start": 100, "test_end": 200},
                    {"window_id": 1, "test_start": 300, "test_end": 400},
                ],
            },
        }

        version_dir = str(tmp_path / "v001")
        os.makedirs(version_dir, exist_ok=True)
        with open(os.path.join(version_dir, "version.json"), "w") as f:
            json.dump(version_info, f)

        # We'll test _get_window_boundaries by partially constructing
        # (bypassing _load_models via mock)
        from ai_engine.training.backtest_runner import BacktestRunner
        runner = object.__new__(BacktestRunner)
        runner.version_dir = version_dir
        runner.stored_windows = version_info["walk_forward"]["windows"]

        boundaries = runner._get_window_boundaries(1000)
        assert len(boundaries) == 2
        assert boundaries[0]["test_start"] == 100
        assert boundaries[0]["test_end"] == 200
        assert boundaries[1]["test_start"] == 300
        assert boundaries[1]["test_end"] == 400
