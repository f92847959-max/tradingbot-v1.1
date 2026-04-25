"""Run OOS backtest on a trained model version.

Usage:
    python scripts/run_backtest.py --version-dir ai_engine/saved_models/v001_... --broker
    python scripts/run_backtest.py --version-dir ai_engine/saved_models/v001_... --csv data/gold_5m.csv
    python scripts/run_backtest.py --version-dir ai_engine/saved_models/v001_... --synthetic 5000
"""

import argparse
import asyncio
import json
import logging
import os
import sys

import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine.features.feature_engineer import FeatureEngineer
from ai_engine.training.backtest_report import print_backtest_report
from ai_engine.training.backtest_runner import BacktestRunner
from ai_engine.training.label_generator import LabelGenerator
from scripts.train_models import fetch_broker_data, generate_synthetic_data

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OOS Walk-Forward Backtest")
    parser.add_argument(
        "--version-dir", required=True, type=str,
        help="Path to the trained model version directory",
    )
    parser.add_argument("--csv", type=str, help="Path to CSV with OHLCV data")
    parser.add_argument("--broker", action="store_true", help="Fetch real data from Capital.com API")
    parser.add_argument(
        "--synthetic", type=int, default=0,
        help="Generate N synthetic candles for testing",
    )
    parser.add_argument("--count", type=int, default=1000, help="Number of candles to fetch from broker")
    parser.add_argument("--timeframe", type=str, default="5m", help="Candle timeframe")
    parser.add_argument("--commission", type=float, default=0.0, help="Commission per trade in pips")
    parser.add_argument(
        "--output", type=str, default=None,
        help="Path to save JSON backtest report (default: {version_dir}/backtest_report.json)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 1. Validate version dir
    version_dir = args.version_dir
    version_json_path = os.path.join(version_dir, "version.json")
    if not os.path.exists(version_json_path):
        logger.error(f"version.json not found in {version_dir}")
        sys.exit(1)

    with open(version_json_path, "r", encoding="utf-8") as f:
        version_info = json.load(f)

    # 2. Load Data
    if args.broker:
        logger.info(f"Fetching real data from Capital.com (count={args.count}, tf={args.timeframe})...")
        df = asyncio.run(fetch_broker_data(
            count=args.count,
            timeframe=args.timeframe,
            save_csv=None,
        ))
    elif args.csv:
        logger.info(f"Loading data from: {args.csv}")
        df = pd.read_csv(args.csv, index_col=0, parse_dates=True)
    elif args.synthetic > 0:
        logger.info(f"Generating {args.synthetic} synthetic candles...")
        df = generate_synthetic_data(args.synthetic)
    else:
        logger.error("Provide --broker, --csv <path>, or --synthetic <count>")
        sys.exit(1)

    logger.info(f"Loaded {len(df)} candles.")

    # 3. Compute Features
    logger.info("Computing features...")
    fe = FeatureEngineer()
    df = fe.create_features(df, timeframe=args.timeframe)
    
    # After computing features, we need the feature names
    feature_names = fe.get_feature_names()

    # 4. Generate Labels
    label_params = version_info.get("label_params", {})
    tp_pips = label_params.get("tp_pips", 50.0)
    sl_pips = label_params.get("sl_pips", 30.0)
    spread_pips = label_params.get("spread_pips", 2.5)
    pip_size = label_params.get("pip_size", 0.01)
    max_holding = label_params.get("max_holding_candles", 15)
    use_dynamic_atr = label_params.get("use_dynamic_atr", False)
    tp_atr_mult = label_params.get("tp_atr_multiplier", 2.0)
    sl_atr_mult = label_params.get("sl_atr_multiplier", 1.5)

    logger.info("Generating true labels for backtest validation...")
    lg = LabelGenerator(
        tp_pips=tp_pips,
        sl_pips=sl_pips,
        spread_pips=spread_pips,
        pip_size=pip_size,
        max_candles=max_holding,
        use_dynamic_atr=use_dynamic_atr,
        tp_atr_multiplier=tp_atr_mult,
        sl_atr_multiplier=sl_atr_mult,
    )
    df = lg.generate_labels(df)

    # 5. Extract ATR if needed
    atr_values = None
    if use_dynamic_atr:
        if "atr_14" not in df.columns:
            logger.error("use_dynamic_atr is True but atr_14 column is missing")
            sys.exit(1)
        atr_values = df["atr_14"].values

    # 6. Remove warmup (NaN) rows
    warmup = 200
    if len(df) <= warmup:
        logger.error(f"Not enough data after warmup (len={len(df)}, warmup={warmup})")
        sys.exit(1)
    
    df = df.iloc[warmup:].copy()
    if atr_values is not None:
        atr_values = atr_values[warmup:]

    # 7. Extract X and y
    X = df[feature_names].values
    y = df["label"].values

    logger.info(f"Starting OOS backtest on {len(df)} prepared samples...")
    
    # 8. Run Backtester
    runner = BacktestRunner(
        version_dir=version_dir,
        commission_per_trade_pips=args.commission,
    )
    
    try:
        results = runner.run(
            X=X, 
            y=y, 
            feature_names=feature_names, 
            atr_values=atr_values
        )
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        sys.exit(1)

    report = results.get("report", {})
    consistency = results.get("consistency", {})

    # 9. Print & Save output
    print_backtest_report(report, consistency)

    output_path = args.output
    if not output_path:
        output_path = os.path.join(version_dir, "backtest_report.json")
    
    # Add consistency to saved report
    report["consistency"] = consistency
    
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Backtest report saved to {output_path}")


if __name__ == "__main__":
    main()
