"""Train XGBoost + LightGBM models on historical Gold data.

Usage:
    python scripts/train_models.py --broker                          # Fetch from Capital.com
    python scripts/train_models.py --broker --tp-pips 15 --sl-pips 10
    python scripts/train_models.py --csv data/gold_5m.csv
    python scripts/train_models.py --synthetic 5000
"""

import argparse
import asyncio
import logging
import sys
import os

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine.training.trainer import ModelTrainer


logger = logging.getLogger(__name__)


def _warn_if_credentials_in_onedrive() -> None:
    """Warn when broker credentials are loaded from a OneDrive-synced .env file.

    OneDrive uploads files to MS cloud storage, so .env files containing
    CAPITAL_* secrets there should be migrated to a secure location
    (Windows env vars, secret manager, ~/secrets/...).
    """
    paths_to_check = (os.getcwd(), str(__file__))
    if any("OneDrive" in p for p in paths_to_check):
        logger.warning(
            "WARNING: .env credentials in OneDrive path -- "
            "consider moving to secure env vars"
        )


def generate_synthetic_data(n_candles: int = 5000) -> pd.DataFrame:
    """Generate realistic synthetic Gold price data for testing."""
    np.random.seed(42)
    price = 2045.0
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}

    for _ in range(n_candles):
        change = np.random.randn() * 0.3
        open_p = price
        close_p = price + change
        high_p = max(open_p, close_p) + abs(np.random.randn()) * 0.2
        low_p = min(open_p, close_p) - abs(np.random.randn()) * 0.2
        vol = int(np.random.uniform(500, 2000))

        data["open"].append(round(open_p, 2))
        data["high"].append(round(high_p, 2))
        data["low"].append(round(low_p, 2))
        data["close"].append(round(close_p, 2))
        data["volume"].append(vol)
        price = close_p

    timestamps = pd.date_range("2025-01-01", periods=n_candles, freq="5min", tz="UTC")
    return pd.DataFrame(data, index=timestamps)


