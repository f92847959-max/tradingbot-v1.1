"""
Backtest Runner -- Standalone out-of-sample backtest orchestrator.

Loads a trained model version (model pkl + scaler pkl + version.json)
and runs walk-forward backtesting on the OOS test windows with full
cost modeling (spread + slippage + commission).
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .backtester import Backtester
from .backtest_report import check_consistency, generate_backtest_report
from .trade_filter import probs_to_trade_signals
from .walk_forward import calculate_walk_forward_windows

logger = logging.getLogger(__name__)


class BacktestRunner:
    """Standalone out-of-sample backtest orchestrator.

    Loads a trained model version (model pkl + scaler pkl + version.json)
    and runs walk-forward backtesting on the OOS test windows with full
    cost modeling (spread + slippage + commission).

    Usage:
        runner = BacktestRunner("saved_models/v001_20260310_120000")
        results = runner.run(X, y, feature_names, atr_values=atr)
    """

    def __init__(
        self,
        version_dir: str,
        commission_per_trade_pips: float = 0.0,
    ) -> None:
        """Initialize the BacktestRunner.

        Args:
            version_dir: Path to the version directory containing
                version.json, model pkls, and scaler pkl.
            commission_per_trade_pips: Configurable commission per trade
                in pips (default 0.0).
        """
        self.version_dir = version_dir
        self.commission_per_trade_pips = commission_per_trade_pips

        # Load version.json
        version_path = os.path.join(version_dir, "version.json")
        if not os.path.exists(version_path):
            raise FileNotFoundError(
                f"version.json not found in {version_dir}"
            )
        with open(version_path, "r", encoding="utf-8") as f:
            self.version_info = json.load(f)

        # Extract parameters
        self.feature_names: List[str] = self.version_info.get(
            "feature_names", []
        )
        self.label_params: Dict[str, Any] = self.version_info.get(
            "label_params", {}
        )
        self.use_dynamic_atr: bool = self.label_params.get(
            "use_dynamic_atr", False
        )
        self.tp_atr_multiplier: float = self.label_params.get(
            "tp_atr_multiplier", 2.0
        )
        self.sl_atr_multiplier: float = self.label_params.get(
            "sl_atr_multiplier", 1.5
        )
        self.tp_pips: float = self.label_params.get("tp_pips", 50.0)
        self.sl_pips: float = self.label_params.get("sl_pips", 30.0)
        self.spread_pips: float = self.label_params.get("spread_pips", 2.5)
        self.slippage_pips: float = self.label_params.get(
            "slippage_pips", 0.5
        )

        # Trade filter thresholds (XGBoost is the primary model)
        self.min_confidence: float = self.version_info.get(
            "xgboost_trade_min_confidence", 0.40
        )
        self.min_margin: float = self.version_info.get(
            "xgboost_trade_min_margin", 0.06
        )

        # Stored walk-forward window boundaries
        wf = self.version_info.get("walk_forward", {})
        self.stored_windows = wf.get("windows", [])

        # Load models and scaler
        self._load_models()

    def _load_models(self) -> None:
        """Load XGBoost model and feature scaler from version directory."""
        from ..models.xgboost_model import XGBoostModel
        from ..features.feature_scaler import FeatureScaler

        # XGBoost (primary model for OOS evaluation)
        xgb_path = os.path.join(self.version_dir, "xgboost_gold.pkl")
        if not os.path.exists(xgb_path):
            raise FileNotFoundError(
                f"xgboost_gold.pkl not found in {self.version_dir}"
            )
        self.xgb_model = XGBoostModel()
        self.xgb_model.load(xgb_path)

        # Feature scaler
        scaler_path = os.path.join(self.version_dir, "feature_scaler.pkl")
        if not os.path.exists(scaler_path):
            raise FileNotFoundError(
                f"feature_scaler.pkl not found in {self.version_dir}"
            )
        self.scaler = FeatureScaler()
        self.scaler.load(scaler_path)

    def _get_window_boundaries(
        self, n_samples: int
    ) -> List[Dict[str, int]]:
        """Get walk-forward window boundaries.

        Uses stored boundaries from version.json if available.
        Falls back to recalculating with calculate_walk_forward_windows().

        Args:
            n_samples: Total number of samples in the dataset.

        Returns:
            List of window boundary dicts with test_start and test_end.
        """
        if self.stored_windows:
            # Use stored window boundaries
            boundaries = []
            for w in self.stored_windows:
                boundaries.append({
                    "window_id": w.get("window_id", len(boundaries)),
                    "test_start": w.get("test_start", 0),
                    "test_end": w.get("test_end", 0),
                })
            return boundaries

        # Fallback: recalculate windows
        logger.warning(
            "No stored window boundaries in version.json, "
            "recalculating with calculate_walk_forward_windows()"
        )
        windows = calculate_walk_forward_windows(n_samples)
        return [
            {
                "window_id": w.window_id,
                "test_start": w.test_start,
                "test_end": w.test_end,
            }
            for w in windows
        ]

    def run(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
        atr_values: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Run out-of-sample walk-forward backtest.

        For each walk-forward test window:
        1. Slices X, y (and atr) using stored window boundaries
        2. Creates DataFrame and transforms with loaded scaler
        3. Predicts with loaded XGBoost model
        4. Applies trade filter (confidence + margin)
        5. Runs Backtester.run_simple() with fresh 10k balance
        6. Collects per-window results

        Args:
            X: Feature matrix [n_samples, n_features].
            y: True labels [n_samples] (values: -1, 0, 1).
            feature_names: List of feature column names matching X columns.
            atr_values: Optional per-candle ATR values for dynamic TP/SL.
                Required if use_dynamic_atr is True in version.json.

        Returns:
            Dict with per_window_results, report, and consistency.

        Raises:
            ValueError: If use_dynamic_atr is True but atr_values is None.
        """
        if self.use_dynamic_atr and atr_values is None:
            raise ValueError(
                "atr_values must be provided when use_dynamic_atr is True "
                "(as stored in version.json label_params)"
            )

        windows = self._get_window_boundaries(len(X))
        if not windows:
            logger.warning("No walk-forward windows found")
            return {
                "per_window_results": [],
                "report": generate_backtest_report([], self.version_info),
                "consistency": check_consistency([]),
            }

        logger.info(
            f"Running OOS backtest on {len(windows)} walk-forward windows"
        )

        per_window_results: List[Dict[str, Any]] = []

        for wb in windows:
            wid = wb["window_id"]
            test_start = wb["test_start"]
            test_end = wb["test_end"]

            # Slice test data
            X_test = X[test_start:test_end]
            y_test = y[test_start:test_end]

            if len(X_test) == 0:
                logger.warning(f"Window {wid}: empty test slice, skipping")
                continue

            # Create DataFrame and scale features
            # Use the feature names from version.json (may be a subset after
            # SHAP pruning), matching against the provided feature_names
            use_features = self.feature_names or feature_names
            df_test = pd.DataFrame(X_test, columns=feature_names)

            # Select only the features the model was trained on
            if set(use_features) != set(feature_names):
                missing = set(use_features) - set(feature_names)
                if missing:
                    logger.warning(
                        f"Window {wid}: missing features: {missing}"
                    )

            df_scaled = self.scaler.transform(df_test)

            # Get the scaled feature matrix using only the features the
            # model was trained on (may be a subset after SHAP pruning)
            X_scaled = df_scaled[use_features].values

            # Predict with XGBoost
            y_probs = self.xgb_model.predict(X_scaled)

            # Apply trade filter
            signals = probs_to_trade_signals(
                y_probs,
                min_confidence=self.min_confidence,
                min_margin=self.min_margin,
            )

            # Create fresh Backtester per window (independent, fresh 10k)
            bt = Backtester(
                initial_balance=10000.0,
                tp_pips=self.tp_pips,
                sl_pips=self.sl_pips,
                spread_pips=self.spread_pips,
                slippage_pips=self.slippage_pips,
                commission_per_trade_pips=self.commission_per_trade_pips,
            )

            # Run backtest
            if self.use_dynamic_atr and atr_values is not None:
                atr_test = atr_values[test_start:test_end]
                result = bt.run_simple(
                    predictions=signals,
                    actual_labels=y_test,
                    atr_values=atr_test,
                    tp_atr_multiplier=self.tp_atr_multiplier,
                    sl_atr_multiplier=self.sl_atr_multiplier,
                )
            else:
                result = bt.run_simple(
                    predictions=signals,
                    actual_labels=y_test,
                )

            # Annotate with window metadata
            result["window_id"] = wid
            result["test_start"] = test_start
            result["test_end"] = test_end
            result["test_samples"] = len(X_test)

            per_window_results.append(result)

            logger.info(
                f"  Window {wid}: {result['n_trades']} trades, "
                f"{result['total_pips']:+.1f} pips, "
                f"WR={result['win_rate']*100:.0f}%, "
                f"PF={result['profit_factor']:.2f}"
            )

        # Generate report and check consistency
        report = generate_backtest_report(per_window_results, self.version_info)
        consistency = check_consistency(per_window_results)

        return {
            "per_window_results": per_window_results,
            "report": report,
            "consistency": consistency,
        }
