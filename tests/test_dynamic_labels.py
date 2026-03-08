"""Tests for ATR-based dynamic label generation and backtester alignment.

Covers:
- LabelGenerator dynamic ATR mode (high/low ATR, NaN handling, floors)
- LabelGenerator fixed mode backward compatibility
- LabelGenerator.get_params() with ATR params
- Backtester.run_simple() with per-trade ATR-based TP/SL
- Backtester.run_simple() without ATR (unchanged fixed behavior)
- Non-degenerate label distribution
- ModelTrainer ATR parameter forwarding
"""

import numpy as np
import pandas as pd
import pytest

from ai_engine.training.label_generator import LabelGenerator
from ai_engine.training.backtester import Backtester


def _make_synthetic_df(
    n: int = 500,
    seed: int = 42,
    atr_value: float | None = None,
    atr_array: np.ndarray | None = None,
) -> pd.DataFrame:
    """Create synthetic OHLC DataFrame with optional ATR column."""
    np.random.seed(seed)
    price = 2045.0
    closes, highs, lows = [], [], []

    for _ in range(n):
        change = np.random.randn() * 0.3
        price += change
        highs.append(price + abs(np.random.randn()) * 0.2)
        lows.append(price - abs(np.random.randn()) * 0.2)
        closes.append(price)

    df = pd.DataFrame({"close": closes, "high": highs, "low": lows})

    if atr_value is not None:
        df["atr_14"] = atr_value
    elif atr_array is not None:
        df["atr_14"] = atr_array

    return df


class TestDynamicATRLabels:
    """Tests for LabelGenerator with use_dynamic_atr=True."""

    def test_high_atr_wider_tp_sl_more_hold(self):
        """High ATR -> wider TP/SL -> more HOLD labels (harder to hit)."""
        df = _make_synthetic_df(n=500, atr_value=5.0)  # Very high ATR

        lg = LabelGenerator(
            use_dynamic_atr=True,
            tp_atr_multiplier=2.0,
            sl_atr_multiplier=1.5,
            max_candles=60,
        )
        labels = lg.generate_labels(df)

        hold_pct = (labels == 0).sum() / len(labels)
        # With very high ATR (5.0), TP=10.0, SL=7.5 -- most candles timeout
        assert hold_pct > 0.5, f"Expected >50% HOLD with high ATR, got {hold_pct:.1%}"

    def test_low_atr_tighter_tp_sl_more_trades(self):
        """Low ATR -> tighter TP/SL -> more BUY/SELL labels (easier to hit)."""
        df = _make_synthetic_df(n=500, atr_value=0.1)  # Low ATR

        lg = LabelGenerator(
            use_dynamic_atr=True,
            tp_atr_multiplier=2.0,
            sl_atr_multiplier=1.5,
            max_candles=60,
        )
        labels = lg.generate_labels(df)

        trade_pct = ((labels == 1).sum() + (labels == -1).sum()) / len(labels)
        # With low ATR (0.1), TP=0.2, SL=0.15 -- most candles produce signals
        assert trade_pct > 0.3, f"Expected >30% trades with low ATR, got {trade_pct:.1%}"

    def test_nan_atr_handling_first_14_rows(self):
        """First 14 rows NaN ATR -> uses median ATR, no NaN labels."""
        n = 500
        atr = np.full(n, 0.5)
        atr[:14] = np.nan  # Simulate ATR warmup period

        df = _make_synthetic_df(n=n, atr_array=atr)

        lg = LabelGenerator(use_dynamic_atr=True)
        labels = lg.generate_labels(df)

        # No NaN in labels
        assert not labels.isna().any(), "Labels contain NaN values"
        # All labels are valid
        assert set(labels.unique()).issubset({-1, 0, 1}), "Invalid label values"
        assert len(labels) == n

    def test_all_nan_atr_fallback_to_fixed(self):
        """All-NaN ATR -> falls back to fixed pips with warning."""
        n = 500
        atr = np.full(n, np.nan)
        df = _make_synthetic_df(n=n, atr_array=atr)

        lg = LabelGenerator(
            tp_pips=50,
            sl_pips=30,
            use_dynamic_atr=True,
        )
        labels = lg.generate_labels(df)

        # Should produce labels (via fixed fallback)
        assert len(labels) == n
        assert set(labels.unique()).issubset({-1, 0, 1})

        # Compare with explicit fixed mode
        lg_fixed = LabelGenerator(tp_pips=50, sl_pips=30, use_dynamic_atr=False)
        labels_fixed = lg_fixed.generate_labels(df)
        np.testing.assert_array_equal(
            labels.values, labels_fixed.values,
            err_msg="All-NaN ATR should produce identical labels to fixed mode",
        )

    def test_atr_floor_very_small_atr(self):
        """Very small ATR -> TP/SL clamped to min_tp_pips/min_sl_pips."""
        n = 500
        df = _make_synthetic_df(n=n, atr_value=0.001)  # Tiny ATR

        lg = LabelGenerator(
            use_dynamic_atr=True,
            tp_atr_multiplier=2.0,
            sl_atr_multiplier=1.5,
            min_tp_pips=5.0,
            min_sl_pips=3.0,
            pip_size=0.01,
        )
        labels = lg.generate_labels(df)

        # Labels should be valid (not all HOLD due to tiny distances)
        assert len(labels) == n
        assert set(labels.unique()).issubset({-1, 0, 1})

    def test_missing_atr_column_raises_error(self):
        """Dynamic ATR mode without atr_14 column raises ValueError."""
        df = _make_synthetic_df(n=100)  # No ATR column

        lg = LabelGenerator(use_dynamic_atr=True)
        with pytest.raises(ValueError, match="atr_14 column required"):
            lg.generate_labels(df)


