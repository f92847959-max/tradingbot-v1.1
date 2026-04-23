"""Integration tests for calibration persistence in the training pipeline."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from ai_engine.calibration.calibrator import fit_calibrator
from ai_engine.calibration.threshold_tuner import tune_thresholds
from ai_engine.features.feature_scaler import FeatureScaler
from ai_engine.training.pipeline import TrainingPipeline


class _DummyFeatureEngineer:
    def create_features(self, df: pd.DataFrame, timeframe: str = "5m") -> pd.DataFrame:
        out = df.copy()
        out["feat_a"] = np.linspace(0.0, 1.0, len(out))
        return out

    def get_feature_names(self) -> list[str]:
        return ["feat_a"]


class _DummyLabelGenerator:
    max_candles = 10

    def generate_labels(self, df: pd.DataFrame) -> np.ndarray:
        pattern = np.array([-1, 0, 1], dtype=np.int64)
        return pattern[np.arange(len(df)) % len(pattern)]

    def get_label_stats(self, labels) -> dict[str, int]:
        values = np.asarray(labels, dtype=np.int64)
        return {
            "sell": int(np.sum(values == -1)),
            "hold": int(np.sum(values == 0)),
            "buy": int(np.sum(values == 1)),
        }

    def get_params(self) -> dict[str, float]:
        return {"tp_pips": 50.0, "sl_pips": 30.0}


class _DummyDataPreparation:
    def validate_minimum_duration(self, df: pd.DataFrame, min_months: int) -> None:
        return None

    def remove_warmup_period(self, df: pd.DataFrame, warmup_candles: int) -> pd.DataFrame:
        return df.iloc[min(warmup_candles, len(df) // 4):].copy()

    def prepare_features_labels(
        self,
        df: pd.DataFrame,
        feature_names: list[str],
        label_col: str,
    ) -> tuple[np.ndarray, np.ndarray]:
        return (
            df[feature_names].to_numpy(dtype=np.float64),
            df[label_col].to_numpy(dtype=np.int64),
        )


class _DummyModel:
    is_trained = False

    def save(self, path: str) -> None:
        raise AssertionError("Model saving should be skipped in this test")


class _FakeValidator:
    def __init__(self, *args, **kwargs) -> None:
        return None

    def calculate_windows(self, n_samples: int):
        return ["w0"]

    def run_all_windows(self, X, y, feature_names, trainer):
        probs = np.array(
            [
                [0.82, 0.10, 0.08],
                [0.08, 0.80, 0.12],
                [0.10, 0.18, 0.72],
                [0.76, 0.14, 0.10],
                [0.10, 0.22, 0.68],
                [0.16, 0.70, 0.14],
            ],
            dtype=np.float64,
        )
        labels = np.array([-1, 0, 1, -1, 1, 0], dtype=np.int64)
        calibrator = fit_calibrator(probs, labels, model_name="xgboost", min_samples=4)
        threshold_artifact = tune_thresholds(
            y_true=labels,
            y_probs=probs,
            model_name="xgboost",
            min_support=2,
        )

        scaler = FeatureScaler()
        scaler.fit(pd.DataFrame({"feat_a": np.linspace(0.0, 1.0, len(labels))}), ["feat_a"])

        window_result = {
            "window_id": 0,
            "train_samples": 32,
            "test_samples": 12,
            "test_start": 32,
            "test_end": 44,
            "xgboost_eval": {
                "model_name": "XGBoost_W0",
                "accuracy": 0.55,
                "f1_score": 0.50,
            },
            "xgboost_trading": {
                "win_rate": 0.6,
                "profit_factor": 1.4,
                "expectancy": 1.2,
                "n_trades": 10,
                "wins": 6,
                "losses": 4,
                "tp_pips": 50.0,
                "sl_pips": 30.0,
                "spread_pips": 2.5,
            },
            "trade_filters": {
                "XGBoost": {
                    "min_confidence": 0.52,
                    "min_margin": 0.06,
                    "validation_trading": {"win_rate": 0.58, "profit_factor": 1.3, "n_trades": 9},
                }
            },
            "selected_features": ["feat_a"],
            "scaler": scaler,
            "eval_results": [
                {"model_name": "XGBoost_W0", "accuracy": 0.55, "f1_score": 0.50}
            ],
            "shap_importance": {},
            "calibrators": {"xgboost": calibrator},
            "calibration_artifacts": {
                "schema_version": 1,
                "class_labels": ["SELL", "HOLD", "BUY"],
                "models": {
                    "xgboost": {
                        "model_name": "xgboost",
                        "method": "isotonic",
                        "validation_metrics": {"after": {"log_loss": 0.7}},
                        "test_metrics": {"log_loss": 0.72},
                    }
                },
            },
            "threshold_artifacts": {
                "schema_version": 1,
                "class_labels": ["SELL", "HOLD", "BUY"],
                "models": {"xgboost": threshold_artifact},
            },
        }

        return {
            "windows": [window_result],
            "n_windows": 1,
            "final_scaler": scaler,
            "final_trade_filters": window_result["trade_filters"],
            "final_feature_names": ["feat_a"],
            "final_eval_results": window_result["eval_results"],
            "final_shap_importance": {},
            "final_calibrators": {"xgboost": calibrator},
            "final_calibration_artifacts": window_result["calibration_artifacts"],
            "final_threshold_artifacts": window_result["threshold_artifacts"],
        }


class _DummyTrainer:
    def __init__(self, saved_models_dir: str) -> None:
        self.saved_models_dir = saved_models_dir
        self.tp_pips = 50.0
        self.sl_pips = 30.0
        self.spread_pips = 2.5
        self.use_dynamic_atr = False
        self.tp_atr_multiplier = 2.0
        self.sl_atr_multiplier = 1.5
        self._feature_engineer = _DummyFeatureEngineer()
        self._label_generator = _DummyLabelGenerator()
        self._data_prep = _DummyDataPreparation()
        self._scaler = FeatureScaler()
        self._xgboost = _DummyModel()
        self._lightgbm = _DummyModel()


def _sample_frame(n_rows: int = 260) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n_rows, freq="5min", tz="UTC")
    close = np.linspace(2000.0, 2050.0, n_rows)
    return pd.DataFrame(
        {
            "open": close - 0.3,
            "high": close + 0.8,
            "low": close - 0.8,
            "close": close,
            "volume": np.full(n_rows, 1000),
        },
        index=idx,
    )


def test_training_pipeline_writes_calibration_and_threshold_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("ai_engine.training.pipeline.WalkForwardValidator", _FakeValidator)

    trainer = _DummyTrainer(str(tmp_path))
    pipeline = TrainingPipeline(trainer)
    results = pipeline.run(_sample_frame(), min_data_months=0)

    version_dir = results["version_dir"]
    assert os.path.exists(os.path.join(version_dir, "calibration.json"))
    assert os.path.exists(os.path.join(version_dir, "thresholds.json"))
    assert os.path.exists(os.path.join(version_dir, "xgboost_calibrator.pkl"))


def test_version_metadata_references_calibration_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("ai_engine.training.pipeline.WalkForwardValidator", _FakeValidator)

    trainer = _DummyTrainer(str(tmp_path))
    pipeline = TrainingPipeline(trainer)
    results = pipeline.run(_sample_frame(), min_data_months=0)

    metadata = results["metadata"]
    assert metadata["calibration_artifact"] == "calibration.json"
    assert metadata["threshold_artifact"] == "thresholds.json"
    assert "xgboost" in metadata["calibration"]["models"]
    assert "xgboost" in metadata["decision_thresholds"]["models"]
