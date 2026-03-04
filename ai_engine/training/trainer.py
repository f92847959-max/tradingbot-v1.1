"""
Trainer â€“ VollstÃ¤ndige Training-Pipeline (Optimiert).

Orchestriert den gesamten Training-Prozess:
Daten laden â†’ Features berechnen â†’ Labels generieren â†’
Split â†’ Skalieren â†’ Modelle trainieren â†’ Evaluieren â†’
Backtester â†’ Speichern.

Verbesserungen:
- Backtester-Integration fÃ¼r ehrliche Performance-Messung
- Feature-Importance-basierte Selektion
- class_weight statt Undersampling
- Trading-spezifische Metriken im Report
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ..features.feature_engineer import FeatureEngineer
from ..features.feature_scaler import FeatureScaler
from ..models.xgboost_model import XGBoostModel
from ..models.lightgbm_model import LightGBMModel
from .label_generator import LabelGenerator
from .data_preparation import DataPreparation
from .evaluation import ModelEvaluator
from .backtester import Backtester
from .trade_filter import probs_to_trade_signals, trade_metrics_rank, tune_trade_filter

logger = logging.getLogger(__name__)


class ModelTrainer:
    """
    Komplette Training-Pipeline fÃ¼r alle 3 Modelle.

    10-Schritte-Pipeline:
    1. Historische Daten laden & pruefen
    2. Features berechnen
    3. Labels generieren (mit Spread-Kosten)
    4. Warmup-Periode entfernen
    5. Features/Labels trennen
    6. Chronologischer Split (mit Purging-Gap)
    7. Features skalieren
    8. Feature-Selektion (Importance-basiert)
    9. Modelle trainieren (XGBoost + LightGBM)
    10. Evaluieren, Backtest, Speichern
    """

    def __init__(
        self,
        saved_models_dir: str = "ai_engine/saved_models",
        tp_pips: float = 50.0,
        sl_pips: float = 30.0,
        max_holding_candles: int = 60,
        pip_size: float = 0.01,
        spread_pips: float = 2.5,
        slippage_pips: float = 0.5,
    ) -> None:
        """
        Initialisiert den ModelTrainer.

        Args:
            saved_models_dir: Pfad zum Speichern der Modelle
            tp_pips: Take-Profit in Pips fÃ¼r Label-Generierung
            sl_pips: Stop-Loss in Pips fÃ¼r Label-Generierung
            max_holding_candles: Max. Haltedauer fÃ¼r Label-Generierung
            pip_size: Pip-GrÃ¶ÃŸe fÃ¼r Gold
            spread_pips: Spread-Kosten fÃ¼r Labels
            slippage_pips: Slippage fÃ¼r Labels
        """
        self.saved_models_dir = saved_models_dir
        self.tp_pips = tp_pips
        self.sl_pips = sl_pips
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips

        self._feature_engineer = FeatureEngineer()
        self._label_generator = LabelGenerator(
            tp_pips=tp_pips,
            sl_pips=sl_pips,
            max_candles=max_holding_candles,
            pip_size=pip_size,
            spread_pips=spread_pips,
            slippage_pips=slippage_pips,
        )
        self._data_prep = DataPreparation(
            train_ratio=0.70,
            val_ratio=0.15,
            test_ratio=0.15,
        )
        self._evaluator = ModelEvaluator()
        self._scaler = FeatureScaler()
        self._backtester = Backtester(
            tp_pips=tp_pips,
            sl_pips=sl_pips,
            spread_pips=spread_pips,
            slippage_pips=slippage_pips,
        )

        # Modelle (nur XGBoost + LightGBM, CPU-only)
        self._xgboost = XGBoostModel()
        self._lightgbm = LightGBMModel()

        os.makedirs(saved_models_dir, exist_ok=True)
        logger.info(f"ModelTrainer initialisiert. Modelle â†’ {saved_models_dir}")

    def train_all(
        self,
        df: pd.DataFrame,
        timeframe: str = "5m",
        feature_selection: bool = True,
        min_feature_importance: float = 0.005,
    ) -> Dict[str, Any]:
        """
        FÃ¼hrt die komplette Training-Pipeline aus.

        Args:
            df: DataFrame mit OHLCV + technischen Indikatoren
            timeframe: Timeframe der Daten
            feature_selection: Feature-Selektion basierend auf Importance
            min_feature_importance: Min. Importance fÃ¼r Feature-Selektion

        Returns:
            Dict mit Training-Ergebnissen, ML- und Trading-Metriken
        """
        start_time = time.time()
        results = {}

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # SCHRITT 1: Daten prÃ¼fen
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        logger.info(f"\n{'='*60}")
        logger.info(f"1/12 ðŸ“¥ Daten prÃ¼fen... ({len(df)} Candles)")
        logger.info(f"{'='*60}")

        required_cols = ["open", "high", "low", "close"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Fehlende Spalten: {missing}")

        if len(df) < 500:
            logger.warning(f"âš ï¸ Nur {len(df)} Candles â€“ min. 2000 empfohlen!")

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # SCHRITT 2: Features berechnen
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        logger.info(f"\n2/12 ðŸ§® Features berechnen...")
        df = self._feature_engineer.create_features(df, timeframe=timeframe)
        feature_names = self._feature_engineer.get_feature_names()
        logger.info(f"  â†’ {len(feature_names)} Features erstellt")

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # SCHRITT 3: Labels generieren (MIT Spread!)
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        logger.info(f"\n3/12 ðŸ·ï¸ Labels generieren (Triple Barrier + Spread={self.spread_pips} Pips)...")
        df["label"] = self._label_generator.generate_labels(df)
        raw_label_stats = self._label_generator.get_label_stats(df["label"])
        results["label_stats_raw"] = raw_label_stats

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # SCHRITT 4: Warmup-Periode entfernen
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        logger.info(f"\n4/12 ðŸ§¹ Warmup-Periode entfernen...")
        df = self._data_prep.remove_warmup_period(df, warmup_candles=200)

        # Letzte max_candles sind Label-Horizon-Randzone ohne vollstaendige Zukunft.
        label_tail = int(getattr(self._label_generator, "max_candles", 0) or 0)
        if label_tail > 0 and len(df) > label_tail:
            df = df.iloc[:-label_tail].copy()
            logger.info(f"  â†’ Label-Horizon-Tail entfernt: {label_tail} Candles")

        label_stats = self._label_generator.get_label_stats(df["label"])
        results["label_stats"] = label_stats

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # SCHRITT 5: Features und Labels trennen
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        logger.info(f"\n5/12 âœ‚ï¸ Features und Labels trennen...")
        X, y = self._data_prep.prepare_features_labels(df, feature_names, "label")
        logger.info(f"  â†’ X: {X.shape}, y: {y.shape}")

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # SCHRITT 6: Chronologischer Split (mit Purging-Gap)
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        logger.info(f"\n6/12 ðŸ“Š Chronologischer Split (70/15/15) + Purging-Gap...")
        max_label_horizon = int(getattr(self._label_generator, "max_candles", 60) or 60)
        dynamic_purge_gap = min(max_label_horizon, max(8, len(X) // 20))
        splits = self._data_prep.split_chronological(X, y, purge_gap=dynamic_purge_gap)
        X_train, y_train = splits["train"]
        X_val_full, y_val_full = splits["val"]
        X_test, y_test = splits["test"]

        # Sub-split validation into val (for early stopping) and tune (for trade filter tuning)
        # This prevents overfitting the trade filter to the same data used for evaluation
        tune_split_idx = int(len(X_val_full) * 0.67)  # ~10% val, ~5% tune of total
        X_val, y_val = X_val_full[:tune_split_idx], y_val_full[:tune_split_idx]
        X_tune, y_tune = X_val_full[tune_split_idx:], y_val_full[tune_split_idx:]
        logger.info(f"  Val/Tune split: val={len(X_val)}, tune={len(X_tune)}")

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # SCHRITT 7: Features skalieren
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        logger.info(f"\n7/12 ðŸ“ Features skalieren (StandardScaler)...")
        train_df = pd.DataFrame(X_train, columns=feature_names)
        self._scaler.fit(train_df, feature_names)

        X_train_scaled = self._scaler.transform(
            pd.DataFrame(X_train, columns=feature_names)
        )[feature_names].values
        X_val_scaled = self._scaler.transform(
            pd.DataFrame(X_val, columns=feature_names)
        )[feature_names].values
        X_test_scaled = self._scaler.transform(
            pd.DataFrame(X_test, columns=feature_names)
        )[feature_names].values
        X_tune_scaled = self._scaler.transform(
            pd.DataFrame(X_tune, columns=feature_names)
        )[feature_names].values

        scaler_path = os.path.join(self.saved_models_dir, "feature_scaler.pkl")
        self._scaler.save(scaler_path)

        # Feature-Namen an Modelle weitergeben
        for model in [self._xgboost, self._lightgbm]:
            model.set_feature_names(feature_names)

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # SCHRITT 8: Feature-Selektion (optional)
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        selected_features = feature_names  # Default: alle

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # SCHRITT 9: Modelle trainieren (mit class_weight + recency)
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        logger.info(f"\n9/12 ðŸ‹ï¸ Modelle trainieren (mit class_weight + recency)...")

        # 9a: XGBoost
        logger.info(f"\n  9a) XGBoost trainieren...")
        try:
            xgb_result = self._xgboost.train(
                X_train_scaled, y_train, X_val_scaled, y_val,
                use_class_weight=True, use_recency_weight=True,
            )
            results["xgboost_train"] = xgb_result
        except Exception as e:
            logger.error(f"âŒ XGBoost Training fehlgeschlagen: {e}")
            results["xgboost_train"] = {"error": str(e)}

        # Feature Selection nach XGBoost (wenn aktiviert) + re-slice data
        if feature_selection and self._xgboost.is_trained:
            logger.info(f"\n8/12 ðŸŽ¯ Feature-Selektion (Importance > {min_feature_importance*100}%)...")
            importance = self._xgboost.get_feature_importance()
            total_imp = sum(importance.values()) or 1
            selected_features = [
                f for f, imp in importance.items()
                if imp / total_imp >= min_feature_importance
            ]
            dropped = len(feature_names) - len(selected_features)
            logger.info(f"  â†’ {len(selected_features)} Features behalten, {dropped} entfernt")
            results["feature_selection"] = {
                "original": len(feature_names),
                "selected": len(selected_features),
                "dropped": dropped,
                "top_10": list(importance.items())[:10],
            }

        # Apply feature selection: re-slice data arrays and re-train
        if len(selected_features) < len(feature_names):
            sel_idx = [feature_names.index(f) for f in selected_features if f in feature_names]
            X_train_scaled = X_train_scaled[:, sel_idx]
            X_val_scaled = X_val_scaled[:, sel_idx]
            X_test_scaled = X_test_scaled[:, sel_idx]
            feature_names = selected_features

            # Re-train XGBoost on selected features only
            logger.info(f"  Re-training XGBoost on {len(selected_features)} selected features...")
            self._xgboost.set_feature_names(selected_features)
            try:
                xgb_result = self._xgboost.train(
                    X_train_scaled, y_train, X_val_scaled, y_val,
                    use_class_weight=True, use_recency_weight=True,
                )
                results["xgboost_train_selected"] = xgb_result
            except Exception as e:
                logger.error(f"XGBoost re-training fehlgeschlagen: {e}")

        # Update feature names for LightGBM
        self._lightgbm.set_feature_names(selected_features)

        # 9b: LightGBM (trained on selected features)
        logger.info(f"\n  9b) LightGBM trainieren (auf {len(selected_features)} Features)...")
        try:
            lgb_result = self._lightgbm.train(
                X_train_scaled, y_train, X_val_scaled, y_val,
                use_recency_weight=True,
            )
            results["lightgbm_train"] = lgb_result
        except Exception as e:
            logger.error(f"âŒ LightGBM Training fehlgeschlagen: {e}")
            results["lightgbm_train"] = {"error": str(e)}

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # SCHRITT 10: ML-Evaluation auf Test-Set
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        logger.info(f"\n10/10 ML-Evaluation auf Test-Set...")

        eval_results = []
        model_predictions = {}
        trade_filters: Dict[str, Dict[str, Any]] = {}

        for name, model in [("XGBoost", self._xgboost), ("LightGBM", self._lightgbm)]:
            if not model.is_trained:
                continue
            try:
                y_probs_test = model.predict(X_test_scaled)
                y_probs_tune = model.predict(X_tune_scaled)

                eval_result = self._evaluator.evaluate_probabilities(
                    y_test, y_probs_test, label_space="signal", model_name=name
                )
                eval_results.append(eval_result)
                results[f"{name.lower()}_eval"] = eval_result

                # Tune trade filter on separate tune set (not val) to avoid overfitting
                trade_filter = tune_trade_filter(
                    y_true_val=y_tune,
                    y_probs_val=y_probs_tune,
                    model_name=name,
                    evaluator=self._evaluator,
                    tp_pips=self.tp_pips,
                    sl_pips=self.sl_pips,
                    spread_pips=self.spread_pips,
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
                logger.error(f"❌ {name} Evaluation fehlgeschlagen: {e}")
        if eval_results:
            comparison = self._evaluator.compare_models(eval_results)
            results["ml_comparison"] = comparison

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # SCHRITT 11: Trading-Evaluation & Backtest
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        logger.info(f"\n11/12 ðŸ’° Trading-Evaluation & Backtest...")

        trading_results = []
        for name, y_pred in model_predictions.items():
            try:
                trading_eval = self._evaluator.evaluate_trading(
                    y_test, y_pred,
                    tp_pips=self.tp_pips,
                    sl_pips=self.sl_pips,
                    spread_pips=self.spread_pips,
                    label_space="signal",
                    model_name=name,
                )
                trading_results.append(trading_eval)
                results[f"{name.lower()}_trading"] = trading_eval
            except Exception as e:
                logger.error(f"âŒ {name} Trading-Eval fehlgeschlagen: {e}")

        if trading_results:
            trading_comparison = self._evaluator.compare_trading(trading_results)
            results["trading_comparison"] = trading_comparison

        # Backtest auf bestes Modell
        if model_predictions:
            # Nutze das Modell mit bestem Profit Factor
            best_name = max(
                trading_results,
                key=lambda x: x.get("profit_factor", 0)
            )["model_name"] if trading_results else list(model_predictions.keys())[0]

            best_pred = model_predictions[best_name]
            backtest = self._backtester.run_simple(best_pred, y_test)
            results["backtest"] = backtest
            results["best_model_for_trading"] = best_name

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # SCHRITT 12: Modelle speichern
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        logger.info(f"\n12/12 ðŸ’¾ Modelle und Metadata speichern...")

        if self._xgboost.is_trained:
            self._xgboost.save(os.path.join(self.saved_models_dir, "xgboost_gold.pkl"))
        if self._lightgbm.is_trained:
            self._lightgbm.save(os.path.join(self.saved_models_dir, "lightgbm_gold.pkl"))

        # Metadata
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
            "label_params": self._label_generator.get_params(),
            "label_stats_raw": raw_label_stats,
            "label_stats": label_stats,
            "training_duration_seconds": round(time.time() - start_time, 1),
        }

        # ML-Metriken
        for eval_r in eval_results:
            model_key = eval_r["model_name"].lower()
            metadata[f"{model_key}_accuracy"] = eval_r["accuracy"]
            metadata[f"{model_key}_f1"] = eval_r["f1_score"]

        # Trading-Metriken
        for tr in trading_results:
            model_key = tr["model_name"].lower()
            metadata[f"{model_key}_win_rate"] = tr["win_rate"]
            metadata[f"{model_key}_profit_factor"] = tr["profit_factor"]
            metadata[f"{model_key}_sharpe"] = tr["sharpe_ratio"]

        # Trade-Filter aus Validation-Tuning
        for model_name, filter_info in trade_filters.items():
            model_key = model_name.lower()
            metadata[f"{model_key}_trade_min_confidence"] = filter_info["min_confidence"]
            metadata[f"{model_key}_trade_min_margin"] = filter_info["min_margin"]
            val_tr = filter_info.get("validation_trading", {})
            metadata[f"{model_key}_val_trade_win_rate"] = val_tr.get("win_rate")
            metadata[f"{model_key}_val_trade_profit_factor"] = val_tr.get("profit_factor")
            metadata[f"{model_key}_val_trade_count"] = val_tr.get("n_trades")

        meta_path = os.path.join(self.saved_models_dir, "model_metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        duration = time.time() - start_time
        logger.info(f"\n{'='*60}")
        logger.info(f"âœ… Training komplett! Dauer: {duration:.1f}s")
        logger.info(f"ðŸ’¾ Modelle gespeichert in: {self.saved_models_dir}")
        logger.info(f"{'='*60}")

        results["metadata"] = metadata
        return results

    def train_from_csv(
        self,
        csv_path: str,
        timeframe: str = "5m",
    ) -> Dict[str, Any]:
        """Convenience: Trainiert aus einer CSV-Datei."""
        logger.info(f"ðŸ“‚ Lade Daten aus: {csv_path}")
        df = pd.read_csv(csv_path)

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.set_index("timestamp", inplace=True)

        return self.train_all(df, timeframe=timeframe)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Test mit synthetischen Daten
    np.random.seed(42)
    n = 2000
    price = 2045.0
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}

    for i in range(n):
        change = np.random.randn() * 0.3
        open_p = price
        close_p = price + change
        high_p = max(open_p, close_p) + abs(np.random.randn()) * 0.2
        low_p = min(open_p, close_p) - abs(np.random.randn()) * 0.2
        vol = int(np.random.uniform(500, 2000))

        data["open"].append(open_p)
        data["high"].append(high_p)
        data["low"].append(low_p)
        data["close"].append(close_p)
        data["volume"].append(vol)
        price = close_p

    timestamps = pd.date_range("2025-01-01", periods=n, freq="5min", tz="UTC")
    df = pd.DataFrame(data, index=timestamps)

    # Simulierte Indikatoren
    df["rsi_14"] = np.random.uniform(20, 80, n)
    df["macd_line"] = np.random.randn(n) * 0.5
    df["macd_signal"] = np.random.randn(n) * 0.3
    df["macd_hist"] = df["macd_line"] - df["macd_signal"]
    df["ema_9"] = df["close"].ewm(span=9).mean()
    df["ema_21"] = df["close"].ewm(span=21).mean()
    df["ema_50"] = df["close"].ewm(span=50).mean()
    df["ema_200"] = df["close"].ewm(span=200).mean()
    df["bb_width"] = np.random.uniform(0.005, 0.02, n)
    df["adx_14"] = np.random.uniform(10, 50, n)
    df["atr_14"] = np.random.uniform(0.5, 2.0, n)
    df["stoch_k"] = np.random.uniform(10, 90, n)
    df["stoch_d"] = np.random.uniform(10, 90, n)

    trainer = ModelTrainer(
        saved_models_dir="ai_engine/saved_models",
        tp_pips=30, sl_pips=20,
        max_holding_candles=30,
        spread_pips=2.5, slippage_pips=0.5,
    )

    results = trainer.train_all(df, timeframe="5m")
    print(f"\nâœ… Training komplett! Dauer: {results['metadata']['training_duration_seconds']}s")

