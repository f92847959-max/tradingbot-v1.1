"""
Walk-Forward Validation -- Expanding window validation for ML trading models.

Replaces the single chronological split with multiple expanding (anchored)
windows. Each window trains on all data from the start up to a cutoff,
then tests on the subsequent period. The training portion grows with
each window while test periods are non-overlapping.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List

import numpy as np
import pandas as pd

from ..features.feature_scaler import FeatureScaler
from .trade_filter import probs_to_trade_signals, tune_trade_filter

if TYPE_CHECKING:
    from .trainer import ModelTrainer

logger = logging.getLogger(__name__)


@dataclass
class WindowSpec:
    """Specification for a single walk-forward window."""

    window_id: int
    train_start: int  # Always 0 for expanding windows
    train_end: int
    test_start: int  # train_end + purge_gap
    test_end: int

    @property
    def train_size(self) -> int:
        return self.train_end - self.train_start

    @property
    def test_size(self) -> int:
        return self.test_end - self.test_start


def calculate_walk_forward_windows(
    n_samples: int,
    min_train_samples: int = 1500,
    purge_gap: int = 60,
    min_test_samples: int = 200,
) -> List[WindowSpec]:
    """
    Calculate expanding walk-forward windows dynamically.

    Test period = 20% of total window size (= 25% of train size).
    Windows are non-overlapping in test period.
    Training always starts from index 0 (expanding/anchored).

    Args:
        n_samples: Total number of samples after warmup removal
        min_train_samples: Minimum first window training size
        purge_gap: Gap between train/test to prevent label leakage
        min_test_samples: Minimum test period size

    Returns:
        List of WindowSpec describing each window
    """
    windows: List[WindowSpec] = []
    train_end = min_train_samples
    window_id = 0

    while train_end < n_samples:
        test_size = max(int(train_end * 0.25), min_test_samples)
        test_start = train_end + purge_gap
        test_end = min(test_start + test_size, n_samples)

        actual_test_size = test_end - test_start
        if actual_test_size < min_test_samples:
            break  # Not enough data for a valid test period

        windows.append(
            WindowSpec(
                window_id=window_id,
                train_start=0,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
        )

        window_id += 1
        train_end = test_end  # Next window trains up to end of this test

    return windows


class WalkForwardValidator:
    """Execute walk-forward validation across expanding windows."""

    def __init__(
        self,
        purge_gap: int = 60,
        min_train_samples: int = 1500,
        min_test_samples: int = 200,
    ) -> None:
        self.purge_gap = purge_gap
        self.min_train_samples = min_train_samples
        self.min_test_samples = min_test_samples

    def calculate_windows(self, n_samples: int) -> List[WindowSpec]:
        """Calculate expanding walk-forward windows. Delegates to module function."""
        return calculate_walk_forward_windows(
            n_samples=n_samples,
            min_train_samples=self.min_train_samples,
            purge_gap=self.purge_gap,
            min_test_samples=self.min_test_samples,
        )

    def run_window(
        self,
        window: WindowSpec,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
        trainer: "ModelTrainer",
    ) -> Dict[str, Any]:
        """Execute training pipeline steps for a single walk-forward window.

        This method:
        1. Slices X, y by window indices
        2. Creates a fresh FeatureScaler, fits on window's training data ONLY
        3. Splits training into train/val (85/15) for early stopping + trade filter
        4. Trains XGBoost + LightGBM
        5. Runs feature selection (importance-based, using XGBoost)
        6. Re-trains on selected features if any dropped
        7. Tunes trade filter on validation subset
        8. Evaluates ML + trading metrics on test portion
        9. Returns per-window results dict
        """
        wid = window.window_id
        logger.info(
            f"\n  --- Window {wid}: train[{window.train_start}:{window.train_end}] "
            f"test[{window.test_start}:{window.test_end}] "
            f"(train={window.train_size}, test={window.test_size}) ---"
        )

        result: Dict[str, Any] = {
            "window_id": wid,
            "train_start": window.train_start,
            "train_end": window.train_end,
            "test_start": window.test_start,
            "test_end": window.test_end,
            "train_samples": window.train_size,
            "test_samples": window.test_size,
        }

        # 1. Slice data by window
        X_train_full = X[window.train_start : window.train_end]
        y_train_full = y[window.train_start : window.train_end]
        X_test = X[window.test_start : window.test_end]
        y_test = y[window.test_start : window.test_end]

        # 2. Split training into train (85%) and val (15%) for early stopping + tuning
        val_split = int(len(X_train_full) * 0.85)
        X_train = X_train_full[:val_split]
        y_train = y_train_full[:val_split]
        X_val = X_train_full[val_split:]
        y_val = y_train_full[val_split:]

        logger.info(
            f"    Split: train={len(X_train)}, val={len(X_val)}, test={len(X_test)}"
        )

        # 3. Create FRESH scaler per window -- fit on training data only
        scaler = FeatureScaler()
        train_df = pd.DataFrame(X_train, columns=feature_names)
        scaler.fit(train_df, feature_names)

        X_train_scaled = scaler.transform(
            pd.DataFrame(X_train, columns=feature_names)
        )[feature_names].values
        X_val_scaled = scaler.transform(
            pd.DataFrame(X_val, columns=feature_names)
        )[feature_names].values
        X_test_scaled = scaler.transform(
            pd.DataFrame(X_test, columns=feature_names)
        )[feature_names].values

        # Set feature names on models
        for model in [trainer._xgboost, trainer._lightgbm]:
            model.set_feature_names(feature_names)

        selected_features = list(feature_names)

        # 4. Train XGBoost (initial, before feature selection)
        logger.info(f"    Training XGBoost (window {wid})...")
        try:
            xgb_result = trainer._xgboost.train(
                X_train_scaled,
                y_train,
                X_val_scaled,
                y_val,
                use_class_weight=True,
                use_recency_weight=True,
            )
            result["xgboost_train"] = xgb_result
        except Exception as e:
            logger.error(f"    XGBoost training failed (window {wid}): {e}")
            result["xgboost_train"] = {"error": str(e)}

        # 5. Feature selection (importance-based using XGBoost)
        if trainer._xgboost.is_trained:
            importance = trainer._xgboost.get_feature_importance()
            total_imp = sum(importance.values()) or 1
            selected_features = [
                f
                for f, imp in importance.items()
                if imp / total_imp >= 0.005  # min_feature_importance
            ]
            if not selected_features:
                selected_features = list(feature_names)

            dropped = len(feature_names) - len(selected_features)
            if dropped > 0:
                logger.info(
                    f"    Feature selection: kept {len(selected_features)}, "
                    f"dropped {dropped}"
                )
                sel_idx = [
                    feature_names.index(f)
                    for f in selected_features
                    if f in feature_names
                ]
                X_train_scaled = X_train_scaled[:, sel_idx]
                X_val_scaled = X_val_scaled[:, sel_idx]
                X_test_scaled = X_test_scaled[:, sel_idx]

                # Re-train XGBoost on selected features
                trainer._xgboost.set_feature_names(selected_features)
                try:
                    xgb_result = trainer._xgboost.train(
                        X_train_scaled,
                        y_train,
                        X_val_scaled,
                        y_val,
                        use_class_weight=True,
                        use_recency_weight=True,
                    )
                    result["xgboost_train_selected"] = xgb_result
                except Exception as e:
                    logger.error(f"    XGBoost re-training failed (window {wid}): {e}")

            result["feature_selection"] = {
                "original": len(feature_names),
                "selected": len(selected_features),
                "dropped": dropped,
            }

        # 6. Train LightGBM on selected features
        trainer._lightgbm.set_feature_names(selected_features)
        logger.info(
            f"    Training LightGBM on {len(selected_features)} features (window {wid})..."
        )
        try:
            lgb_result = trainer._lightgbm.train(
                X_train_scaled,
                y_train,
                X_val_scaled,
                y_val,
                use_recency_weight=True,
            )
            result["lightgbm_train"] = lgb_result
        except Exception as e:
            logger.error(f"    LightGBM training failed (window {wid}): {e}")
            result["lightgbm_train"] = {"error": str(e)}

        # 7. Evaluate + tune trade filter on each model
        eval_results = []
        model_predictions = {}
        trade_filters: Dict[str, Dict[str, Any]] = {}

        for name, model in [
            ("XGBoost", trainer._xgboost),
            ("LightGBM", trainer._lightgbm),
        ]:
            if not model.is_trained:
                continue
            try:
                y_probs_test = model.predict(X_test_scaled)
                y_probs_val = model.predict(X_val_scaled)

                # ML evaluation on test
                eval_result = trainer._evaluator.evaluate_probabilities(
                    y_test,
                    y_probs_test,
                    label_space="signal",
                    model_name=f"{name}_W{wid}",
                )
                eval_results.append(eval_result)
                result[f"{name.lower()}_eval"] = eval_result

                # Trade filter tuning on val
                trade_filter = tune_trade_filter(
                    y_true_val=y_val,
                    y_probs_val=y_probs_val,
                    model_name=f"{name}_W{wid}",
                    evaluator=trainer._evaluator,
                    tp_pips=trainer.tp_pips,
                    sl_pips=trainer.sl_pips,
                    spread_pips=trainer.spread_pips,
                )
                trade_filters[name] = trade_filter
                result[f"{name.lower()}_trade_filter"] = trade_filter

                # Trading evaluation on test with tuned filter
                y_pred_trade = probs_to_trade_signals(
                    y_probs_test,
                    min_confidence=trade_filter["min_confidence"],
                    min_margin=trade_filter["min_margin"],
                )
                model_predictions[name] = y_pred_trade

                trading_eval = trainer._evaluator.evaluate_trading(
                    y_test,
                    y_pred_trade,
                    tp_pips=trainer.tp_pips,
                    sl_pips=trainer.sl_pips,
                    spread_pips=trainer.spread_pips,
                    label_space="signal",
                    model_name=f"{name}_W{wid}",
                    log_details=False,
                )
                result[f"{name.lower()}_trading"] = trading_eval

                logger.info(
                    "    %s W%d: acc=%.3f f1=%.3f | WR=%.1f%% PF=%.2f trades=%d",
                    name,
                    wid,
                    eval_result.get("accuracy", 0),
                    eval_result.get("f1_score", 0),
                    trading_eval.get("win_rate", 0) * 100,
                    trading_eval.get("profit_factor", 0),
                    trading_eval.get("n_trades", 0),
                )

            except Exception as e:
                logger.error(f"    {name} evaluation failed (window {wid}): {e}")

        result["eval_results"] = eval_results
        result["trade_filters"] = trade_filters
        result["selected_features"] = selected_features
        result["scaler"] = scaler

        return result

    def run_all_windows(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
        trainer: "ModelTrainer",
    ) -> Dict[str, Any]:
        """Run walk-forward validation across all windows.

        Returns dict with:
        - "windows": List of per-window results
        - "final_models": dict with xgboost/lightgbm references
        - "final_scaler": Scaler from last window
        - "final_trade_filters": Trade filters from last window
        - "final_feature_names": Selected features from last window
        """
        windows = self.calculate_windows(len(X))

        if not windows:
            raise ValueError(
                f"Cannot create walk-forward windows from {len(X)} samples "
                f"(min_train={self.min_train_samples}, purge_gap={self.purge_gap}, "
                f"min_test={self.min_test_samples}). Need more data."
            )

        logger.info(f"\n{'='*60}")
        logger.info(f"Walk-Forward Validation: {len(windows)} windows")
        logger.info(f"  Purge gap: {self.purge_gap} candles")
        logger.info(f"  Window type: expanding (anchored)")
        for w in windows:
            logger.info(
                f"  W{w.window_id}: train[0:{w.train_end}]({w.train_size}) "
                f"gap({self.purge_gap}) "
                f"test[{w.test_start}:{w.test_end}]({w.test_size})"
            )
        logger.info(f"{'='*60}")

        window_results: List[Dict[str, Any]] = []
        for window in windows:
            w_result = self.run_window(window, X, y, feature_names, trainer)
            window_results.append(w_result)

        # Final window provides production models
        last = window_results[-1]

        return {
            "windows": window_results,
            "n_windows": len(windows),
            "final_scaler": last.get("scaler"),
            "final_trade_filters": last.get("trade_filters", {}),
            "final_feature_names": last.get("selected_features", feature_names),
            "final_eval_results": last.get("eval_results", []),
        }
