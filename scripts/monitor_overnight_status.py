"""Live status monitor for overnight training runs.

Shows:
- Runner heartbeat/status from health JSON
- Improvement between the latest two completed runs (F1 / Profit Factor)
- BUY / HOLD / SELL signal counts for both models (when available)

Usage:
    python scripts/monitor_overnight_status.py
    python scripts/monitor_overnight_status.py --once
    python scripts/monitor_overnight_status.py --refresh-seconds 5
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from typing import Any


def _load_json(path: str) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except FileNotFoundError:
        return []
    except OSError:
        return []
    return rows


def _parse_iso(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fmt_age(raw_ts: Any) -> str:
    dt = _parse_iso(raw_ts)
    if dt is None:
        return "-"
    seconds = int((datetime.now(timezone.utc) - dt).total_seconds())
    if seconds < 0:
        seconds = 0
    mins, sec = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{sec:02d}"


def _fmt_float(value: Any, digits: int = 4) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _fmt_delta(current: Any, previous: Any, digits: int = 4) -> str:
    try:
        cur = float(current)
        prev = float(previous)
        return f"{cur - prev:+.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _fmt_int(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "-"


def _extract_model(summary: dict[str, Any], model_key: str) -> dict[str, Any]:
    signals = summary.get("signals", {}).get(model_key, {})
    return {
        "f1": summary.get(f"{model_key}_f1"),
        "pf": summary.get(f"{model_key}_profit_factor"),
        "win_rate": summary.get(f"{model_key}_win_rate"),
        "buy": signals.get("buy") if isinstance(signals, dict) else None,
        "hold": signals.get("hold") if isinstance(signals, dict) else None,
        "sell": signals.get("sell") if isinstance(signals, dict) else None,
    }


def _find_latest_metric_runs(
    runs: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    metric_runs: list[dict[str, Any]] = []
    for row in runs:
        summary = row.get("summary")
        if not isinstance(summary, dict):
            continue
        if summary.get("xgboost_f1") is None and summary.get("lightgbm_f1") is None:
            continue
        metric_runs.append(row)
    if not metric_runs:
        return None, None
    latest = metric_runs[-1]
    previous = metric_runs[-2] if len(metric_runs) >= 2 else None
    return latest, previous


def _render(health: dict[str, Any] | None, runs: list[dict[str, Any]]) -> str:
    latest_run, prev_run = _find_latest_metric_runs(runs)

    lines: list[str] = []
    lines.append("=== OVERNIGHT TRAINING STATUS ===")

    if health is None:
        lines.append("Health: Datei nicht lesbar")
    else:
        lines.append(
            "Runner: "
            f"status={health.get('status', '-')}"
            f" | run={health.get('run', '-')}"
            f" | errors={health.get('consecutive_errors', '-')}/{health.get('max_consecutive_errors', '-')}"
            f" | promoted={health.get('promoted_runs', '-')}"
        )
        lines.append(
            "Source: "
            f"{health.get('source', '-')}"
            f" {health.get('symbol', '-') if health.get('source') == 'yfinance' else ''}"
            f" | tf={health.get('timeframe', '-')}"
            f" | candles={health.get('requested_count', '-')}"
        )
        if health.get("source") == "yfinance":
            anchor_mode = health.get("yfinance_anchor_mode", "-")
            if anchor_mode == "history_jump":
                lines.append(
                    "Anchor: "
                    f"mode=history_jump"
                    f" | active={health.get('active_anchor_date_utc', '-')}"
                    f" | range={health.get('yfinance_history_jump_start_utc', '-')}"
                    f" -> {health.get('yfinance_history_jump_end_utc', '-')}"
                )
            else:
                lines.append(
                    "Anchor: "
                    f"mode={anchor_mode}"
                    f" | active={health.get('active_anchor_date_utc', '-')}"
                    f" | cycle={health.get('yfinance_anchor_dates', [])}"
                )
        lines.append(
            "Heartbeat: "
            f"last_update={health.get('last_update_utc', '-')}"
            f" (age { _fmt_age(health.get('last_update_utc')) })"
            f" | next_run={health.get('next_run_utc', '-')}"
        )
        gate = health.get("last_quality_gate")
        if isinstance(gate, dict):
            lines.append(
                "Gate: "
                f"accepted={gate.get('accepted', '-')}"
                f" | reason={gate.get('reason', '-')}"
            )

    lines.append("")
    lines.append("=== AI PERFORMANCE (latest vs previous run) ===")

    if latest_run is None:
        lines.append("Noch keine abgeschlossenen Runs mit Metriken im Run-Log.")
        return "\n".join(lines)

    latest_summary = latest_run.get("summary", {})
    prev_summary = prev_run.get("summary", {}) if isinstance(prev_run, dict) else {}

    xgb_latest = _extract_model(latest_summary, "xgboost")
    lgb_latest = _extract_model(latest_summary, "lightgbm")
    xgb_prev = _extract_model(prev_summary, "xgboost") if prev_summary else {}
    lgb_prev = _extract_model(prev_summary, "lightgbm") if prev_summary else {}

    lines.append(
        f"Latest run={latest_run.get('run', '-')}"
        f" | status={latest_run.get('status', '-')}"
        f" | ts={latest_run.get('timestamp_utc', '-')}"
        f" | candles={latest_run.get('candles_received', '-')}"
        f" | anchor={latest_run.get('yfinance_anchor_date_utc', '-')}"
    )
    lines.append("Model      F1       dF1      PF       dPF      BUY   HOLD  SELL")
    lines.append(
        f"XGBoost  "
        f"{_fmt_float(xgb_latest.get('f1')):>7}  "
        f"{_fmt_delta(xgb_latest.get('f1'), xgb_prev.get('f1')):>7}  "
        f"{_fmt_float(xgb_latest.get('pf')):>7}  "
        f"{_fmt_delta(xgb_latest.get('pf'), xgb_prev.get('pf')):>7}  "
        f"{_fmt_int(xgb_latest.get('buy')):>5}  "
        f"{_fmt_int(xgb_latest.get('hold')):>5}  "
        f"{_fmt_int(xgb_latest.get('sell')):>5}"
    )
    lines.append(
        f"LightGBM "
        f"{_fmt_float(lgb_latest.get('f1')):>7}  "
        f"{_fmt_delta(lgb_latest.get('f1'), lgb_prev.get('f1')):>7}  "
        f"{_fmt_float(lgb_latest.get('pf')):>7}  "
        f"{_fmt_delta(lgb_latest.get('pf'), lgb_prev.get('pf')):>7}  "
        f"{_fmt_int(lgb_latest.get('buy')):>5}  "
        f"{_fmt_int(lgb_latest.get('hold')):>5}  "
        f"{_fmt_int(lgb_latest.get('sell')):>5}"
    )

    if xgb_latest.get("buy") is None or lgb_latest.get("buy") is None:
        lines.append("")
        lines.append(
            "Hinweis: BUY/HOLD/SELL pro Modell sind erst sichtbar, "
            "wenn der Runner mit der neuen Logging-Version gestartet wurde."
        )

    label_stats = latest_summary.get("label_stats")
    if isinstance(label_stats, dict):
        lines.append(
            "Labels (Datensatz): "
            f"BUY={label_stats.get('buy', '-')}, "
            f"HOLD={label_stats.get('hold', '-')}, "
            f"SELL={label_stats.get('sell', '-')}"
        )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Live monitor for overnight training.")
    parser.add_argument(
        "--health-file",
        default="logs/overnight_training_health_gc.json",
        help="Path to health JSON file.",
    )
    parser.add_argument(
        "--run-log",
        default="logs/overnight_training_runs_gc.jsonl",
        help="Path to run-log JSONL file.",
    )
    parser.add_argument(
        "--refresh-seconds",
        type=float,
        default=10.0,
        help="Refresh interval in seconds.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print one snapshot and exit.",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not clear terminal between refreshes.",
    )
    args = parser.parse_args()

    refresh = max(0.5, float(args.refresh_seconds))

    while True:
        health = _load_json(args.health_file)
        runs = _read_jsonl(args.run_log)
        output = _render(health, runs)

        if not args.no_clear:
            os.system("cls" if os.name == "nt" else "clear")
        print(output, flush=True)

        if args.once:
            return 0

        time.sleep(refresh)


if __name__ == "__main__":
    raise SystemExit(main())
