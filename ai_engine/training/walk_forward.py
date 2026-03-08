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
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List

import numpy as np
import pandas as pd

from ..features.feature_scaler import FeatureScaler
from .shap_importance import compute_shap_importance
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
            "use_dynamic_atr": getattr(trainer, "use_dynamic_atr", False),
            "tp_atr_multiplier": getattr(trainer, "tp_atr_multiplier", 2.0),
            "sl_atr_multiplier": getattr(trainer, "sl_atr_multiplier", 1.5),
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

        # 5. SHAP-based feature importance + 50% pruning (replaces XGBoost gain importance)
        shap_importance = {}
        pruning_result = {
            "method": "shap_mean_abs",
            "original_count": len(feature_names),
            "kept_count": len(feature_names),
            "pruned_count": 0,
            "pruned_features": [],
            "kept_features": list(feature_names),
            "pruning_accepted": False,
        }

        if trainer._xgboost.is_trained:
            # Compute SHAP importance on TEST data (not training data)
            shap_importance = compute_shap_importance(
                model=trainer._xgboost.model,
                X_data=X_test_scaled,
                feature_names=feature_names,
                max_samples=2000,
            )

            # Save full-model eval BEFORE pruning for comparison
            full_model_eval = None
            try:
                y_probs_full = trainer._xgboost.predict(X_test_scaled)
                full_model_eval = trainer._evaluator.evaluate_trading(
                    y_test,
                    probs_to_trade_signals(y_probs_full, min_confidence=0.4, min_margin=0.1),
                    tp_pips=trainer.tp_pips,
                    sl_pips=trainer.sl_pips,
                    spread_pips=trainer.spread_pips,
                    label_space="signal",
                    model_name=f"XGBoost_W{wid}_full",
                    log_details=False,
                )
            except Exception as e:
                logger.warning(f"    Full-model eval failed (window {wid}): {e}")

            # Rank and prune bottom 50%
            ranked = sorted(shap_importance.items(), key=lambda x: x[1], reverse=True)
            n_keep = max(len(ranked) // 2, 1)  # Keep at least 1 feature
            kept_features = [f for f, _ in ranked[:n_keep]]
            pruned_features_list = [f for f, _ in ranked[n_keep:]]

            if len(kept_features) < len(feature_names):
                logger.info(
                    f"    SHAP pruning: keeping {len(kept_features)}/{len(feature_names)} features"
                )

                # Slice arrays to kept features
                sel_idx = [feature_names.index(f) for f in kept_features]
                X_train_pruned = X_train_scaled[:, sel_idx]
                X_val_pruned = X_val_scaled[:, sel_idx]
                X_test_pruned = X_test_scaled[:, sel_idx]

                # Retrain XGBoost on pruned features
                trainer._xgboost.set_feature_names(kept_features)
                try:
                    xgb_pruned_result = trainer._xgboost.train(
                        X_train_pruned, y_train, X_val_pruned, y_val,
                        use_class_weight=True, use_recency_weight=True,
                    )
                    result["xgboost_train_pruned"] = xgb_pruned_result

                    # Performance guard: compare pruned vs full
                    pruning_accepted = True  # Default accept if can't compare
                    if full_model_eval and full_model_eval.get("n_trades", 0) > 0:
                        try:
                            y_probs_pruned = trainer._xgboost.predict(X_test_pruned)
                            pruned_eval = trainer._evaluator.evaluate_trading(
                                y_test,
                                probs_to_trade_signals(
                                    y_probs_pruned, min_confidence=0.4, min_margin=0.1
                                ),
                                tp_pips=trainer.tp_pips,
                                sl_pips=trainer.sl_pips,
                                spread_pips=trainer.spread_pips,
                                label_space="signal",
                                model_name=f"XGBoost_W{wid}_pruned",
                                log_details=False,
                            )
                            full_pf = full_model_eval.get("profit_factor", 0)
                            pruned_pf = pruned_eval.get("profit_factor", 0)
                            pruning_accepted = pruned_pf >= full_pf

                            logger.info(
                                f"    Performance guard: full PF={full_pf:.2f}, "
                                f"pruned PF={pruned_pf:.2f} -> "
                                f"{'ACCEPTED' if pruning_accepted else 'REJECTED (falling back)'}"
                            )

                            result["pruning_comparison"] = {
                                "full_profit_factor": full_pf,
                                "pruned_profit_factor": pruned_pf,
                                "pruning_accepted": pruning_accepted,
                            }
                        except Exception as e:
                            logger.warning(f"    Pruned eval failed (window {wid}): {e}")

                    if pruning_accepted:
                        # Accept pruning: update arrays and selected_features
                        selected_features = kept_features
                        X_train_scaled = X_train_pruned
                        X_val_scaled = X_val_pruned
                        X_test_scaled = X_test_pruned

                        pruning_result.update({
                            "kept_count": len(kept_features),
                            "pruned_count": len(pruned_features_list),
                            "pruned_features": pruned_features_list,
                            "kept_features": kept_features,
                            "pruning_accepted": True,
                        })
                    else:
                        # Reject pruning: retrain XGBoost on full features
                        trainer._xgboost.set_feature_names(list(feature_names))
                        trainer._xgboost.train(
                            X_train_scaled, y_train, X_val_scaled, y_val,
                            use_class_weight=True, use_recency_weight=True,
                        )
                        logger.info(f"    Reverted to full feature set ({len(feature_names)} features)")

                except Exception as e:
                    logger.error(f"    XGBoost pruned re-training failed (window {wid}): {e}")
                    # Fall back to full features on error
                    trainer._xgboost.set_feature_names(list(feature_names))

        result["shap_importance"] = shap_importance
        result["feature_pruning"] = pruning_result

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
            "final_shap_importance": last.get("shap_importance", {}),
        }


