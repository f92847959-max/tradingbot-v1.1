"""Train the isolated Exit-AI specialist and emit promotion artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine.training.exit_ai_evaluation import (  # noqa: E402
    build_exit_ai_promotion_artifact,
    evaluate_exit_ai_candidate,
)
from ai_engine.training.exit_ai_pipeline import (  # noqa: E402
    compare_exit_ai_to_baseline,
    train_exit_ai_specialist,
)


def generate_synthetic_exit_snapshots(rows: int = 360) -> pd.DataFrame:
    """Generate deterministic synthetic snapshots for Exit-AI training."""
    timestamps = pd.date_range(
        "2026-04-01T00:00:00Z",
        periods=rows,
        freq="5min",
        tz="UTC",
    )
    rng = np.random.default_rng(20260425)
    records: list[dict[str, float | str | bool]] = []

    for idx, ts in enumerate(timestamps):
        direction = "BUY" if idx % 2 == 0 else "SELL"
        base_price = 2050.0 + np.sin(idx / 18.0) * 2.5 + (idx * 0.01)
        base_risk = 0.9 + ((idx % 7) * 0.07)
        take_profit = (
            base_price + (base_risk * 3.0)
            if direction == "BUY"
            else base_price - (base_risk * 3.0)
        )
        tp1 = (
            base_price + (base_risk * 1.5)
            if direction == "BUY"
            else base_price - (base_risk * 1.5)
        )
        initial_stop = (
            base_price - base_risk if direction == "BUY" else base_price + base_risk
        )
        pattern = idx % 4
        if pattern == 0:
            profit_r = 0.25
            reversal_exit = False
            already_closed = False
            future_adverse_r = 0.45
            future_favorable_r = 0.65
        elif pattern == 1:
            profit_r = 1.20
            reversal_exit = False
            already_closed = False
            tp1 = (
                base_price + (base_risk * 1.8)
                if direction == "BUY"
                else base_price - (base_risk * 1.8)
            )
            future_adverse_r = 0.95
            future_favorable_r = 1.10
        elif pattern == 2:
            profit_r = 1.75
            reversal_exit = False
            already_closed = False
            future_adverse_r = 0.70
            future_favorable_r = 1.35
        else:
            profit_r = 0.60
            reversal_exit = True
            already_closed = False
            future_adverse_r = 1.10
            future_favorable_r = 0.35

        current_price = (
            base_price + (base_risk * profit_r)
            if direction == "BUY"
            else base_price - (base_risk * profit_r)
        )
        records.append(
            {
                "timestamp": ts.isoformat(),
                "direction": direction,
                "regime": "TRENDING" if idx % 3 else "RANGING",
                "entry_price": round(base_price, 4),
                "current_price": round(current_price, 4),
                "current_stop_loss": round(initial_stop, 4),
                "initial_stop_loss": round(initial_stop, 4),
                "take_profit": round(take_profit, 4),
                "tp1": round(tp1, 4),
                "atr": round(0.9 + ((idx % 5) * 0.1), 4),
                "hours_open": round((idx % 18) * 0.5, 4),
                "volume_ratio": round(0.8 + ((idx % 6) * 0.15), 4),
                "spread_pips": round(2.0 + ((idx % 4) * 0.2), 4),
                "support_level": round(base_price - (base_risk * 1.4), 4),
                "resistance_level": round(base_price + (base_risk * 1.4), 4),
                "reversal_exit": reversal_exit,
                "already_closed": already_closed,
                "future_adverse_r": round(future_adverse_r + rng.normal(0.0, 0.03), 4),
                "future_favorable_r": round(
                    future_favorable_r + rng.normal(0.0, 0.03),
                    4,
                ),
                "future_return_r": round(
                    future_favorable_r - (future_adverse_r * 0.5),
                    4,
                ),
            }
        )
    return pd.DataFrame.from_records(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Exit-AI specialist")
    parser.add_argument("--csv", type=str, help="Path to a CSV snapshot dataset")
    parser.add_argument(
        "--synthetic",
        type=int,
        default=360,
        help="Generate N synthetic snapshots when no CSV is provided",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="ai_engine/saved_models",
        help="Model output directory",
    )
    parser.add_argument("--purge-gap", type=int, default=12)
    parser.add_argument("--min-train-samples", type=int, default=120)
    parser.add_argument("--min-test-samples", type=int, default=40)
    args = parser.parse_args()

    if args.csv:
        frame = pd.read_csv(args.csv)
    else:
        frame = generate_synthetic_exit_snapshots(args.synthetic)

    train_result = train_exit_ai_specialist(
        frame,
        saved_models_dir=args.output,
        purge_gap=args.purge_gap,
    )
    comparison = compare_exit_ai_to_baseline(
        frame,
        purge_gap=args.purge_gap,
        min_train_samples=args.min_train_samples,
        min_test_samples=args.min_test_samples,
    )
    evaluation = evaluate_exit_ai_candidate(comparison)
    promotion_artifact = build_exit_ai_promotion_artifact(
        comparison,
        evaluation,
        version_dir=train_result["version_dir"],
    )

    comparison_path = os.path.join(
        train_result["version_dir"],
        "exit_ai_comparison_report.json",
    )
    promotion_path = os.path.join(
        train_result["version_dir"],
        "exit_ai_promotion_artifact.json",
    )
    with open(comparison_path, "w", encoding="utf-8") as handle:
        json.dump(comparison, handle, indent=2)
    with open(promotion_path, "w", encoding="utf-8") as handle:
        json.dump(promotion_artifact, handle, indent=2)

    print("Exit-AI training complete")
    print(f"  Version dir: {train_result['version_dir']}")
    print(f"  Specialist root: {train_result['specialist_root']}")
    print(f"  Training report: {train_result['report_path']}")
    print(f"  Comparison report: {comparison_path}")
    print(f"  Promotion artifact: {promotion_path}")
    print(f"  Promotion status: {promotion_artifact['promotion_status']}")


if __name__ == "__main__":
    main()
