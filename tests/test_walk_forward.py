"""
Tests for walk-forward validation engine and data duration validation.
"""

import numpy as np
import pandas as pd
import pytest

from ai_engine.training.walk_forward import (
    WindowSpec,
    WalkForwardValidator,
    calculate_walk_forward_windows,
)
from ai_engine.training.data_preparation import DataPreparation


# ---------------------------------------------------------------------------
# WindowSpec tests
# ---------------------------------------------------------------------------

class TestWindowSpec:
    def test_train_size(self):
        ws = WindowSpec(window_id=0, train_start=0, train_end=1500, test_start=1560, test_end=1900)
        assert ws.train_size == 1500

    def test_test_size(self):
        ws = WindowSpec(window_id=0, train_start=0, train_end=1500, test_start=1560, test_end=1900)
        assert ws.test_size == 340

    def test_properties_with_expanding(self):
        """train_start is always 0 for expanding windows."""
        ws = WindowSpec(window_id=2, train_start=0, train_end=5000, test_start=5060, test_end=6000)
        assert ws.train_size == 5000
        assert ws.test_size == 940


# ---------------------------------------------------------------------------
# calculate_walk_forward_windows tests
# ---------------------------------------------------------------------------

class TestCalculateWindows:
    def test_minimum_5_windows_with_10000(self):
        """With 10000 samples, produces >= 5 windows."""
        windows = calculate_walk_forward_windows(n_samples=10000, purge_gap=60)
        assert len(windows) >= 5, f"Expected >= 5 windows, got {len(windows)}"

    def test_windows_expanding(self):
        """Every window has train_start=0 (anchored/expanding)."""
        windows = calculate_walk_forward_windows(n_samples=10000, purge_gap=60)
        for w in windows:
            assert w.train_start == 0, f"Window {w.window_id} has train_start={w.train_start}"

    def test_windows_non_overlapping_test(self):
        """Each window's test_start >= previous window's test_end."""
        windows = calculate_walk_forward_windows(n_samples=10000, purge_gap=60)
        for i in range(1, len(windows)):
            assert windows[i].test_start >= windows[i - 1].test_end, (
                f"Window {i} test_start={windows[i].test_start} < "
                f"window {i-1} test_end={windows[i-1].test_end}"
            )

    def test_windows_purge_gap(self):
        """test_start = train_end + purge_gap for each window."""
        purge_gap = 60
        windows = calculate_walk_forward_windows(n_samples=10000, purge_gap=purge_gap)
        for w in windows:
            assert w.test_start == w.train_end + purge_gap, (
                f"Window {w.window_id}: test_start={w.test_start} != "
                f"train_end({w.train_end}) + purge_gap({purge_gap})"
            )

    def test_windows_test_ratio(self):
        """test_size is approximately 20% of total window size (within tolerance)."""
        windows = calculate_walk_forward_windows(n_samples=12000, purge_gap=60)
        # Check windows that are not truncated by dataset boundary
        for w in windows[:-1]:  # Skip last window which may be truncated
            total = w.train_size + w.test_size
            ratio = w.test_size / total
            # 20% target with some tolerance (min_test_samples can skew small windows)
            assert 0.10 <= ratio <= 0.30, (
                f"Window {w.window_id}: test ratio={ratio:.3f} "
                f"(expected ~0.20, train={w.train_size}, test={w.test_size})"
            )

    def test_small_dataset_fewer_windows(self):
        """With 3000 samples, still produces valid windows (may be < 5)."""
        windows = calculate_walk_forward_windows(
            n_samples=3000, min_train_samples=1500, purge_gap=60
        )
        assert len(windows) >= 1, "Should produce at least 1 window with 3000 samples"
        # Verify windows are valid
        for w in windows:
            assert w.train_start == 0
            assert w.train_end > 0
            assert w.test_start > w.train_end
            assert w.test_end > w.test_start

    def test_empty_for_tiny_dataset(self):
        """Very small dataset produces no windows."""
        windows = calculate_walk_forward_windows(
            n_samples=500, min_train_samples=1500, purge_gap=60
        )
        assert len(windows) == 0

    def test_train_end_grows(self):
        """Each window's train_end should grow (expanding)."""
        windows = calculate_walk_forward_windows(n_samples=10000, purge_gap=60)
        for i in range(1, len(windows)):
            assert windows[i].train_end > windows[i - 1].train_end


# ---------------------------------------------------------------------------
# WalkForwardValidator.calculate_windows tests
# ---------------------------------------------------------------------------

class TestWalkForwardValidator:
    def test_calculate_windows_delegates(self):
        """Validator.calculate_windows delegates to module function."""
        v = WalkForwardValidator(purge_gap=60)
        windows = v.calculate_windows(10000)
        direct = calculate_walk_forward_windows(n_samples=10000, purge_gap=60)
        assert len(windows) == len(direct)
        for a, b in zip(windows, direct):
            assert a.window_id == b.window_id
            assert a.train_end == b.train_end
            assert a.test_start == b.test_start
            assert a.test_end == b.test_end

    def test_run_all_windows_raises_on_insufficient_data(self):
        """run_all_windows raises ValueError when no windows can be created."""
        v = WalkForwardValidator(purge_gap=60, min_train_samples=5000)
        X = np.random.randn(100, 5).astype(np.float32)
        y = np.random.choice([-1, 0, 1], 100)

        class FakeTrainer:
            pass

        with pytest.raises(ValueError, match="Cannot create walk-forward windows"):
            v.run_all_windows(X, y, ["f1", "f2", "f3", "f4", "f5"], FakeTrainer())


# ---------------------------------------------------------------------------
# Data duration validation tests
# ---------------------------------------------------------------------------

class TestValidateMinimumDuration:
    def _make_df(self, start: str, periods: int, freq: str = "5min") -> pd.DataFrame:
        idx = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
        return pd.DataFrame(
            {"close": np.random.randn(periods)},
            index=idx,
        )

    def test_passes_with_7_months(self):
        """7 months of data passes validation."""
        # 7 months at 5-min intervals: ~7*30*24*12 = ~60480 candles
        df = self._make_df("2025-01-01", periods=60480, freq="5min")
        dp = DataPreparation()
        # Should not raise
        dp.validate_minimum_duration(df, min_months=6)

    def test_fails_with_4_months(self):
        """4 months of data raises ValueError."""
        # 4 months: ~4*30*24*12 = ~34560 candles
        df = self._make_df("2025-01-01", periods=34560, freq="5min")
        dp = DataPreparation()
        with pytest.raises(ValueError, match="Insufficient data"):
            dp.validate_minimum_duration(df, min_months=6)

    def test_fails_without_datetime_index(self):
        """Non-DatetimeIndex raises ValueError."""
        df = pd.DataFrame({"close": [1, 2, 3]})
        dp = DataPreparation()
        with pytest.raises(ValueError, match="DatetimeIndex"):
            dp.validate_minimum_duration(df, min_months=6)

    def test_passes_just_over_6_months(self):
        """Just over 6 months of data passes."""
        # 6.1 months: ~6.1*30.44*24*12 = ~53540 5-min candles
        df = self._make_df("2025-01-01", periods=53600, freq="5min")
        dp = DataPreparation()
        dp.validate_minimum_duration(df, min_months=6)