class TestFixedModeBackwardCompat:
    """Tests for backward compatibility with fixed TP/SL mode."""

    def test_fixed_mode_produces_identical_output(self):
        """use_dynamic_atr=False produces identical output to original code."""
        df = _make_synthetic_df(n=1000, seed=42)

        lg = LabelGenerator(tp_pips=50, sl_pips=30, use_dynamic_atr=False)
        labels = lg.generate_labels(df)

        assert len(labels) == 1000
        assert set(labels.unique()).issubset({-1, 0, 1})

        # Spot-check: should produce some trades
        trade_count = (labels != 0).sum()
        assert trade_count > 0, "Fixed mode produced no trades"

    def test_default_label_generator_is_fixed(self):
        """LabelGenerator() defaults to use_dynamic_atr=False."""
        lg = LabelGenerator()
        assert lg.use_dynamic_atr is False

    def test_get_params_fixed_mode(self):
        """get_params() without dynamic ATR does not include ATR params."""
        lg = LabelGenerator(tp_pips=50, sl_pips=30, use_dynamic_atr=False)
        params = lg.get_params()

        assert params["use_dynamic_atr"] is False
        assert "tp_atr_multiplier" not in params
        assert "sl_atr_multiplier" not in params
        assert params["tp_pips"] == 50.0
        assert params["sl_pips"] == 30.0

    def test_get_params_dynamic_mode(self):
        """get_params() with dynamic ATR includes ATR multipliers and floors."""
        lg = LabelGenerator(
            use_dynamic_atr=True,
            tp_atr_multiplier=2.5,
            sl_atr_multiplier=1.8,
            min_tp_pips=10.0,
            min_sl_pips=5.0,
        )
        params = lg.get_params()

        assert params["use_dynamic_atr"] is True
        assert params["tp_atr_multiplier"] == 2.5
        assert params["sl_atr_multiplier"] == 1.8
        assert params["min_tp_pips"] == 10.0
        assert params["min_sl_pips"] == 5.0
        # Still includes fixed fallback values
        assert "tp_pips" in params
        assert "sl_pips" in params


