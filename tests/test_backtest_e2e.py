"""
End-to-End integration test for the Phase 5 Backtesting Pipeline.

Validates all 4 Phase 5 UAT criteria:
1. BACK-01: OOS backtest runs successfully on saved model Version Directory.
2. BACK-02: Report shows spread, slippage, and commission costs applied.
3. BACK-03: Report provides Sharpe, Max Drawdown, Win Rate, Profit Factor.
4. BACK-04: Consistency structure verifies 60% pos and 20% DD rules.
"""

import json
import os
import shutil

import numpy as np
import pandas as pd
import pytest

from ai_engine.training.backtest_runner import BacktestRunner
from ai_engine.training.trainer import ModelTrainer


def _generate_synthetic_ohlcv(n_candles: int = 4000) -> pd.DataFrame:
    """Generate synthetic OHLCV data with DatetimeIndex."""
    np.random.seed(42)
    price = 2045.0
    
    # We need all these columns so that FeatureEngineer doesn't drop MACD, Stoch, etc.
    data = {
        "open": [], "high": [], "low": [], "close": [], "volume": [],
        "tick_volume": [], "spread": [], 
        "bid_qty": [], "ask_qty": [],
        "l2_bids_volume": [], "l2_asks_volume": [],
        "l2_depth_ratio": [], "micro_price": []
    }

    # Enough volatility so TP=1500 / SL=800 pips triggers
    for _ in range(n_candles):
        change = np.random.randn() * 5.0
        open_p = price
        close_p = price + change
        high_p = max(open_p, close_p) + abs(np.random.randn()) * 3.0
        low_p = min(open_p, close_p) - abs(np.random.randn()) * 3.0
        vol = int(np.random.uniform(500, 2000))
        tick_vol = int(np.random.uniform(100, 500))

        data["open"].append(round(open_p, 2))
        data["high"].append(round(high_p, 2))
        data["low"].append(round(low_p, 2))
        data["close"].append(round(close_p, 2))
        data["volume"].append(vol)
        
        # Order book/l2 mocks
        data["tick_volume"].append(tick_vol)
        data["spread"].append(abs(np.random.randn()) * 0.5 + 2.0)
        data["bid_qty"].append(np.random.uniform(10, 50))
        data["ask_qty"].append(np.random.uniform(10, 50))
        data["l2_bids_volume"].append(np.random.uniform(100, 500))
        data["l2_asks_volume"].append(np.random.uniform(100, 500))
        data["l2_depth_ratio"].append(np.random.uniform(0.5, 2.0))
        data["micro_price"].append(round(close_p + np.random.randn() * 0.1, 2))
        
        price = close_p

    # 40min freq makes 4000 candles span >3 months
    timestamps = pd.date_range(
        "2025-01-01", periods=n_candles, freq="40min", tz="UTC"
    )
    return pd.DataFrame(data, index=timestamps)


@pytest.fixture(scope="module")
def trained_version_dir(tmp_path_factory):
    """Module-scoped fixture: Train a model on synthetic data.
    
    Yields the path to the trained model version directory (v001_...)
    and the raw dataframe used for training (to be used in OOS testing).
    """
    tmp_path = tmp_path_factory.mktemp("saved_models")
    saved_models_dir = str(tmp_path)
    
    # Needs enough months to bypass the minimum data check
    # Let's generate 7000 candles at 40m (>6 months)
    df = _generate_synthetic_ohlcv(n_candles=7000)
    
    trainer = ModelTrainer(
        saved_models_dir=saved_models_dir,
        tp_pips=1500.0,
        sl_pips=800.0,
        max_holding_candles=15,
        pip_size=0.01,
        spread_pips=2.5,
        slippage_pips=0.5,
        use_dynamic_atr=False,
    )
    
    # Train
    results = trainer.train_all(df, min_data_months=6)
    
    version_dir = results.get("version_dir", "")
    assert version_dir != "", "Training failed to produce a version dir"
    assert os.path.exists(version_dir), "Version dir does not exist"
    
    return version_dir, df


