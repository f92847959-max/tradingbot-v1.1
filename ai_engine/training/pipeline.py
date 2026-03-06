"""
Training Pipeline -- Walk-forward training orchestration.

Contains the step-by-step pipeline logic extracted from ModelTrainer.train_all().
Steps 1-12 cover data validation, feature engineering, label generation,
splitting, scaling, feature selection, model training, evaluation, and saving.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict

import numpy as np
import pandas as pd

from .trade_filter import probs_to_trade_signals, tune_trade_filter

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
        """Run the complete 12-step training pipeline."""
        start_time = time.time()
        results: Dict[str, Any] = {}

        # Step 1: Validate data
        logger.info(f"\n{'='*60}")
        logger.info(f"1/12 Daten pruefen... ({len(df)} Candles)")
        logger.info(f"{'='*60}")

        required_cols = ["open", "high", "low", "close"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Fehlende Spalten: {missing}")
        if len(df) < 500:
            logger.warning(f"Nur {len(df)} Candles -- min. 2000 empfohlen!")

        # Step 2: Compute features
        logger.info(f"\n2/12 Features berechnen...")
        df = self._t._feature_engineer.create_features(df, timeframe=timeframe)
        feature_names = self._t._feature_engineer.get_feature_names()
        logger.info(f"  -> {len(feature_names)} Features erstellt")

        # Step 3: Generate labels
        logger.info(f"\n3/12 Labels generieren (Triple Barrier + Spread={self._t.spread_pips} Pips)...")
        df["label"] = self._t._label_generator.generate_labels(df)
        raw_label_stats = self._t._label_generator.get_label_stats(df["label"])
        results["label_stats_raw"] = raw_label_stats

        # Step 4: Remove warmup period
        logger.info(f"\n4/12 Warmup-Periode entfernen...")
        df = self._t._data_prep.remove_warmup_period(df, warmup_candles=200)
        label_tail = int(getattr(self._t._label_generator, "max_candles", 0) or 0)
        if label_tail > 0 and len(df) > label_tail:
            df = df.iloc[:-label_tail].copy()
            logger.info(f"  -> Label-Horizon-Tail entfernt: {label_tail} Candles")
        label_stats = self._t._label_generator.get_label_stats(df["label"])
        results["label_stats"] = label_stats

        # Step 5: Separate features and labels
        logger.info(f"\n5/12 Features und Labels trennen...")
        X, y = self._t._data_prep.prepare_features_labels(df, feature_names, "label")
        logger.info(f"  -> X: {X.shape}, y: {y.shape}")

        # Step 6: Chronological split with purging gap
        logger.info(f"\n6/12 Chronologischer Split (70/15/15) + Purging-Gap...")
        max_label_horizon = int(getattr(self._t._label_generator, "max_candles", 60) or 60)
        dynamic_purge_gap = min(max_label_horizon, max(8, len(X) // 20))
        splits = self._t._data_prep.split_chronological(X, y, purge_gap=dynamic_purge_gap)
        X_train, y_train = splits["train"]
        X_val_full, y_val_full = splits["val"]
        X_test, y_test = splits["test"]

        tune_split_idx = int(len(X_val_full) * 0.67)
        X_val, y_val = X_val_full[:tune_split_idx], y_val_full[:tune_split_idx]
        X_tune, y_tune = X_val_full[tune_split_idx:], y_val_full[tune_split_idx:]
        logger.info(f"  Val/Tune split: val={len(X_val)}, tune={len(X_tune)}")

        # Step 7: Scale features
        logger.info(f"\n7/12 Features skalieren (StandardScaler)...")
        train_df = pd.DataFrame(X_train, columns=feature_names)
        self._t._scaler.fit(train_df, feature_names)

        X_train_scaled = self._t._scaler.transform(
            pd.DataFrame(X_train, columns=feature_names)
        )[feature_names].values
        X_val_scaled = self._t._scaler.transform(
            pd.DataFrame(X_val, columns=feature_names)
        )[feature_names].values
        X_test_scaled = self._t._scaler.transform(
            pd.DataFrame(X_test, columns=feature_names)
        )[feature_names].values
        X_tune_scaled = self._t._scaler.transform(
            pd.DataFrame(X_tune, columns=feature_names)
        )[feature_names].values

        scaler_path = os.path.join(self._t.saved_models_dir, "feature_scaler.pkl")
        self._t._scaler.save(scaler_path)

        for model in [self._t._xgboost, self._t._lightgbm]:
            model.set_feature_names(feature_names)

        selected_features = feature_names

        # Step 8: Train XGBoost (initial, before feature selection)
        logger.info(f"\n8/12 Modelle trainieren (mit class_weight + recency)...")

        logger.info(f"\n  8a) XGBoost trainieren...")
        try:
            xgb_result = self._t._xgboost.train(
                X_train_scaled, y_train, X_val_scaled, y_val,
                use_class_weight=True, use_recency_weight=True,
            )
            results["xgboost_train"] = xgb_result
        except Exception as e:
            logger.error(f"XGBoost Training fehlgeschlagen: {e}")
            results["xgboost_train"] = {"error": str(e)}

        # Step 9: Feature selection (optional, importance-based)
        if feature_selection and self._t._xgboost.is_trained:
            logger.info(f"\n9/12 Feature-Selektion (Importance > {min_feature_importance*100}%)...")
            importance = self._t._xgboost.get_feature_importance()
            total_imp = sum(importance.values()) or 1
            selected_features = [
                f for f, imp in importance.items()
                if imp / total_imp >= min_feature_importance
            ]
            dropped = len(feature_names) - len(selected_features)
            logger.info(f"  -> {len(selected_features)} Features behalten, {dropped} entfernt")
            results["feature_selection"] = {
                "original": len(feature_names),
                "selected": len(selected_features),
                "dropped": dropped,
                "top_10": list(importance.items())[:10],
            }

        if len(selected_features) < len(feature_names):
            sel_idx = [feature_names.index(f) for f in selected_features if f in feature_names]
            X_train_scaled = X_train_scaled[:, sel_idx]
            X_val_scaled = X_val_scaled[:, sel_idx]
            X_test_scaled = X_test_scaled[:, sel_idx]
            feature_names = selected_features

            logger.info(f"  Re-training XGBoost on {len(selected_features)} selected features...")
            self._t._xgboost.set_feature_names(selected_features)
            try:
                xgb_result = self._t._xgboost.train(
                    X_train_scaled, y_train, X_val_scaled, y_val,
                    use_class_weight=True, use_recency_weight=True,
                )
                results["xgboost_train_selected"] = xgb_result
            except Exception as e:
                logger.error(f"XGBoost re-training fehlgeschlagen: {e}")

        self._t._lightgbm.set_feature_names(selected_features)

        # Step 8b/9b: Train LightGBM on selected features
        logger.info(f"\n  LightGBM trainieren (auf {len(selected_features)} Features)...")
        try:
            lgb_result = self._t._lightgbm.train(
                X_train_scaled, y_train, X_val_scaled, y_val,
                use_recency_weight=True,
            )
            results["lightgbm_train"] = lgb_result
        except Exception as e:
            logger.error(f"LightGBM Training fehlgeschlagen: {e}")
            results["lightgbm_train"] = {"error": str(e)}

        # Step 10: ML evaluation on test set
        logger.info(f"\n10/12 ML-Evaluation auf Test-Set...")

        eval_results = []
        model_predictions = {}
        trade_filters: Dict[str, Dict[str, Any]] = {}

        for name, model in [("XGBoost", self._t._xgboost), ("LightGBM", self._t._lightgbm)]:
            if not model.is_trained:
                continue
            try:
                y_probs_test = model.predict(X_test_scaled)
                y_probs_tune = model.predict(X_tune_scaled)

                eval_result = self._t._evaluator.evaluate_probabilities(
                    y_test, y_probs_test, label_space="signal", model_name=name
                )
                eval_results.append(eval_result)
                results[f"{name.lower()}_eval"] = eval_result

                trade_filter = tune_trade_filter(
                    y_true_val=y_tune,
                    y_probs_val=y_probs_tune,
                    model_name=name,
                    evaluator=self._t._evaluator,
                    tp_pips=self._t.tp_pips,
                    sl_pips=self._t.sl_pips,
                    spread_pips=self._t.spread_pips,
                )
                trade_filters[name] = trade_filter
                results[f"{name.lower()}_trade_filter"] = trade_filter

                y_pred_trade = probs_to_trade_signals(
                    y_probs_test,
                    min_confidence=trade_filter["min_confidence"],
                    min_margin=trade_filter["min_margin"],
                )
                model_predictions[name] = y_pred_trade
                logger.info(
                    "  %s Trade-Filter: min_conf=%.2f min_margin=%.2f | val_pf=%.3f val_wr=%.3f val_trades=%d",
                    name,
                    trade_filter["min_confidence"],
                    trade_filter["min_margin"],
                    float(trade_filter["validation_trading"].get("profit_factor", 0.0) or 0.0),
                    float(trade_filter["validation_trading"].get("win_rate", 0.0) or 0.0),
                    int(trade_filter["validation_trading"].get("n_trades", 0) or 0),
                )
            except Exception as e:
                logger.error(f"{name} Evaluation fehlgeschlagen: {e}")
        if eval_results:
            comparison = self._t._evaluator.compare_models(eval_results)
            results["ml_comparison"] = comparison

        # Step 11: Trading evaluation and backtest
        logger.info(f"\n11/12 Trading-Evaluation & Backtest...")

        trading_results = []
        for name, y_pred in model_predictions.items():
            try:
                trading_eval = self._t._evaluator.evaluate_trading(
                    y_test, y_pred,
                    tp_pips=self._t.tp_pips,
                    sl_pips=self._t.sl_pips,
                    spread_pips=self._t.spread_pips,
                    label_space="signal",
                    model_name=name,
                )
                trading_results.append(trading_eval)
                results[f"{name.lower()}_trading"] = trading_eval
            except Exception as e:
                logger.error(f"{name} Trading-Eval fehlgeschlagen: {e}")

        if trading_results:
            trading_comparison = self._t._evaluator.compare_trading(trading_results)
            results["trading_comparison"] = trading_comparison

        if model_predictions:
            best_name = max(
                trading_results,
                key=lambda x: x.get("profit_factor", 0)
            )["model_name"] if trading_results else list(model_predictions.keys())[0]

            best_pred = model_predictions[best_name]
            backtest = self._t._backtester.run_simple(best_pred, y_test)
            results["backtest"] = backtest
            results["best_model_for_trading"] = best_name

        # Step 12: Save models and metadata
        logger.info(f"\n12/12 Modelle und Metadata speichern...")

        if self._t._xgboost.is_trained:
            self._t._xgboost.save(os.path.join(self._t.saved_models_dir, "xgboost_gold.pkl"))
        if self._t._lightgbm.is_trained:
            self._t._lightgbm.save(os.path.join(self._t.saved_models_dir, "lightgbm_gold.pkl"))

        metadata = {
            "training_date": datetime.now().isoformat(),
            "timeframe": timeframe,
            "n_samples_total": len(X),
            "n_samples_train": len(X_train),
            "n_samples_val": len(X_val),
            "n_samples_test": len(X_test),
            "purge_gap_candles": dynamic_purge_gap,
            "n_features_original": len(feature_names),
            "n_features_selected": len(selected_features),
            "feature_names": selected_features,
            "label_params": self._t._label_generator.get_params(),
            "label_stats_raw": raw_label_stats,
            "label_stats": label_stats,
            "training_duration_seconds": round(time.time() - start_time, 1),
        }

        for eval_r in eval_results:
            model_key = eval_r["model_name"].lower()
            metadata[f"{model_key}_accuracy"] = eval_r["accuracy"]
            metadata[f"{model_key}_f1"] = eval_r["f1_score"]

        for tr in trading_results:
            model_key = tr["model_name"].lower()
            metadata[f"{model_key}_win_rate"] = tr["win_rate"]
            metadata[f"{model_key}_profit_factor"] = tr["profit_factor"]
            metadata[f"{model_key}_sharpe"] = tr["sharpe_ratio"]

        for model_name, filter_info in trade_filters.items():
            model_key = model_name.lower()
            metadata[f"{model_key}_trade_min_confidence"] = filter_info["min_confidence"]
            metadata[f"{model_key}_trade_min_margin"] = filter_info["min_margin"]
            val_tr = filter_info.get("validation_trading", {})
            metadata[f"{model_key}_val_trade_win_rate"] = val_tr.get("win_rate")
            metadata[f"{model_key}_val_trade_profit_factor"] = val_tr.get("profit_factor")
            metadata[f"{model_key}_val_trade_count"] = val_tr.get("n_trades")

        meta_path = os.path.join(self._t.saved_models_dir, "model_metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        duration = time.time() - start_time
        logger.info(f"\n{'='*60}")
        logger.info(f"Training komplett! Dauer: {duration:.1f}s")
        logger.info(f"Modelle gespeichert in: {self._t.saved_models_dir}")
        logger.info(f"{'='*60}")

        results["metadata"] = metadata
        return results
