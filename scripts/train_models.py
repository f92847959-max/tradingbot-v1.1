"""Train XGBoost + LightGBM models on historical Gold data.

Usage:
    python scripts/train_models.py --broker                          # Fetch from Capital.com
    python scripts/train_models.py --broker --tp-pips 15 --sl-pips 10
    python scripts/train_models.py --csv data/gold_5m.csv
    python scripts/train_models.py --synthetic 5000
"""

import argparse
import asyncio
import json
import logging
import sys
import os
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine.training.trainer import ModelTrainer
from ai_engine.training.data_coverage import (
    build_dataset_manifest,
    build_row_loss_report,
    calculate_trainable_span,
    write_dataset_manifest,
)
from ai_engine.training.data_source import (
    DataSourceError,
    DataLoadResult,
    load_auto,
    load_from_db,
    load_from_file,
)


logger = logging.getLogger(__name__)


def _require_min_candles(df: pd.DataFrame, *, min_candles: int, timeframe: str) -> None:
    """Fail before training if the selected data source returned too few candles."""
    if min_candles <= 0:
        return
    if len(df) < min_candles:
        raise ValueError(
            f"Insufficient candles for {timeframe}: received {len(df)}, "
            f"minimum {min_candles} required"
        )


def _ensure_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add base technical indicators (atr_14, rsi_14, ema_*, ...) if missing.

    The training pipeline's feature engineer expects these as input columns;
    raw OHLCV CSVs (e.g. from scripts/fetch_bulk_history.py) do not include
    them. Idempotent: skips when atr_14 is already present.
    """
    if "atr_14" in df.columns:
        return df
    from market_data.indicators import calculate_indicators

    logger.info("Computing technical indicators (atr_14, rsi_14, ema_*, ...)")
    return calculate_indicators(df)


def _source_details(source: str, timeframe: str, rows: int, **extra) -> dict:
    details = {"source": source, "timeframe": timeframe, "rows": int(rows)}
    details.update({key: value for key, value in extra.items() if value is not None})
    return details


def _load_json_file(path: str | None) -> dict | None:
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


GPU_PF_TOLERANCE = 0.02  # +/-2% aggregate PF reproducibility window (D-11)


def _aggregate_pf(results: dict) -> float:
    """Best-model aggregate profit factor from a train_all() result dict."""
    report = results.get("training_report", {}) or {}
    agg = report.get("aggregate", {}) or {}
    best = agg.get("best_model")
    if best and isinstance(agg.get(best), dict):
        return float(agg[best].get("profit_factor", 0.0) or 0.0)
    scores = [
        float(v.get("profit_factor", 0.0) or 0.0)
        for v in agg.values()
        if isinstance(v, dict)
    ]
    return max(scores) if scores else 0.0


def _run_training(
    trainer,
    df,
    *,
    args,
    dataset_manifest,
    data_csv_path,
    make_trainer,
) -> dict:
    """Run train_all with the GPU equivalence guard (Phase 18 D-11 / T-18-11).

    For a GPU run that actually used the GPU, runs a CPU control at the same
    seed and compares aggregate PF. When |delta| > 2% the GPU result is tagged
    device_accepted=False in run_manifest.json and is NOT promoted to
    production (the version dir is still written for diagnostics).

    On a CPU-only machine the GPU wrappers fall back to CPU during fit, so no
    divergence is possible and the run is accepted (device_accepted=True for an
    explicit cuda request, None for cpu).
    """
    champion_report = _load_json_file(args.champion_report)
    effective_min_months = 0 if args.allow_short_data else args.min_data_months
    requested_cuda = args.device == "cuda"

    if not requested_cuda:
        return trainer.train_all(
            df,
            timeframe=args.timeframe,
            min_data_months=effective_min_months,
            champion_report=champion_report,
            enforce_promotion_gate=champion_report is not None,
            dataset_manifest=dataset_manifest,
            seed=args.seed,
            device="cpu",
            gpu_info=None,
            device_accepted=None,
            data_csv_path=data_csv_path,
        )

    # GPU requested: run a CPU control first at the same seed (cheap relative
    # to a real training run, and the only reproducible equivalence check we
    # can make on a machine that may or may not have a GPU build).
    logger.info("GPU run requested: training CPU control at seed=%s first", args.seed)
    cpu_trainer = make_trainer("cpu")
    cpu_results = cpu_trainer.train_all(
        df,
        timeframe=args.timeframe,
        min_data_months=effective_min_months,
        champion_report=champion_report,
        enforce_promotion_gate=False,  # control run is never promoted
        dataset_manifest=dataset_manifest,
        seed=args.seed,
        device="cpu",
        gpu_info=None,
        device_accepted=None,
        data_csv_path=data_csv_path,
    )
    pf_cpu = _aggregate_pf(cpu_results)

    logger.info("Training GPU run (device=cuda)")
    gpu_results = trainer.train_all(
        df,
        timeframe=args.timeframe,
        min_data_months=effective_min_months,
        champion_report=champion_report,
        enforce_promotion_gate=False,  # acceptance decided below
        dataset_manifest=dataset_manifest,
        seed=args.seed,
        device="cuda",
        gpu_info={"requested": "cuda", "effective": trainer.device},
        device_accepted=None,
        data_csv_path=data_csv_path,
    )
    pf_gpu = _aggregate_pf(gpu_results)

    # If the GPU wrapper fell back to CPU there is nothing to diverge.
    used_gpu = trainer.device == "cuda"
    if not used_gpu:
        logger.warning(
            "GPU build unavailable; ran on CPU. device_accepted=True (CPU result)."
        )
        accepted = True
    else:
        delta = abs(pf_gpu - pf_cpu) / pf_cpu if pf_cpu else float("inf")
        accepted = delta <= GPU_PF_TOLERANCE
        if accepted:
            logger.info(
                "GPU equivalence OK: pf_cpu=%.4f pf_gpu=%.4f delta=%.4f",
                pf_cpu, pf_gpu, delta,
            )
        else:
            logger.error(
                "GPU PF regression: pf_cpu=%.4f pf_gpu=%.4f delta=%.4f > %.2f. "
                "Production pointer NOT updated; run tagged device_accepted=False.",
                pf_cpu, pf_gpu, delta, GPU_PF_TOLERANCE,
            )

    # Record acceptance into the GPU run's manifest (overwrite the sidecar).
    version_dir = gpu_results.get("version_dir")
    if version_dir:
        from ai_engine.training.run_manifest import write_run_manifest
        manifest = dict(gpu_results.get("run_manifest", {}))
        manifest["device_accepted"] = accepted
        manifest.setdefault("gpu_equivalence", {})
        manifest["gpu_equivalence"] = {
            "pf_cpu": pf_cpu, "pf_gpu": pf_gpu,
            "tolerance": GPU_PF_TOLERANCE, "accepted": accepted,
        }
        write_run_manifest(manifest, version_dir)
        gpu_results["run_manifest"] = manifest

    if accepted and champion_report is not None and used_gpu:
        # Promote the GPU version only when equivalent and a champion gate
        # approved it. (When champion_report is None the pipeline never
        # auto-promotes, matching the canonical no-champion flow.)
        decision = gpu_results.get("promotion_decision", {})
        if decision.get("approved"):
            from ai_engine.training.model_versioning import update_production_pointer
            update_production_pointer(args.output, version_dir)
            logger.info("GPU run promoted to production (equivalence passed).")

    return gpu_results


def _preflight_dataset(
    df: pd.DataFrame,
    source_details: dict,
    *,
    args,
) -> dict:
    """Run coverage preflight and optionally write a dataset manifest."""
    stage_counts = {
        "received": int(source_details.get("rows", len(df))),
        "saved": int(len(df)),
        "normalized": int(len(df)),
        "feature_ready": int(len(df)),
        "label_ready": int(len(df)),
    }
    row_loss = build_row_loss_report(stage_counts)
    manifest = build_dataset_manifest(
        source_details,
        df,
        row_loss,
        feature_set="core",
        label_set="entry",
        min_months=args.min_data_months,
    )
    if not args.allow_short_data:
        calculate_trainable_span(df, min_months=args.min_data_months)
    if args.manifest_out:
        manifest_path = write_dataset_manifest(manifest, args.manifest_out)
        logger.info("Dataset manifest written to %s", manifest_path)
    return manifest


def _normalise_loaded_result(result: DataLoadResult) -> tuple[pd.DataFrame, dict]:
    df = result.dataframe
    details = dict(result.details)
    details.setdefault("source", result.source)
    details.setdefault("timeframe", result.timeframe)
    details.setdefault("rows", len(df))
    return df, details


async def _load_configured_source(args) -> tuple[pd.DataFrame, dict]:
    if args.source == "auto":
        return _normalise_loaded_result(
            await load_auto(
                timeframe=args.timeframe,
                count=args.count,
                file_path=args.csv,
                with_indicators=False,
            )
        )
    if args.source == "db":
        return _normalise_loaded_result(
            await load_from_db(
                timeframe=args.timeframe,
                count=args.count,
                with_indicators=False,
            )
        )
    if args.source == "csv":
        if not args.csv:
            raise DataSourceError("--source csv requires --csv <path>")
        return _normalise_loaded_result(
            load_from_file(
                args.csv,
                timeframe=args.timeframe,
                with_indicators=False,
            )
        )
    if args.source == "broker":
        save_path = args.save_csv or f"data/gold_{args.timeframe}.csv"
        effective_save_csv = None if args.dry_run else save_path
        df = await fetch_broker_data(
            count=args.count,
            timeframe=args.timeframe,
            save_csv=effective_save_csv,
        )
        return df, _source_details(
            "broker",
            args.timeframe,
            len(df),
            save_csv=effective_save_csv,
        )
    if args.source == "synthetic":
        candles = args.synthetic if args.synthetic > 0 else args.count
        df = generate_synthetic_data(candles)
        return df, _source_details("synthetic", args.timeframe, len(df))
    raise DataSourceError(f"Unsupported --source value: {args.source}")


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
    parser.add_argument(
        "--source",
        choices=["auto", "db", "csv", "broker", "synthetic"],
        default=None,
        help="Training data source. Omit to keep legacy --broker/--csv/--synthetic behavior.",
    )
    parser.add_argument("--csv", type=str, help="Path to CSV with OHLCV data")
    parser.add_argument("--broker", action="store_true", help="Fetch real data from Capital.com API")
    parser.add_argument(
        "--synthetic", type=int, default=0,
        help="Generate N synthetic candles for testing",
    )
    parser.add_argument("--count", type=int, default=1000, help="Number of candles to fetch from broker")
    parser.add_argument(
        "--min-candles",
        type=int,
        default=0,
        help="Minimum candles required before training starts (0 = disabled)",
    )
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
        "--manifest-out",
        type=str,
        default=None,
        help="Optional path for dataset coverage manifest JSON.",
    )
    parser.add_argument(
        "--allow-short-data",
        action="store_true",
        default=False,
        help="Skip trainable-span preflight and pass min_data_months=0 to training.",
    )
    parser.add_argument(
        "--champion-report",
        type=str,
        default=None,
        help="Optional JSON report for promotion-gate comparison.",
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
        "--exit-aware-labels",
        action="store_true",
        default=True,
        help="Demote entry labels when deterministic exit logic would bail early (default).",
    )
    parser.add_argument(
        "--no-exit-aware-labels",
        dest="exit_aware_labels",
        action="store_false",
        help="Disable exit-aware label demotion.",
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
    parser.add_argument(
        "--device", choices=["cpu", "cuda"], default="cpu",
        help=(
            "Compute device. 'cuda' enables GPU training (XGBoost "
            "tree_method=hist + device=cuda, LightGBM device=gpu) with "
            "automatic CPU fallback when no GPU build is available. GPU runs "
            "are accepted only when aggregate PF reproduces within +/-2%% of a "
            "CPU control run at the same seed (Phase 18 D-11)."
        ),
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed recorded in run_manifest.json (default: 42).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.dry_run:
        logger.warning("DRY-RUN active: no data writes, no model serialization.")

    def _make_trainer(device: str) -> ModelTrainer:
        return ModelTrainer(
            saved_models_dir=args.output,
            tp_pips=args.tp_pips,
            sl_pips=args.sl_pips,
            max_holding_candles=args.max_holding,
            pip_size=args.pip_size,
            spread_pips=args.spread_pips,
            use_dynamic_atr=args.dynamic_atr,
            tp_atr_multiplier=args.tp_atr_mult,
            sl_atr_multiplier=args.sl_atr_mult,
            exit_aware_labels=args.exit_aware_labels,
            device=device,
        )

    trainer = _make_trainer(args.device)
    effective_min_months = 0 if args.allow_short_data else args.min_data_months
    champion_report = _load_json_file(args.champion_report)
    dataset_manifest = None

    if args.source:
        df, details = asyncio.run(_load_configured_source(args))
        df = _ensure_indicators(df)
        _require_min_candles(
            df, min_candles=args.min_candles, timeframe=args.timeframe,
        )
        dataset_manifest = _preflight_dataset(df, details, args=args)
        if args.dry_run:
            logger.info(
                "DRY-RUN: would train on %d %s candles from %s and save to %s. Skipped.",
                len(df), args.timeframe, details.get("source"), args.output,
            )
            return
        results = _run_training(
            trainer, df, args=args, dataset_manifest=dataset_manifest,
            data_csv_path=args.csv, make_trainer=_make_trainer,
        )

    elif args.broker:
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
        df = _ensure_indicators(df)
        _require_min_candles(
            df, min_candles=args.min_candles, timeframe=args.timeframe,
        )
        dataset_manifest = _preflight_dataset(
            df,
            _source_details("broker", args.timeframe, len(df), save_csv=effective_save_csv),
            args=args,
        )
        if args.dry_run:
            logger.info(
                "DRY-RUN: would train on %d real broker candles "
                "(TP=%s pips, SL=%s pips, max_holding=%s) and save to %s. Skipped.",
                len(df), args.tp_pips, args.sl_pips, args.max_holding, args.output,
            )
            return
        print(f"Training on {len(df)} real broker candles...")
        print(f"  TP={args.tp_pips} pips, SL={args.sl_pips} pips, max_holding={args.max_holding}")
        results = _run_training(
            trainer, df, args=args, dataset_manifest=dataset_manifest,
            data_csv_path=effective_save_csv, make_trainer=_make_trainer,
        )
    elif args.csv:
        print(f"Loading data from: {args.csv}")
        df = pd.read_csv(args.csv)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df.set_index("timestamp", inplace=True)
        df = _ensure_indicators(df)
        _require_min_candles(
            df, min_candles=args.min_candles, timeframe=args.timeframe,
        )
        dataset_manifest = _preflight_dataset(
            df,
            _source_details("csv", args.timeframe, len(df), file_path=args.csv),
            args=args,
        )
        if args.dry_run:
            logger.info(
                "DRY-RUN: validated CSV %s with %d candles and would save to %s. Skipped.",
                args.csv, len(df), args.output,
            )
            return
        results = _run_training(
            trainer, df, args=args, dataset_manifest=dataset_manifest,
            data_csv_path=args.csv, make_trainer=_make_trainer,
        )
    elif args.synthetic > 0:
        print(f"Generating {args.synthetic} synthetic candles...")
        df = generate_synthetic_data(args.synthetic)
        df = _ensure_indicators(df)
        _require_min_candles(
            df, min_candles=args.min_candles, timeframe=args.timeframe,
        )
        dataset_manifest = _preflight_dataset(
            df,
            _source_details("synthetic", args.timeframe, len(df)),
            args=args,
        )
        if args.dry_run:
            logger.info(
                "DRY-RUN: would train on %d synthetic candles and save to %s. Skipped.",
                args.synthetic, args.output,
            )
            return
        results = _run_training(
            trainer, df, args=args, dataset_manifest=dataset_manifest,
            data_csv_path=None, make_trainer=_make_trainer,
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
    print(f"  Exit-aware labels: {'enabled' if args.exit_aware_labels else 'disabled'}")
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

    promotion = results.get("promotion_decision", {})
    if promotion:
        print(
            "  Promotion: "
            f"{'approved' if promotion.get('approved') else 'blocked'} "
            f"({', '.join(promotion.get('reasons', [])) or promotion.get('mode', '')})"
        )

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
        diagnostic_dir = os.path.join(version_dir, "charts")
        if os.path.isdir(diagnostic_dir):
            chart_count = len([
                name for name in os.listdir(diagnostic_dir)
                if name.lower().endswith(".png")
            ])
            print(f"  Diagnostic charts: {chart_count} -> {diagnostic_dir}")

    print(f"  Version dir: {version_dir}")
    print(f"  Models saved to: {args.output}")

    # Report file path
    if version_dir:
        report_path = os.path.join(version_dir, "training_report.json")
        print(f"  Training report: {report_path}")
        print(f"  Promotion decision: {os.path.join(version_dir, 'promotion_decision.json')}")
        if promotion.get("approved"):
            print(f"  Shadow manifest: {os.path.join(version_dir, 'shadow_training_manifest.json')}")


if __name__ == "__main__":
    main()
