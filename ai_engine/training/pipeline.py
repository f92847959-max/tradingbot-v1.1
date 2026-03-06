"""
Training Pipeline -- Walk-forward training orchestration.

Contains the step-by-step pipeline logic extracted from ModelTrainer.train_all().
Steps 1-5 prepare data (validate, features, labels, warmup, split X/y).
Steps 6-7 run walk-forward validation and save models + metadata.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List

import numpy as np
import pandas as pd

from .model_versioning import (
    create_version_dir,
    write_version_json,
    update_production_pointer,
    cleanup_old_versions,
)
from .trade_filter import probs_to_trade_signals, tune_trade_filter
from .walk_forward import WalkForwardValidator

if TYPE_CHECKING:
    from .trainer import ModelTrainer

logger = logging.getLogger(__name__)


class TrainingPipeline:
    """Executes the full training pipeline on behalf of a ModelTrainer."""

    def __init__(self, trainer: ModelTrainer) -> None:
        self._t = trainer

    def run(
        self,
        df: pd.DataFrame,
        timeframe: str = "5m",
        feature_selection: bool = True,
        min_feature_importance: float = 0.005,
    ) -> Dict[str, Any]:
        """Run the walk-forward training pipeline.

        Steps 1-5 run once on the full dataset (data validation, feature
        engineering, label generation, warmup removal, feature/label separation).
        Steps 6-7 use walk-forward validation across expanding windows,
        then save models and metadata from the final window.
        """
        start_time = time.time()
        results: Dict[str, Any] = {}

        # ================================================================
        # Step 1: Validate data (+ 6-month minimum check)
        # ================================================================
        logger.info(f"\n{'='*60}")
        logger.info(f"1/7 Validating data... ({len(df)} candles)")
        logger.info(f"{'='*60}")

        required_cols = ["open", "high", "low", "close"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns: {missing}")
        if len(df) < 500:
            logger.warning(f"Only {len(df)} candles -- minimum 2000 recommended!")

        # 6-month minimum data validation (TRAIN-07)
        if isinstance(df.index, pd.DatetimeIndex):
            self._t._data_prep.validate_minimum_duration(df, min_months=6)
        else:
            logger.warning(
                "DataFrame does not have DatetimeIndex -- "
                "skipping duration validation"
            )

        # ================================================================
        # Step 2: Compute features (on full dataset -- safe for lookback indicators)
        # ================================================================
        logger.info(f"\n2/7 Computing features...")
        df = self._t._feature_engineer.create_features(df, timeframe=timeframe)
        feature_names = self._t._feature_engineer.get_feature_names()
        logger.info(f"  -> {len(feature_names)} features created")

        # ================================================================
        # Step 3: Generate labels
        # ================================================================
        logger.info(
            f"\n3/7 Generating labels "
            f"(Triple Barrier + Spread={self._t.spread_pips} pips)..."
        )
        df["label"] = self._t._label_generator.generate_labels(df)
        raw_label_stats = self._t._label_generator.get_label_stats(df["label"])
        results["label_stats_raw"] = raw_label_stats

        # ================================================================
        # Step 4: Remove warmup period
        # ================================================================
        logger.info(f"\n4/7 Removing warmup period...")
        df = self._t._data_prep.remove_warmup_period(df, warmup_candles=200)
        label_tail = int(
            getattr(self._t._label_generator, "max_candles", 0) or 0
        )
        if label_tail > 0 and len(df) > label_tail:
            df = df.iloc[:-label_tail].copy()
            logger.info(f"  -> Label horizon tail removed: {label_tail} candles")
        label_stats = self._t._label_generator.get_label_stats(df["label"])
        results["label_stats"] = label_stats

        # ================================================================
        # Step 5: Separate features and labels
        # ================================================================
        logger.info(f"\n5/7 Separating features and labels...")
        X, y = self._t._data_prep.prepare_features_labels(
            df, feature_names, "label"
        )
        logger.info(f"  -> X: {X.shape}, y: {y.shape}")

        # ================================================================
        # Step 6: Walk-forward validation
        # ================================================================
        logger.info(f"\n6/7 Running walk-forward validation...")

        # Compute dynamic purge gap ONCE before the loop
        max_label_horizon = int(
            getattr(self._t._label_generator, "max_candles", 60) or 60
        )
        dynamic_purge_gap = min(max_label_horizon, max(8, len(X) // 20))

        validator = WalkForwardValidator(
            purge_gap=dynamic_purge_gap,
            min_train_samples=1500,
            min_test_samples=200,
        )
        windows = validator.calculate_windows(len(X))
        logger.info(f"  Walk-forward: {len(windows)} expanding windows")
        logger.info(f"  Purge gap: {dynamic_purge_gap} candles")

        wf_results = validator.run_all_windows(X, y, feature_names, self._t)

        # Extract walk-forward data
        window_results = wf_results["windows"]
        final_scaler = wf_results["final_scaler"]
        final_trade_filters = wf_results["final_trade_filters"]
        final_feature_names = wf_results["final_feature_names"]
        final_eval_results = wf_results["final_eval_results"]

        results["walk_forward_windows"] = window_results
        results["n_windows"] = wf_results["n_windows"]

        # Populate backward-compatible keys from last window
        last_window = window_results[-1] if window_results else {}
        if "xgboost_train" in last_window:
            results["xgboost_train"] = last_window["xgboost_train"]
        if "xgboost_train_selected" in last_window:
            results["xgboost_train_selected"] = last_window[
                "xgboost_train_selected"
            ]
        if "lightgbm_train" in last_window:
            results["lightgbm_train"] = last_window["lightgbm_train"]
        if "xgboost_eval" in last_window:
            results["xgboost_eval"] = last_window["xgboost_eval"]
        if "lightgbm_eval" in last_window:
            results["lightgbm_eval"] = last_window["lightgbm_eval"]
        if "xgboost_trading" in last_window:
            results["xgboost_trading"] = last_window["xgboost_trading"]
        if "lightgbm_trading" in last_window:
            results["lightgbm_trading"] = last_window["lightgbm_trading"]
        if "xgboost_trade_filter" in last_window:
            results["xgboost_trade_filter"] = last_window[
                "xgboost_trade_filter"
            ]
        if "lightgbm_trade_filter" in last_window:
            results["lightgbm_trade_filter"] = last_window[
                "lightgbm_trade_filter"
            ]

        # Feature selection info from last window
        if "feature_selection" in last_window:
            results["feature_selection"] = last_window["feature_selection"]

        # ================================================================
        # Step 7: Save models with versioning
        # ================================================================
        logger.info(f"\n7/7 Saving models with versioning...")

        # Update trainer's scaler reference for backward compat
        if final_scaler is not None:
            self._t._scaler = final_scaler

        # Create versioned directory
        version_dir = create_version_dir(self._t.saved_models_dir)

        # Save model files to version directory
        if self._t._xgboost.is_trained:
            self._t._xgboost.save(
                os.path.join(version_dir, "xgboost_gold.pkl")
            )
        if self._t._lightgbm.is_trained:
            self._t._lightgbm.save(
                os.path.join(version_dir, "lightgbm_gold.pkl")
            )

        # Save the LAST WINDOW's scaler (production scaler)
        if final_scaler is not None:
            final_scaler.save(os.path.join(version_dir, "feature_scaler.pkl"))

        # Build version data (extends existing metadata format)
        duration = time.time() - start_time
        version_name = os.path.basename(version_dir)

        # Collect per-window metrics for version.json
        wf_window_summaries = []
        for wr in window_results:
            window_metrics: Dict[str, Any] = {}
            for model_key in ["xgboost", "lightgbm"]:
                eval_key = f"{model_key}_eval"
                trade_key = f"{model_key}_trading"
                m: Dict[str, Any] = {}
                if eval_key in wr:
                    m["accuracy"] = wr[eval_key].get("accuracy", 0)
                    m["f1"] = wr[eval_key].get("f1_score", 0)
                if trade_key in wr:
                    m["win_rate"] = wr[trade_key].get("win_rate", 0)
                    m["profit_factor"] = wr[trade_key].get("profit_factor", 0)
                    m["expectancy"] = wr[trade_key].get("expectancy_pips", 0)
                    m["n_trades"] = wr[trade_key].get("n_trades", 0)
                window_metrics[model_key] = m if m else {"error": "not trained"}
            wf_window_summaries.append({
                "window_id": wr["window_id"],
                "train_samples": wr["train_samples"],
                "test_samples": wr["test_samples"],
                "metrics": window_metrics,
            })

        # Compute aggregate metrics across all windows
        aggregate_metrics: Dict[str, Any] = {}
        for model_key in ["xgboost", "lightgbm"]:
            all_win_rates = []
            all_profit_factors = []
            all_expectancies = []
            total_trades = 0
            for ws in wf_window_summaries:
                m = ws["metrics"].get(model_key, {})
                if "win_rate" in m:
                    all_win_rates.append(m["win_rate"])
                if "profit_factor" in m:
                    all_profit_factors.append(m["profit_factor"])
                if "expectancy" in m:
                    all_expectancies.append(m["expectancy"])
                total_trades += m.get("n_trades", 0)
            aggregate_metrics[model_key] = {
                "win_rate": (
                    sum(all_win_rates) / len(all_win_rates)
                    if all_win_rates
                    else 0
                ),
                "profit_factor": (
                    sum(all_profit_factors) / len(all_profit_factors)
                    if all_profit_factors
                    else 0
                ),
                "expectancy": (
                    sum(all_expectancies) / len(all_expectancies)
                    if all_expectancies
                    else 0
                ),
                "n_trades": total_trades,
            }

        # Compute data range info
        data_range: Dict[str, Any] = {"n_candles": len(X)}
        if isinstance(df.index, pd.DatetimeIndex) and len(df) > 1:
            duration_days = (df.index[-1] - df.index[0]).days
            data_range["months_of_data"] = round(duration_days / 30.44, 1)

        # Build version_data with ALL existing metadata fields + new fields
        version_data: Dict[str, Any] = {
            # Existing metadata fields (backward compat)
            "training_date": datetime.now().isoformat(),
            "timeframe": timeframe,
            "n_samples_total": len(X),
            "n_features_original": len(feature_names),
            "n_features_selected": len(final_feature_names),
            "feature_names": final_feature_names,
            "label_params": self._t._label_generator.get_params(),
            "training_duration_seconds": round(duration, 1),
            # NEW: Version metadata
            "version": version_name.split("_")[0],  # e.g., "v001"
            "version_dir": version_name,
            # NEW: Data range info
            "data_range": data_range,
            # NEW: Walk-forward results (TRAIN-05)
            "walk_forward": {
                "n_windows": len(window_results),
                "window_type": "expanding",
                "purge_gap_candles": dynamic_purge_gap,
                "windows": wf_window_summaries,
            },
            # NEW: Aggregate metrics
            "aggregate_metrics": aggregate_metrics,
        }

        # Add last-window flat metrics for backward compatibility
        for eval_r in final_eval_results:
            mk = eval_r["model_name"].lower().split("_w")[0]
            version_data[f"{mk}_accuracy"] = eval_r["accuracy"]
            version_data[f"{mk}_f1"] = eval_r["f1_score"]

        for model_name, filter_info in final_trade_filters.items():
            mk = model_name.lower()
            version_data[f"{mk}_trade_min_confidence"] = filter_info[
                "min_confidence"
            ]
            version_data[f"{mk}_trade_min_margin"] = filter_info[
                "min_margin"
            ]
            val_tr = filter_info.get("validation_trading", {})
            version_data[f"{mk}_val_trade_win_rate"] = val_tr.get("win_rate")
            version_data[f"{mk}_val_trade_profit_factor"] = val_tr.get(
                "profit_factor"
            )
            version_data[f"{mk}_val_trade_count"] = val_tr.get("n_trades")

        for model_key in ["xgboost", "lightgbm"]:
            trade_key = f"{model_key}_trading"
            if trade_key in last_window:
                tr = last_window[trade_key]
                version_data[f"{model_key}_win_rate"] = tr.get("win_rate", 0)
                version_data[f"{model_key}_profit_factor"] = tr.get(
                    "profit_factor", 0
                )
                version_data[f"{model_key}_sharpe"] = tr.get(
                    "sharpe_ratio", 0
                )

        # Write version.json, update production pointer, cleanup old versions
        write_version_json(version_dir, version_data)
        update_production_pointer(self._t.saved_models_dir, version_dir)
        cleanup_old_versions(self._t.saved_models_dir, keep=5)

        logger.info(f"\n{'='*60}")
        logger.info(
            f"Training complete! Duration: {duration:.1f}s "
            f"({len(window_results)} walk-forward windows)"
        )
        logger.info(f"Version: {version_name}")
        logger.info(f"Models saved to: {version_dir}")
        logger.info(f"{'='*60}")

        results["metadata"] = version_data
        results["version_dir"] = version_dir
        return results
