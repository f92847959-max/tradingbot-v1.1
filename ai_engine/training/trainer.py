"""
Trainer -- ModelTrainer shell with pipeline delegation.

The ModelTrainer class owns all sub-components (feature engineer, label
generator, data preparation, evaluator, scaler, backtester, models) and
delegates the actual training pipeline to TrainingPipeline.
"""

import logging
import os
from typing import Any, Dict

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
from .pipeline import TrainingPipeline

logger = logging.getLogger(__name__)


class ModelTrainer:
    """
    Complete training pipeline for all models.

    12-step pipeline (delegated to TrainingPipeline):
    1. Validate historical data
    2. Compute features
    3. Generate labels (with spread costs)
    4. Remove warmup period
    5. Separate features/labels
    6. Chronological split (with purging gap)
    7. Scale features
    8. Train models (XGBoost + LightGBM)
    9. Feature selection (importance-based)
    10. ML evaluation on test set
    11. Trading evaluation & backtest
    12. Save models and metadata
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
        use_dynamic_atr: bool = True,
        tp_atr_multiplier: float = 2.0,
        sl_atr_multiplier: float = 1.5,
    ) -> None:
        """
        Initialize the ModelTrainer.

        Args:
            saved_models_dir: Path to save trained models
            tp_pips: Take-profit in pips for label generation
            sl_pips: Stop-loss in pips for label generation
            max_holding_candles: Max holding duration for label generation
            pip_size: Pip size for Gold
            spread_pips: Spread cost for labels
            slippage_pips: Slippage for labels
            use_dynamic_atr: Use ATR-based dynamic TP/SL for labels (default True)
            tp_atr_multiplier: ATR multiplier for take-profit distance
            sl_atr_multiplier: ATR multiplier for stop-loss distance
        """
        self.saved_models_dir = saved_models_dir
        self.tp_pips = tp_pips
        self.sl_pips = sl_pips
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips
        self.use_dynamic_atr = use_dynamic_atr
        self.tp_atr_multiplier = tp_atr_multiplier
        self.sl_atr_multiplier = sl_atr_multiplier

        self._feature_engineer = FeatureEngineer()
        self._label_generator = LabelGenerator(
            tp_pips=tp_pips,
            sl_pips=sl_pips,
            max_candles=max_holding_candles,
            pip_size=pip_size,
            spread_pips=spread_pips,
            slippage_pips=slippage_pips,
            use_dynamic_atr=use_dynamic_atr,
            tp_atr_multiplier=tp_atr_multiplier,
            sl_atr_multiplier=sl_atr_multiplier,
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

        # Models (XGBoost + LightGBM, CPU-only)
        self._xgboost = XGBoostModel()
        self._lightgbm = LightGBMModel()

        os.makedirs(saved_models_dir, exist_ok=True)
        logger.info(f"ModelTrainer initialized. Models -> {saved_models_dir}")

    def train_all(
        self,
        df: pd.DataFrame,
        timeframe: str = "5m",
        feature_selection: bool = True,
        min_feature_importance: float = 0.005,
        min_data_months: int = 6,
    ) -> Dict[str, Any]:
        """Train all models using walk-forward pipeline."""
        pipeline = TrainingPipeline(self)
        return pipeline.run(
            df, timeframe, feature_selection, min_feature_importance,
            min_data_months=min_data_months,
        )

    def train_from_csv(
        self,
        csv_path: str,
        timeframe: str = "5m",
        min_data_months: int = 6,
    ) -> Dict[str, Any]:
        """Convenience: Train from a CSV file."""
        logger.info(f"Loading data from: {csv_path}")
        df = pd.read_csv(csv_path)

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df.set_index("timestamp", inplace=True)

        return self.train_all(df, timeframe=timeframe, min_data_months=min_data_months)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Test with synthetic data
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

    # Simulated indicators
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
    print(f"\nTraining complete! Duration: {results['metadata']['training_duration_seconds']}s")