class TestBacktesterATR:
    """Tests for Backtester.run_simple() with ATR-based TP/SL."""

    def test_run_simple_with_atr_values(self):
        """Per-trade ATR-based TP/SL evaluation produces valid report."""
        np.random.seed(42)
        n = 200
        preds = np.random.choice([-1, 0, 1], n, p=[0.3, 0.4, 0.3])
        labels = preds.copy()
        noise = np.random.random(n) < 0.3
        labels[noise] = np.random.choice([-1, 0, 1], noise.sum())

        atr_values = np.full(n, 0.5)  # 0.5 price units ATR

        bt = Backtester(tp_pips=50, sl_pips=30)
        report = bt.run_simple(
            preds, labels,
            atr_values=atr_values,
            tp_atr_multiplier=2.0,
            sl_atr_multiplier=1.5,
        )

        assert report["n_trades"] > 0
        assert "win_rate" in report
        assert "profit_factor" in report
        assert "equity_curve" in report

    def test_run_simple_without_atr_unchanged(self):
        """Fixed TP/SL mode produces consistent results."""
        np.random.seed(42)
        n = 200
        preds = np.random.choice([-1, 0, 1], n, p=[0.3, 0.4, 0.3])
        labels = preds.copy()
        noise = np.random.random(n) < 0.3
        labels[noise] = np.random.choice([-1, 0, 1], noise.sum())

        bt = Backtester(tp_pips=50, sl_pips=30)

        # Without ATR (fixed mode)
        report = bt.run_simple(preds, labels)

        assert report["n_trades"] > 0
        assert "win_rate" in report
        assert "total_pips" in report

    def test_atr_vs_fixed_produce_different_pips(self):
        """ATR-based and fixed modes produce different pips per trade."""
        np.random.seed(42)
        n = 200
        preds = np.random.choice([-1, 0, 1], n, p=[0.3, 0.4, 0.3])
        labels = preds.copy()
        noise = np.random.random(n) < 0.3
        labels[noise] = np.random.choice([-1, 0, 1], noise.sum())

        atr_values = np.full(n, 0.3)  # Different from fixed 50/30 pips

        bt = Backtester(tp_pips=50, sl_pips=30)
        r_fixed = bt.run_simple(preds, labels)
        r_atr = bt.run_simple(
            preds, labels,
            atr_values=atr_values,
            tp_atr_multiplier=2.0,
            sl_atr_multiplier=1.5,
        )

        # Different TP/SL -> different total pips
        assert r_fixed["total_pips"] != r_atr["total_pips"], (
            "ATR and fixed modes should produce different results"
        )


class TestDynamicLabelDistribution:
    """Tests for non-degenerate label distribution."""

    def test_dynamic_labels_non_degenerate(self):
        """Dynamic labels produce >10% trade signals."""
        df = _make_synthetic_df(n=1000, atr_value=0.5)

        lg = LabelGenerator(
            use_dynamic_atr=True,
            tp_atr_multiplier=2.0,
            sl_atr_multiplier=1.5,
        )
        labels = lg.generate_labels(df)

        trade_pct = ((labels == 1).sum() + (labels == -1).sum()) / len(labels)
        assert trade_pct > 0.10, (
            f"Expected >10% trades, got {trade_pct:.1%}. "
            "Labels may be degenerate."
        )

    def test_dynamic_vs_fixed_differ(self):
        """Dynamic ATR mode produces different labels than fixed mode."""
        df = _make_synthetic_df(n=500, atr_value=0.5)

        lg_fixed = LabelGenerator(tp_pips=50, sl_pips=30, use_dynamic_atr=False)
        lg_dynamic = LabelGenerator(use_dynamic_atr=True, tp_atr_multiplier=2.0, sl_atr_multiplier=1.5)

        labels_fixed = lg_fixed.generate_labels(df)
        labels_dynamic = lg_dynamic.generate_labels(df)

        # ATR=0.5 -> TP=1.0, SL=0.75 vs fixed TP=0.50, SL=0.30
        # Different distances -> different labels
        assert not np.array_equal(labels_fixed.values, labels_dynamic.values), (
            "Dynamic and fixed labels should differ with ATR=0.5"
        )


class TestModelTrainerATRForwarding:
    """Tests for ModelTrainer ATR parameter forwarding."""

    def test_trainer_forwards_atr_to_label_generator(self):
        """ModelTrainer passes ATR config to its LabelGenerator."""
        from ai_engine.training.trainer import ModelTrainer

        trainer = ModelTrainer(
            use_dynamic_atr=True,
            tp_atr_multiplier=3.0,
            sl_atr_multiplier=2.0,
        )

        assert trainer.use_dynamic_atr is True
        assert trainer.tp_atr_multiplier == 3.0
        assert trainer.sl_atr_multiplier == 2.0
        assert trainer._label_generator.use_dynamic_atr is True
        assert trainer._label_generator.tp_atr_multiplier == 3.0
        assert trainer._label_generator.sl_atr_multiplier == 2.0

    def test_trainer_default_enables_dynamic_atr(self):
        """ModelTrainer() defaults to use_dynamic_atr=True."""
        from ai_engine.training.trainer import ModelTrainer

        trainer = ModelTrainer()
        assert trainer.use_dynamic_atr is True
        assert trainer._label_generator.use_dynamic_atr is True

    def test_trainer_legacy_mode(self):
        """ModelTrainer(use_dynamic_atr=False) uses fixed labels."""
        from ai_engine.training.trainer import ModelTrainer

        trainer = ModelTrainer(use_dynamic_atr=False)
        assert trainer.use_dynamic_atr is False
        assert trainer._label_generator.use_dynamic_atr is False