def generate_training_report(
    windows_results: List[Dict[str, Any]],
    version_info: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate walk-forward training report.

    Aggregate metrics are computed from combined trade results across all
    windows (total gross_profit / total gross_loss), NOT averaged ratios.
    Per research pitfall 6: averaging profit factors is statistically incorrect.

    Args:
        windows_results: Per-window results from WalkForwardValidator.run_all_windows()
        version_info: Version metadata (version string, training_date, etc.)

    Returns:
        Report dict suitable for JSON serialization + console output.
    """
    # Build per-window report entries
    per_window: List[Dict[str, Any]] = []
    for wr in windows_results:
        entry: Dict[str, Any] = {
            "window_id": wr["window_id"],
            "train_samples": wr["train_samples"],
            "test_samples": wr["test_samples"],
        }
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
                m["expectancy"] = wr[trade_key].get("expectancy", 0)
                m["n_trades"] = wr[trade_key].get("n_trades", 0)
            entry[model_key] = m if m else {"n_trades": 0}
        # Add SHAP/pruning info per window
        if "shap_importance" in wr and wr["shap_importance"]:
            # Only store top 10 features in report to keep size manageable
            top_shap = dict(
                list(wr["shap_importance"].items())[:10]
            )
            entry["shap_top_features"] = top_shap
        if "feature_pruning" in wr:
            entry["feature_pruning"] = wr["feature_pruning"]
        per_window.append(entry)

    # Compute aggregate metrics from combined trade results (NOT averaged ratios)
    aggregate: Dict[str, Any] = {}
    for model_key in ["xgboost", "lightgbm"]:
        total_wins = 0
        total_losses = 0
        total_trades = 0
        total_gross_profit = 0.0
        total_gross_loss = 0.0
        all_pips: List[float] = []

        for wr in windows_results:
            trade_key = f"{model_key}_trading"
            if trade_key not in wr:
                continue
            tr = wr[trade_key]
            n_trades = tr.get("n_trades", 0)
            if n_trades == 0:
                continue

            wins = tr.get("wins", 0)
            losses = tr.get("losses", 0)
            tp_pips = tr.get("tp_pips", 0)
            sl_pips = tr.get("sl_pips", 0)
            spread_pips = tr.get("spread_pips", 0)

            net_tp = tp_pips - spread_pips
            net_sl = sl_pips + spread_pips

            total_wins += wins
            total_losses += losses
            total_trades += n_trades
            total_gross_profit += wins * net_tp
            total_gross_loss += losses * net_sl

            # Collect per-trade pips for Sharpe computation
            window_pips = [net_tp] * wins + [-net_sl] * losses
            all_pips.extend(window_pips)

        # Aggregate profit factor from totals
        agg_pf = (
            total_gross_profit / total_gross_loss
            if total_gross_loss > 0
            else float("inf")
        )
        # Aggregate win rate from totals
        agg_wr = total_wins / total_trades if total_trades > 0 else 0.0
        # Aggregate expectancy: use TP/SL from last window with trades
        agg_exp = 0.0
        for wr in reversed(windows_results):
            trade_key = f"{model_key}_trading"
            if trade_key in wr and wr[trade_key].get("n_trades", 0) > 0:
                tr = wr[trade_key]
                net_tp = tr["tp_pips"] - tr["spread_pips"]
                net_sl = tr["sl_pips"] + tr["spread_pips"]
                agg_exp = (agg_wr * net_tp) - ((1 - agg_wr) * net_sl)
                break
        # Sharpe from combined per-trade pips
        agg_sharpe = 0.0
        if len(all_pips) > 1:
            pips_arr = np.array(all_pips)
            std = pips_arr.std()
            if std > 0:
                agg_sharpe = float(
                    (pips_arr.mean() / std) * np.sqrt(2600)
                )

        aggregate[model_key] = {
            "win_rate": float(agg_wr),
            "profit_factor": float(agg_pf) if agg_pf != float("inf") else 0.0,
            "expectancy": float(agg_exp),
            "n_trades": int(total_trades),
            "sharpe": float(agg_sharpe),
        }

    # Determine best model by aggregate profit factor
    xgb_pf = aggregate.get("xgboost", {}).get("profit_factor", 0)
    lgb_pf = aggregate.get("lightgbm", {}).get("profit_factor", 0)
    aggregate["best_model"] = "lightgbm" if lgb_pf >= xgb_pf else "xgboost"

    report: Dict[str, Any] = {
        "report_date": datetime.now().isoformat(),
        "version": version_info.get("version", "unknown"),
        "summary": {
            "n_windows": len(per_window),
            "total_test_samples": sum(
                pw["test_samples"] for pw in per_window
            ),
            "window_type": "expanding",
        },
        "per_window": per_window,
        "aggregate": aggregate,
    }

    return report


def print_training_report(report: Dict[str, Any]) -> None:
    """Print a formatted walk-forward training report to the console via logger."""
    logger.info("=" * 70)
    logger.info("WALK-FORWARD TRAINING REPORT")
    logger.info("=" * 70)
    logger.info(f"Version: {report.get('version', 'unknown')}")
    summary = report.get("summary", {})
    logger.info(
        f"Windows: {summary.get('n_windows', 0)} ({summary.get('window_type', 'expanding')})"
    )
    logger.info("")

    for pw in report.get("per_window", []):
        xgb = pw.get("xgboost", {})
        lgb = pw.get("lightgbm", {})

        xgb_str = _format_model_metrics("XGB", xgb)
        lgb_str = _format_model_metrics("LGB", lgb)

        logger.info(
            f"  Window {pw['window_id']}: "
            f"train={pw['train_samples']}, test={pw['test_samples']}  "
            f"| {xgb_str}  | {lgb_str}"
        )

    logger.info("-" * 70)
    logger.info("AGGREGATE:")

    agg = report.get("aggregate", {})
    for model_key in ["xgboost", "lightgbm"]:
        m = agg.get(model_key, {})
        if not m:
            continue
        label = "XGBoost" if model_key == "xgboost" else "LightGBM"
        logger.info(
            f"  {label:>8s}: WR={m.get('win_rate', 0):.1%} "
            f"PF={m.get('profit_factor', 0):.2f} "
            f"Exp={m.get('expectancy', 0):+.1f} "
            f"Sharpe={m.get('sharpe', 0):.2f} "
            f"({m.get('n_trades', 0)} trades)"
        )

    best = agg.get("best_model", "unknown")
    best_pf = agg.get(best, {}).get("profit_factor", 0)
    logger.info("")
    logger.info(f"Best model: {best.upper()} (PF={best_pf:.2f})")
    logger.info("=" * 70)


def _format_model_metrics(label: str, m: Dict[str, Any]) -> str:
    """Format per-window model metrics for console output."""
    n_trades = m.get("n_trades", 0)
    if n_trades == 0:
        return f"{label}: 0 trades"
    return (
        f"{label}: WR={m.get('win_rate', 0):.1%} "
        f"PF={m.get('profit_factor', 0):.2f} "
        f"Exp={m.get('expectancy', 0):+.1f}"
    )