async def fetch_broker_data(
    count: int = 1000,
    timeframe: str = "5m",
    save_csv: str | None = None,
) -> pd.DataFrame:
    """Fetch real candle data from Capital.com broker API."""
    from market_data.broker_client import CapitalComClient

    # load_dotenv searches parent dirs by default and can crash on UTF-16 .env
    # files (e.g. legacy C:\Users\<user>\.env). Don't let an unrelated .env
    # block training -- we can still read from the real OS env.
    from pathlib import Path
    env_candidates = [
        os.environ.get("GOLD_ENV_PATH"),
        str(Path.home() / "secrets" / "ai-trading-gold" / ".env"),
        ".env",
    ]
    for candidate in env_candidates:
        if not candidate:
            continue
        try:
            if os.path.exists(candidate):
                load_dotenv(candidate, override=False)
                logger.info("Loaded env from %s", candidate)
        except UnicodeDecodeError as exc:
            logger.warning(
                "Skipping %s due to encoding error: %s", candidate, exc,
            )

    email = os.getenv("CAPITAL_EMAIL", "").strip()
    password = os.getenv("CAPITAL_PASSWORD", "").strip()
    api_key = os.getenv("CAPITAL_API_KEY", "").strip()
    demo = os.getenv("CAPITAL_DEMO", "true").strip().lower() in ("1", "true", "yes")

    if email or password or api_key:
        _warn_if_credentials_in_onedrive()

    if not email or not password or not api_key:
        print("ERROR: Broker credentials missing!")
        print("Set CAPITAL_EMAIL, CAPITAL_PASSWORD, CAPITAL_API_KEY in .env")
        sys.exit(1)

    client = CapitalComClient(
        email=email,
        password=password,
        api_key=api_key,
        demo=demo,
    )

    try:
        await client.authenticate()
        mode = "DEMO" if demo else "LIVE"
        print(f"Authenticated with Capital.com ({mode})")

        print(f"Fetching {count} {timeframe} candles...")
        if count > 1000 and hasattr(client, "get_candles_paginated"):
            candles = await client.get_candles_paginated(
                timeframe=timeframe, total_count=count,
            )
        else:
            candles = await client.get_candles(timeframe=timeframe, count=count)
        print(f"Received {len(candles)} candles")

        if not candles:
            print("ERROR: No candles returned from broker!")
            sys.exit(1)

        # Convert to DataFrame
        rows = [
            {
                "timestamp": c.timestamp,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume),
            }
            for c in candles
        ]
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
        df = df.set_index("timestamp")

        # Save CSV for reproducibility
        if save_csv:
            os.makedirs(os.path.dirname(save_csv) if os.path.dirname(save_csv) else ".", exist_ok=True)
            df.to_csv(save_csv)
            print(f"Saved {len(df)} candles to {save_csv}")

        return df
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Gold trading models")
    parser.add_argument("--csv", type=str, help="Path to CSV with OHLCV data")
    parser.add_argument("--broker", action="store_true", help="Fetch real data from Capital.com API")
    parser.add_argument(
        "--synthetic", type=int, default=0,
        help="Generate N synthetic candles for testing",
    )
    parser.add_argument("--count", type=int, default=1000, help="Number of candles to fetch from broker")
    parser.add_argument("--timeframe", type=str, default="5m", help="Candle timeframe")
    parser.add_argument(
        "--output", type=str, default="ai_engine/saved_models",
        help="Directory to save trained models",
    )
    parser.add_argument("--tp-pips", type=float, default=1500.0, help="Take-Profit in pips (default: 1500 = $15 at pip_size=0.01)")
    parser.add_argument("--sl-pips", type=float, default=800.0, help="Stop-Loss in pips (default: 800 = $8 at pip_size=0.01)")
    parser.add_argument("--spread-pips", type=float, default=2.5, help="Spread in pips")
    parser.add_argument("--max-holding", type=int, default=15, help="Max holding candles (default: 15)")
    parser.add_argument("--pip-size", type=float, default=0.01, help="Pip size for Gold (default: 0.01)")
    parser.add_argument("--save-csv", type=str, default=None, help="Save fetched broker data to CSV")
    parser.add_argument(
        "--min-data-months", type=int, default=6,
        help="Minimum months of data required for training (default: 6)",
    )
    parser.add_argument(
        "--dynamic-atr", action="store_true", default=True,
        help="Use ATR-based dynamic TP/SL for label generation (default: True)",
    )
    parser.add_argument(
        "--no-dynamic-atr", dest="dynamic_atr", action="store_false",
        help="Use fixed pip TP/SL (legacy mode)",
    )
    parser.add_argument(
        "--tp-atr-mult", type=float, default=2.0,
        help="ATR multiplier for take-profit (default: 2.0)",
    )
    parser.add_argument(
        "--sl-atr-mult", type=float, default=1.5,
        help="ATR multiplier for stop-loss (default: 1.5)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Log planned actions and skip data writes / model serialization.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.dry_run:
        logger.warning("DRY-RUN active: no data writes, no model serialization.")

    trainer = ModelTrainer(
        saved_models_dir=args.output,
        tp_pips=args.tp_pips,
        sl_pips=args.sl_pips,
        max_holding_candles=args.max_holding,
        pip_size=args.pip_size,
        spread_pips=args.spread_pips,
        use_dynamic_atr=args.dynamic_atr,
        tp_atr_multiplier=args.tp_atr_mult,
        sl_atr_multiplier=args.sl_atr_mult,
    )

    if args.broker:
        save_path = args.save_csv or f"data/gold_{args.timeframe}.csv"
        print(f"Fetching real data from Capital.com (count={args.count}, tf={args.timeframe})...")
        # Dry-run: do not persist fetched candles to CSV.
        effective_save_csv = None if args.dry_run else save_path
        if args.dry_run:
            logger.info("DRY-RUN: would save fetched candles to %s (skipped).", save_path)
        df = asyncio.run(fetch_broker_data(
            count=args.count,
            timeframe=args.timeframe,
            save_csv=effective_save_csv,
        ))
        if args.dry_run:
            logger.info(
                "DRY-RUN: would train on %d real broker candles "
                "(TP=%s pips, SL=%s pips, max_holding=%s) and save to %s. Skipped.",
                len(df), args.tp_pips, args.sl_pips, args.max_holding, args.output,
            )
            return
        print(f"Training on {len(df)} real broker candles...")
        print(f"  TP={args.tp_pips} pips, SL={args.sl_pips} pips, max_holding={args.max_holding}")
        results = trainer.train_all(
            df, timeframe=args.timeframe, min_data_months=args.min_data_months,
        )
    elif args.csv:
        print(f"Loading data from: {args.csv}")
        if args.dry_run:
            logger.info(
                "DRY-RUN: would train from CSV %s and save to %s. Skipped.",
                args.csv, args.output,
            )
            return
        results = trainer.train_from_csv(
            args.csv, timeframe=args.timeframe,
            min_data_months=args.min_data_months,
        )
    elif args.synthetic > 0:
        print(f"Generating {args.synthetic} synthetic candles...")
        df = generate_synthetic_data(args.synthetic)
        if args.dry_run:
            logger.info(
                "DRY-RUN: would train on %d synthetic candles and save to %s. Skipped.",
                args.synthetic, args.output,
            )
            return
        results = trainer.train_all(
            df, timeframe=args.timeframe, min_data_months=args.min_data_months,
        )
    else:
        print("Provide --broker, --csv <path>, or --synthetic <count>")
        print("Example: python scripts/train_models.py --broker")
        print("Example: python scripts/train_models.py --csv data/gold_5m.csv")
        sys.exit(1)

    meta = results.get("metadata", {})
    report = results.get("training_report", {})
    version_dir = results.get("version_dir", "")

    print("\nTraining complete!")
    print(f"  Duration: {meta.get('training_duration_seconds', 0):.1f}s")
    print(f"  Features: {meta.get('n_features_selected', 0)}")
    print(f"  Samples:  {meta.get('n_samples_total', 0)}")
    print(f"  Dynamic ATR: {'enabled' if args.dynamic_atr else 'disabled'}")
    if args.dynamic_atr:
        print(f"  ATR multipliers: TP={args.tp_atr_mult}x, SL={args.sl_atr_mult}x")

    # Walk-forward summary
    n_windows = results.get("n_windows", 0)
    print(f"  Walk-forward windows: {n_windows}")

    # Aggregate metrics per model from training report
    agg = report.get("aggregate", {})
    for model_key in ["xgboost", "lightgbm"]:
        m = agg.get(model_key, {})
        if not m:
            continue
        label = model_key.upper()
        print(
            f"  {label}: "
            f"WR={m.get('win_rate', 0):.1%} "
            f"PF={m.get('profit_factor', 0):.2f} "
            f"Exp={m.get('expectancy', 0):+.1f} "
            f"Sharpe={m.get('sharpe', 0):.2f} "
            f"({m.get('n_trades', 0)} trades)"
        )

    best = agg.get("best_model")
    if best:
        best_pf = agg.get(best, {}).get("profit_factor", 0)
        print(f"  Best model: {best.upper()} (PF={best_pf:.2f})")

    # Feature pruning summary
    pruning = results.get("feature_pruning", {})
    if pruning:
        print(
            f"  Features: {pruning.get('original_count', '?')} -> "
            f"{pruning.get('kept_count', '?')} "
            f"(pruned {pruning.get('pruned_count', 0)}, "
            f"{'accepted' if pruning.get('pruning_accepted') else 'rejected'})"
        )

    # Feature importance chart
    if version_dir:
        chart_file = os.path.join(version_dir, "feature_importance.png")
        if os.path.exists(chart_file):
            print(f"  Feature importance chart: {chart_file}")

    print(f"  Version dir: {version_dir}")
    print(f"  Models saved to: {args.output}")

    # Report file path
    if version_dir:
        report_path = os.path.join(version_dir, "training_report.json")
        print(f"  Training report: {report_path}")


if __name__ == "__main__":
    main()