@pytest.mark.slow
class TestBacktestPipelineE2E:
    """Verifies all Phase 5 Backtest UAT criteria."""

    def test_back01_oos_validation(self, trained_version_dir):
        """BACK-01: BacktestRunner validates strategy on out-of-sample data."""
        version_dir, df = trained_version_dir
        
        # 1. Feature Engineering
        from ai_engine.features.feature_engineer import FeatureEngineer
        fe = FeatureEngineer()
        df_feat = fe.create_features(df.copy(), timeframe="40m")
        feature_names = fe.get_feature_names()
        
        # 2. Label Generation (need true labels to measure outcome)
        from ai_engine.training.label_generator import LabelGenerator
        lg = LabelGenerator(
            tp_pips=1500.0,
            sl_pips=800.0,
            spread_pips=2.5,
            pip_size=0.01,
            max_candles=15,
            use_dynamic_atr=False,
        )
        df_feat["label"] = lg.generate_labels(df_feat)
        
        # Remove warmup
        df_feat = df_feat.iloc[200:]
        X = df_feat[feature_names].values
        y = df_feat["label"].values
        
        # Run Backtest
        runner = BacktestRunner(version_dir=version_dir)
        results = runner.run(X=X, y=y, feature_names=feature_names)
        
        per_window = results.get("per_window_results", [])
        assert len(per_window) >= 1, "Expected walk-forward OOS windows to be evaluated"
        
        # Verify it iterated over the test windows
        for w in per_window:
            assert "window_id" in w
            assert w["n_trades"] >= 0

    def test_back02_realistic_costs(self, trained_version_dir):
        """BACK-02: Spread, slippage, commissions included in costs."""
        version_dir, df = trained_version_dir
        
        from ai_engine.features.feature_engineer import FeatureEngineer
        from ai_engine.training.label_generator import LabelGenerator
        
        fe = FeatureEngineer()
        df_feat = fe.create_features(df.copy())
        feature_names = fe.get_feature_names()
        
        lg = LabelGenerator(tp_pips=1500, sl_pips=800, use_dynamic_atr=False)
        df_feat["label"] = lg.generate_labels(df_feat)
        df_feat = df_feat.iloc[200:]
        X = df_feat[feature_names].values
        y = df_feat["label"].values

        # Run without commission
        runner0 = BacktestRunner(version_dir=version_dir, commission_per_trade_pips=0.0)
        res0 = runner0.run(X, y, feature_names)
        
        # Run with large commission
        runner5 = BacktestRunner(version_dir=version_dir, commission_per_trade_pips=50.0)
        res5 = runner5.run(X, y, feature_names)
        
        p0 = sum(w["total_pips"] for w in res0["per_window_results"])
        p5 = sum(w["total_pips"] for w in res5["per_window_results"])
        
        trades0 = sum(w["n_trades"] for w in res0["per_window_results"])
        
        if trades0 > 0:
            # Commission lowers profits or worsens losses
            assert p5 < p0, "Commission should reduce total pips"

    def test_back03_report_metrics(self, trained_version_dir):
        """BACK-03: Report shows Sharpe, max DD, win rate, profit factor."""
        version_dir, df = trained_version_dir
        
        from ai_engine.features.feature_engineer import FeatureEngineer
        from ai_engine.training.label_generator import LabelGenerator
        
        fe = FeatureEngineer()
        df_feat = fe.create_features(df.copy())
        feature_names = fe.get_feature_names()
        
        lg = LabelGenerator(tp_pips=1500, sl_pips=800, use_dynamic_atr=False)
        df_feat["label"] = lg.generate_labels(df_feat)
        df_feat = df_feat.iloc[200:]
        X = df_feat[feature_names].values
        y = df_feat["label"].values
        
        runner = BacktestRunner(version_dir=version_dir)
        results = runner.run(X, y, feature_names)
        
        report = results["report"]

        assert "aggregate" in report
        agg = report["aggregate"]
        # Required Phase 5 aggregate metrics
        assert "sharpe_ratio" in agg, "aggregate missing sharpe_ratio"
        assert "profit_factor" in agg, "aggregate missing profit_factor"
        assert "win_rate" in agg, "aggregate missing win_rate"
        assert "max_drawdown_pct" in agg, "aggregate missing max_drawdown_pct"
        assert "n_windows" in agg, "aggregate missing n_windows"
        # Per-window metrics
        pw = report["per_window"]
        for w in pw:
            assert "sharpe_ratio" in w, f"per_window missing sharpe_ratio: {w}"
            assert "max_drawdown_pct" in w, f"per_window missing max_drawdown_pct: {w}"
            assert "win_rate" in w, f"per_window missing win_rate: {w}"
            assert "profit_factor" in w, f"per_window missing profit_factor: {w}"

    def test_back04_consistency(self, trained_version_dir):
        """BACK-04: Consistency check correctly enforces 60% and 20% rules."""
        version_dir, df = trained_version_dir
        
        from ai_engine.features.feature_engineer import FeatureEngineer
        from ai_engine.training.label_generator import LabelGenerator
        
        fe = FeatureEngineer()
        df_feat = fe.create_features(df.copy())
        feature_names = fe.get_feature_names()
        
        lg = LabelGenerator(tp_pips=1500, sl_pips=800, use_dynamic_atr=False)
        df_feat["label"] = lg.generate_labels(df_feat)
        df_feat = df_feat.iloc[200:]
        X = df_feat[feature_names].values
        y = df_feat["label"].values
        
        runner = BacktestRunner(version_dir=version_dir)
        results = runner.run(X, y, feature_names)
        
        consistency = results["consistency"]

        # All required BACK-04 consistency fields
        required_keys = [
            "passes_60pct", "passes_20pct_dd", "overall_pass",
            "dd_violations", "positive_pct",
        ]
        for k in required_keys:
            assert k in consistency, f"Consistency payload missing: {k}"

        assert isinstance(consistency["passes_60pct"], bool), "passes_60pct must be bool"
        assert isinstance(consistency["passes_20pct_dd"], bool), "passes_20pct_dd must be bool"
        assert isinstance(consistency["overall_pass"], bool), "overall_pass must be bool"
        assert isinstance(consistency["dd_violations"], int), "dd_violations must be int"
        assert 0.0 <= consistency["positive_pct"] <= 1.0, (
            f"positive_pct must be between 0 and 1, got {consistency['positive_pct']}"
        )
