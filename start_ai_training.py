r"""Real-data-only parallel starter for GoldBot AI training.

Default behavior:
    - fetches real Capital.com candles (or pre-fetched CSV via --use-csv-if-present)
    - enforces a per-timeframe minimum candle count derived from --min-data-months
    - trains all selected Core-AI timeframes in parallel
    - can train Exit-AI in parallel when a real snapshot CSV is provided

Examples:
    .\.venv\Scripts\python.exe start_ai_training.py
    .\.venv\Scripts\python.exe start_ai_training.py --timeframes 5m,15m,1h
    .\.venv\Scripts\python.exe start_ai_training.py --target core
    .\.venv\Scripts\python.exe start_ai_training.py --target all --exit-csv data/exit_ai_snapshots.csv
    .\.venv\Scripts\python.exe start_ai_training.py --use-csv-if-present
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
DEFAULT_OUTPUT = "ai_engine/saved_models"
DEFAULT_TIMEFRAMES = ("5m", "15m", "1h")
DEFAULT_MIN_DATA_MONTHS = 6
ABSOLUTE_MIN_CANDLES = 1500
TRADING_MINUTES_PER_MONTH = 23 * 60 * 22
TIMEFRAME_MINUTES = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440,
}
EXIT_REQUIRED_COLUMNS = {
    "timestamp",
    "direction",
    "entry_price",
    "current_price",
    "current_stop_loss",
    "initial_stop_loss",
    "take_profit",
    "atr",
    "future_adverse_r",
    "future_favorable_r",
    "future_return_r",
}


@dataclass(frozen=True)
class TrainingJob:
    name: str
    command: list[str]


def _repo_python() -> str:
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable


def _quote_command(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)


def _has_broker_credentials() -> bool:
    return all(
        os.getenv(name, "").strip()
        for name in ("CAPITAL_EMAIL", "CAPITAL_PASSWORD", "CAPITAL_API_KEY")
    )


def _parse_timeframes(raw: str) -> list[str]:
    values = [part.strip() for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("At least one timeframe is required (--timeframes)")

    seen: set[str] = set()
    unique: list[str] = []
    for timeframe in values:
        if timeframe not in TIMEFRAME_MINUTES:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. "
                f"Supported: {', '.join(TIMEFRAME_MINUTES)}"
            )
        if timeframe in seen:
            continue
        seen.add(timeframe)
        unique.append(timeframe)
    return unique


def _safe_timeframe_name(timeframe: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in timeframe)


def _list_versions(parent: Path) -> list[Path]:
    if not parent.exists() or not parent.is_dir():
        return []
    return sorted(
        (p for p in parent.iterdir() if p.is_dir() and p.name.startswith("v")),
        key=lambda p: p.name,
    )


def _read_json(path: Path) -> dict | None:
    import json
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _print_performance_summary(args: argparse.Namespace) -> None:
    """Prints a concise summary of the latest training results compared to previous runs."""
    output_dir = ROOT / args.output
    timeframes = _parse_timeframes(args.timeframes)
    primary = args.primary_timeframe

    print("\n" + "="*70)
    print(" PERFORMANCE SUMMARY (Lernfortschritt)")
    print("="*70)

    # Core-AI Summary
    if args.target in ("core", "all"):
        print("\nCORE-AI (Best Model Results):")
        for tf in timeframes:
            tf_dir = output_dir if tf == primary else (output_dir / "timeframes" / _safe_timeframe_name(tf))
            versions = _list_versions(tf_dir)
            if not versions:
                continue

            # Read current
            cur_rep = _read_json(versions[-1] / "training_report.json")
            if not cur_rep:
                continue

            agg = cur_rep.get("aggregate", {})
            best = agg.get("best_model", "xgboost")
            m = agg.get(best) or {}
            cur_pf = float(m.get("profit_factor", 0.0) or 0.0)
            cur_wr = float(m.get("win_rate", 0.0) or 0.0)
            cur_tr = int(m.get("n_trades", 0) or 0)

            line = f"  {tf:4s}: PF {cur_pf:.3f} | WR {cur_wr*100:.1f}% | Trades: {cur_tr}"

            # Comparison with previous
            if len(versions) >= 2:
                prev_rep = _read_json(versions[-2] / "training_report.json")
                if prev_rep:
                    prev_agg = prev_rep.get("aggregate", {})
                    prev_best = prev_agg.get("best_model", "xgboost")
                    pm = prev_agg.get(prev_best) or {}
                    prev_pf = float(pm.get("profit_factor", 0.0) or 0.0)
                    if prev_pf > 0:
                        lift = ((cur_pf - prev_pf) / prev_pf) * 100.0
                        line += f" | Verbesserung: {lift:+.1f}%"
            else:
                line += " | [Initialer Run]"

            print(line)

    # Exit-AI Summary
    if args.target in ("exit", "all"):
        print("\nEXIT-AI (vs Baseline):")
        exit_dir = output_dir / "specialists" / "exit_ai"
        versions = _list_versions(exit_dir)
        if versions:
            comp = _read_json(versions[-1] / "exit_ai_comparison_report.json")
            promo = _read_json(versions[-1] / "exit_ai_promotion_artifact.json")
            if comp:
                deltas = comp.get("deltas", {})
                pf_lift = float(deltas.get("profit_factor_delta_pct", 0.0) or 0.0)
                # If pct not in deltas, calculate it manually from pf_base/pf_cand
                if pf_lift == 0:
                    c = comp.get("comparison", {})
                    base_pf = float(c.get("baseline", {}).get("profit_factor_proxy", 0.0) or 0.0)
                    cand_pf = float(c.get("exit_ai_candidate", {}).get("profit_factor_proxy", 0.0) or 0.0)
                    if base_pf > 0:
                        pf_lift = ((cand_pf - base_pf) / base_pf) * 100.0

                dd_lift = float(deltas.get("drawdown_delta", 0.0) or 0.0)
                status = promo.get("promotion_status", "rejected") if promo else "N/A"

                print(f"  Lift PF:  {pf_lift:+.1f}%")
                print(f"  Drawdown: {dd_lift:+.1f} pips delta")
                print(f"  Status:   {status.upper()}")
        else:
            print("  [No Exit-AI models found]")

    print("="*70 + "\n")

def _min_candles_for_timeframe(timeframe: str, months: int) -> int:
    minutes_total = TRADING_MINUTES_PER_MONTH * max(months, 1)
    candles = math.ceil(minutes_total / TIMEFRAME_MINUTES[timeframe])
    return max(candles, ABSOLUTE_MIN_CANDLES)


def _resolve_min_candles(args: argparse.Namespace, timeframe: str) -> int:
    if args.min_candles is not None and args.min_candles > 0:
        return args.min_candles
    return _min_candles_for_timeframe(timeframe, args.min_data_months)


def _resolve_count(args: argparse.Namespace, timeframe: str, min_candles: int) -> int:
    if args.count is not None and args.count > 0:
        if args.count < min_candles:
            print(
                f"[{timeframe}] Count raised from {args.count} to {min_candles} "
                f"to satisfy {args.min_data_months}-month minimum."
            )
        return max(args.count, min_candles)
    return min_candles


def _core_output_dir(args: argparse.Namespace, timeframe: str) -> str:
    if timeframe == args.primary_timeframe:
        return args.output
    return str(Path(args.output) / "timeframes" / _safe_timeframe_name(timeframe))


def _core_save_csv_path(args: argparse.Namespace, timeframe: str) -> str:
    return str(Path(args.save_csv_dir) / f"gold_{_safe_timeframe_name(timeframe)}.csv")


def _existing_csv_path(args: argparse.Namespace, timeframe: str) -> Path | None:
    if not args.use_csv_if_present:
        return None
    candidate = ROOT / _core_save_csv_path(args, timeframe)
    return candidate if candidate.exists() else None


def _build_core_jobs(args: argparse.Namespace) -> list[TrainingJob]:
    timeframes = _parse_timeframes(args.timeframes)
    if args.primary_timeframe not in timeframes:
        raise ValueError(
            "--primary-timeframe must be included in --timeframes "
            f"(primary={args.primary_timeframe}, timeframes={','.join(timeframes)})"
        )

    jobs: list[TrainingJob] = []
    for timeframe in timeframes:
        min_candles = _resolve_min_candles(args, timeframe)
        count = _resolve_count(args, timeframe, min_candles)
        existing_csv = _existing_csv_path(args, timeframe)

        command = [
            _repo_python(),
            "scripts/train_models.py",
            "--timeframe", timeframe,
            "--min-candles", str(min_candles),
            "--output", _core_output_dir(args, timeframe),
            "--min-data-months", str(args.min_data_months),
            "--tp-atr-mult", str(args.tp_atr_mult),
            "--sl-atr-mult", str(args.sl_atr_mult),
            "--max-holding", str(args.max_holding),
        ]

        if existing_csv is not None:
            command.extend(["--csv", str(existing_csv)])
        else:
            command.extend([
                "--broker",
                "--count", str(count),
                "--save-csv", _core_save_csv_path(args, timeframe),
            ])

        if args.no_dynamic_atr:
            command.append("--no-dynamic-atr")
        if args.train_dry_run:
            command.append("--dry-run")
        jobs.append(TrainingJob(name=f"core-{timeframe}", command=command))

    return jobs


def _validate_exit_csv(path: Path, *, min_samples: int) -> None:
    try:
        import pandas as pd

        frame = pd.read_csv(path)
    except Exception as exc:
        raise ValueError(f"Exit-AI snapshot CSV cannot be read: {path} ({exc})") from exc

    missing = sorted(EXIT_REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(
            "Exit-AI snapshot CSV is not a real exit-snapshot dataset. "
            f"Missing columns: {', '.join(missing)}"
        )

    rows = int(len(frame))
    if rows < min_samples:
        raise ValueError(
            f"Exit-AI snapshot CSV has only {rows} rows, "
            f"minimum is {min_samples}: {path}"
        )


class ExitJobSkipped(Exception):
    """Raised when the Exit-AI snapshot CSV is missing or invalid in soft mode."""


def _build_exit_job(
    args: argparse.Namespace, *, validate_csv: bool, soft_skip: bool,
) -> TrainingJob:
    exit_csv = ROOT / args.exit_csv
    if validate_csv:
        if not exit_csv.exists():
            msg = (
                f"Exit-AI real snapshot CSV missing: {exit_csv}. "
                "Lege echte Exit-Snapshots dort ab oder starte nur --target core."
            )
            if soft_skip:
                raise ExitJobSkipped(msg)
            raise FileNotFoundError(msg)
        try:
            _validate_exit_csv(exit_csv, min_samples=args.exit_min_samples)
        except ValueError as exc:
            if soft_skip:
                raise ExitJobSkipped(str(exc)) from exc
            raise

    command = [
        _repo_python(),
        "scripts/train_exit_ai.py",
        "--csv", args.exit_csv,
        "--output", args.output,
        "--purge-gap", str(args.exit_purge_gap),
        "--min-train-samples", str(args.exit_min_train_samples),
        "--min-test-samples", str(args.exit_min_test_samples),
    ]
    return TrainingJob(name="exit-ai", command=command)


def _build_jobs(args: argparse.Namespace, *, validate: bool) -> list[TrainingJob]:
    jobs: list[TrainingJob] = []
    if args.target in ("core", "all"):
        jobs.extend(_build_core_jobs(args))
    if args.target in ("exit", "all"):
        soft_skip = (args.target == "all") and not args.exit_required
        try:
            jobs.append(_build_exit_job(
                args, validate_csv=validate, soft_skip=soft_skip,
            ))
        except ExitJobSkipped as exc:
            print(
                f"WARN: Exit-AI skipped ({exc}). "
                "Run with --exit-required to make this fatal, or --target exit "
                "to train only Exit-AI."
            )
    return jobs


def _run_step(label: str, command: list[str]) -> int:
    print(f"\n[{label}] {_quote_command(command)}")
    log_dir = ROOT / "logs" / "training"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{label}.log"
    with open(log_path, "w", encoding="utf-8", buffering=1) as log_handle:
        proc = subprocess.Popen(
            command, cwd=ROOT, stdout=log_handle, stderr=subprocess.STDOUT,
        )
        try:
            return int(proc.wait())
        except KeyboardInterrupt:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            raise


def _run_refetch(args: argparse.Namespace) -> int:
    fetch_script = ROOT / "scripts" / "fetch_bulk_history.py"
    if not fetch_script.exists():
        print(f"WARN: refetch skipped, missing: {fetch_script}")
        return 0
    command = [
        _repo_python(),
        str(fetch_script),
        "--years", str(args.loop_refetch_years),
        "--base-timeframe", "1m",
        "--resample-from-base",
        "--output-dir", args.save_csv_dir,
        "--timeframes", args.timeframes,
    ]
    return _run_step("loop-refetch", command)


def _run_rebuild_exit_snapshots(args: argparse.Namespace) -> int:
    build_script = ROOT / "scripts" / "build_exit_snapshots.py"
    if not build_script.exists():
        print(f"WARN: snapshot rebuild skipped, missing: {build_script}")
        return 0
    source_csv = ROOT / args.save_csv_dir / f"gold_{_safe_timeframe_name(args.snapshot_timeframe)}.csv"
    command = [
        _repo_python(),
        str(build_script),
        "--csv", str(source_csv),
        "--output", args.exit_csv,
        "--stride", str(args.snapshot_stride),
        "--tp-atr-mult", str(args.tp_atr_mult),
        "--sl-atr-mult", str(args.sl_atr_mult),
        "--max-holding", str(args.max_holding),
    ]
    return _run_step("loop-snapshots", command)


def _run_parallel(jobs: list[TrainingJob], *, show_command_only: bool) -> int:
    print("\nTraining jobs:")
    for job in jobs:
        print(f"  [{job.name}] {_quote_command(job.command)}")

    if show_command_only:
        print("\nShow-command-only active: no training process started.")
        return 0

    log_dir = ROOT / "logs" / "training"
    log_dir.mkdir(parents=True, exist_ok=True)

    processes: list[tuple[TrainingJob, subprocess.Popen, object]] = []
    for job in jobs:
        log_path = log_dir / f"{job.name}.log"
        log_handle = open(log_path, "w", encoding="utf-8", buffering=1)
        print(f"\nStarting [{job.name}] -> {log_path}")
        proc = subprocess.Popen(
            job.command, cwd=ROOT, stdout=log_handle, stderr=subprocess.STDOUT,
        )
        processes.append((job, proc, log_handle))

    failures: list[tuple[str, int]] = []
    try:
        while processes:
            for entry in list(processes):
                job, process, log_handle = entry
                code = process.poll()
                if code is None:
                    continue
                processes.remove(entry)
                log_handle.close()
                if code == 0:
                    print(f"[{job.name}] finished OK")
                else:
                    print(f"[{job.name}] failed with exit code {code}")
                    failures.append((job.name, int(code)))
            if processes:
                time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nInterrupted. Terminating running training jobs...")
        for job, process, _h in processes:
            print(f"  terminating [{job.name}]")
            process.terminate()
        for job, process, log_handle in processes:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                print(f"  [{job.name}] did not stop, killing...")
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(f"  [{job.name}] still alive after kill - leaking handle")
            finally:
                log_handle.close()
        return 130

    if failures:
        print("\nTraining finished with failures:")
        for name, code in failures:
            print(f"  {name}: exit code {code}")
        return 1

    print("\nAll training jobs finished successfully.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start GoldBot AI training from real broker data only.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--target",
        choices=("core", "exit", "all"),
        default="all",
        help="Which existing AI families to train in parallel.",
    )
    parser.add_argument(
        "--timeframes",
        default=",".join(DEFAULT_TIMEFRAMES),
        help="Comma-separated Core-AI timeframes to train.",
    )
    parser.add_argument(
        "--primary-timeframe",
        default="5m",
        help="Core timeframe promoted to the default production model directory.",
    )
    parser.add_argument(
        "--count", type=int, default=None,
        help="Override candle count (default: auto from --min-data-months).",
    )
    parser.add_argument(
        "--min-candles", type=int, default=None,
        help="Override per-timeframe minimum (default: auto from --min-data-months).",
    )
    parser.add_argument("--save-csv-dir", default="data")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--min-data-months", type=int, default=DEFAULT_MIN_DATA_MONTHS,
        help="Minimum months of history required (default: 6, per TRAIN-07).",
    )
    parser.add_argument("--max-holding", type=int, default=15)
    parser.add_argument("--tp-atr-mult", type=float, default=2.0)
    parser.add_argument("--sl-atr-mult", type=float, default=1.5)
    parser.add_argument("--no-dynamic-atr", action="store_true")
    parser.add_argument(
        "--train-dry-run", action="store_true",
        help="Pass --dry-run into train_models.py",
    )
    parser.add_argument(
        "--show-command-only", action="store_true",
        help="Print parallel commands without executing them or validating snapshots",
    )
    parser.add_argument(
        "--use-csv-if-present", action="store_true",
        help=(
            "If a pre-fetched CSV exists at <save-csv-dir>/gold_<tf>.csv, "
            "use it instead of calling the broker (for bulk-downloaded datasets)."
        ),
    )
    parser.add_argument("--exit-csv", default="data/exit_ai_snapshots.csv")
    parser.add_argument(
        "--exit-required", action="store_true",
        help=(
            "With --target all, treat a missing/invalid Exit-AI CSV as a hard "
            "error instead of skipping the exit job (default: skip)."
        ),
    )
    parser.add_argument("--exit-min-samples", type=int, default=500)
    parser.add_argument("--exit-purge-gap", type=int, default=12)
    parser.add_argument("--exit-min-train-samples", type=int, default=120)
    parser.add_argument("--exit-min-test-samples", type=int, default=40)

    parser.add_argument(
        "--loop-iterations", type=int, default=1,
        help="How often to repeat the full training cycle (0 = forever).",
    )
    parser.add_argument(
        "--loop-interval-min", type=float, default=0.0,
        help="Sleep N minutes between loop iterations (0 = no sleep).",
    )
    parser.add_argument(
        "--loop-refetch", action="store_true",
        help="Run scripts/fetch_bulk_history.py before each iteration.",
    )
    parser.add_argument(
        "--loop-refetch-years", type=int, default=2,
        help="Years of history requested per refetch (resume-aware).",
    )
    parser.add_argument(
        "--rebuild-exit-snapshots", action="store_true",
        help="Regenerate data/exit_ai_snapshots.csv before each Exit-AI job.",
    )
    parser.add_argument(
        "--snapshot-timeframe", default="5m",
        help="Source OHLCV timeframe used for the Exit-AI snapshot generator.",
    )
    parser.add_argument(
        "--snapshot-stride", type=int, default=4,
        help="Open virtual trades every N bars in the snapshot generator.",
    )
    return parser


def _run_one_iteration(args: argparse.Namespace) -> int:
    if args.loop_refetch and not args.show_command_only:
        rc = _run_refetch(args)
        if rc != 0:
            print(f"WARN: refetch returned {rc}, continuing with existing CSVs")

    if (args.rebuild_exit_snapshots
            and args.target in ("exit", "all")
            and not args.show_command_only):
        rc = _run_rebuild_exit_snapshots(args)
        if rc != 0:
            print(f"WARN: snapshot rebuild returned {rc}, will skip/fail Exit-AI")

    try:
        jobs = _build_jobs(args, validate=not args.show_command_only)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2

    rc = _run_parallel(jobs, show_command_only=args.show_command_only)
    if rc == 0 and not args.show_command_only:
        _print_performance_summary(args)
    return rc


def main() -> int:
    args = _build_parser().parse_args()

    if not ROOT.joinpath("scripts", "train_models.py").exists():
        print("ERROR: start_ai_training.py must be run from the GoldBot repo root.")
        return 2

    if args.min_data_months < 1:
        print("ERROR: --min-data-months must be >= 1.")
        return 2

    if args.loop_iterations < 0:
        print("ERROR: --loop-iterations must be >= 0.")
        return 2

    try:
        timeframes = _parse_timeframes(args.timeframes)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    print("GoldBot AI training starter")
    print(f"Repo: {ROOT}")
    print(f"Python: {_repo_python()}")
    print("Source: Capital.com broker real candles (or pre-fetched CSV)")
    print(f"Target: {args.target}")
    print(f"Timeframes: {', '.join(timeframes)}")
    print(f"Min data months: {args.min_data_months}")
    if args.target in ("core", "all"):
        print("Per-timeframe minimum candles:")
        for tf in timeframes:
            print(f"  {tf}: {_resolve_min_candles(args, tf)}")
    print("Parallel execution: enabled")
    loop_label = "infinite" if args.loop_iterations == 0 else str(args.loop_iterations)
    print(f"Loop iterations: {loop_label}")
    if args.loop_refetch:
        print(f"  - refetch enabled ({args.loop_refetch_years} years per cycle)")
    if args.rebuild_exit_snapshots:
        print(f"  - exit-snapshot rebuild from {args.snapshot_timeframe} (stride={args.snapshot_stride})")
    if args.loop_interval_min > 0:
        print(f"  - sleep {args.loop_interval_min} min between iterations")

    if not _has_broker_credentials() and not args.use_csv_if_present:
        print(
            "Broker credentials are not visible in the current OS environment. "
            "scripts/train_models.py will still try GOLD_ENV_PATH, "
            "~/secrets/ai-trading-gold/.env, and .env."
        )

    iteration = 0
    last_rc = 0
    while True:
        iteration += 1
        target_label = "INF" if args.loop_iterations == 0 else str(args.loop_iterations)
        print(f"\n========== Loop iteration {iteration}/{target_label} ==========")
        try:
            last_rc = _run_one_iteration(args)
        except KeyboardInterrupt:
            print("\nLoop interrupted by user.")
            return 130

        if last_rc == 130:
            print("Iteration was interrupted - stopping loop.")
            return 130

        if args.loop_iterations and iteration >= args.loop_iterations:
            break

        if args.show_command_only:
            print("show-command-only active: not looping.")
            break

        if args.loop_interval_min > 0:
            print(f"\nSleeping {args.loop_interval_min} min before next iteration...")
            try:
                time.sleep(args.loop_interval_min * 60)
            except KeyboardInterrupt:
                print("\nSleep interrupted - stopping loop.")
                return 130

    return last_rc


if __name__ == "__main__":
    raise SystemExit(main())
