"""Overnight training runner with real market data.

Runs repeated training cycles for a minimum duration (default: 8h):
1. Fetch real candles from Capital.com or Yahoo Finance
2. Train XGBoost + LightGBM models
3. Save models and append run result to a JSONL log

Example:
    python scripts/train_real_overnight.py --hours 8 --interval-minutes 15 --count 1200
    python scripts/train_real_overnight.py --source yfinance --symbol XAUUSD=X --hours 8
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

# Add project root to path (same pattern as train_models.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine.training.trainer import ModelTrainer
from market_data.broker_client import CapitalComClient, CandleData


logger = logging.getLogger("overnight_training")

MODEL_ARTIFACT_FILES = (
    "xgboost_gold.pkl",
    "lightgbm_gold.pkl",
    "feature_scaler.pkl",
    "model_metadata.json",
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _looks_placeholder(value: str) -> bool:
    v = value.strip().lower()
    if not v:
        return True
    markers = ("example.com", "placeholder", "changeme", "your-")
    return any(m in v for m in markers)


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


@dataclass
class BrokerCreds:
    email: str
    password: str
    api_key: str
    demo: bool


def _load_broker_creds() -> BrokerCreds:
    email = os.getenv("CAPITAL_EMAIL", "").strip()
    password = os.getenv("CAPITAL_PASSWORD", "").strip()
    api_key = os.getenv("CAPITAL_API_KEY", "").strip()
    demo = _env_bool("CAPITAL_DEMO", True)

    if email or password or api_key:
        _warn_if_credentials_in_onedrive()

    bad_fields: list[str] = []
    if _looks_placeholder(email):
        bad_fields.append("CAPITAL_EMAIL")
    if _looks_placeholder(password):
        bad_fields.append("CAPITAL_PASSWORD")
    if _looks_placeholder(api_key):
        bad_fields.append("CAPITAL_API_KEY")

    if bad_fields:
        raise RuntimeError(
            "Missing/placeholder broker credentials: "
            + ", ".join(bad_fields)
            + ". Set real values in environment or .env."
        )

    return BrokerCreds(email=email, password=password, api_key=api_key, demo=demo)


def _candles_to_df(candles: list[CandleData]) -> pd.DataFrame:
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
    return df


async def _fetch_candles_with_fallback(
    client: CapitalComClient,
    timeframe: str,
    requested_count: int,
    allow_count_fallback: bool,
) -> list[CandleData]:
    """Try requested count first, then conservative fallbacks."""
    tried: list[int] = []
    candidates = [requested_count]
    if allow_count_fallback:
        if requested_count > 1500:
            candidates.append(1500)
        if requested_count > 1000:
            candidates.append(1000)
        if requested_count > 500:
            candidates.append(500)

    last_error: Exception | None = None
    for count in candidates:
        if count in tried:
            continue
        tried.append(count)
        try:
            logger.info("Fetching %s candles (count=%d)...", timeframe, count)
            candles = await client.get_candles(timeframe=timeframe, count=count)
            if candles:
                return candles
        except (OSError, RuntimeError, ValueError, asyncio.TimeoutError) as exc:
            # Network / broker / parsing errors are recoverable: try next count.
            last_error = exc
            logger.exception("Fetch failed for count=%d", count)
        except Exception as exc:  # noqa: BLE001
            # Last-resort safety net so a single bad count never aborts the loop.
            last_error = exc
            logger.exception("Unexpected error during fetch for count=%d", count)

    if last_error is not None:
        raise last_error
    raise RuntimeError("No candles returned from broker.")


def _map_timeframe_to_yf_interval(timeframe: str) -> str:
    mapping = {
        "1m": "1m",
        "2m": "2m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "60m": "60m",
        "1h": "60m",
        "90m": "90m",
        "1d": "1d",
    }
    if timeframe not in mapping:
        raise ValueError(f"Unsupported timeframe for yfinance: {timeframe}")
    return mapping[timeframe]


def _period_for_count(timeframe: str, count: int) -> str:
    minutes_map = {
        "1m": 1,
        "2m": 2,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "60m": 60,
        "1h": 60,
        "90m": 90,
        "1d": 60 * 24,
    }
    tf_minutes = minutes_map.get(timeframe)
    if tf_minutes is None:
        return "60d"
    days = max(1, int((count * tf_minutes) / (60 * 24)) + 2)
    if days <= 7:
        return "7d"
    if days <= 30:
        return "1mo"
    if days <= 60:
        return "60d"
    if days <= 180:
        return "6mo"
    return "1y"


def _window_days_for_count(timeframe: str, count: int) -> int:
    minutes_map = {
        "1m": 1,
        "2m": 2,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "60m": 60,
        "1h": 60,
        "90m": 90,
        "1d": 60 * 24,
    }
    tf_minutes = minutes_map.get(timeframe)
    if tf_minutes is None:
        return 60
    raw_days = (count * tf_minutes) / (60 * 24)

    # Yahoo daily/intraday windows are calendar-based, while trading candles are not
    # available 24/7. Add a safety factor so anchored pulls reach requested_count.
    if timeframe == "1d":
        factor = 1.75
    elif tf_minutes >= 60:
        factor = 1.35
    else:
        factor = 1.15

    return max(1, int(raw_days * factor) + 4)


def _parse_anchor_date_token(token: str) -> datetime:
    raw = token.strip()
    if not raw:
        raise ValueError("Empty anchor date token.")

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            f"Invalid anchor date '{raw}'. Use YYYY-MM-DD or DD.MM.YYYY."
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)


def _parse_anchor_dates(raw: str) -> list[datetime]:
    if not isinstance(raw, str) or not raw.strip():
        return []
    anchors: list[datetime] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        anchors.append(_parse_anchor_date_token(part))
    return anchors


def _normalize_utc_date(dt: datetime) -> datetime:
    d = dt.astimezone(timezone.utc)
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _parse_optional_anchor_date(raw: str, *, arg_name: str) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return _parse_anchor_date_token(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid value for {arg_name}: {raw!r}") from exc


def _yfinance_intraday_lookback_days(interval: str) -> int | None:
    limits = {
        "1m": 7,
        "2m": 60,
        "5m": 60,
        "15m": 60,
        "30m": 60,
        "60m": 60,
        "90m": 60,
    }
    return limits.get(interval)


def _infer_yfinance_first_available_date_utc(symbol: str) -> datetime | None:
    try:
        import yfinance as yf  # Local optional dependency
    except ImportError:
        return None

    try:
        hist = yf.Ticker(symbol).history(
            period="max",
            interval="1d",
            auto_adjust=False,
            actions=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Could not infer full yfinance history start for %s: %s",
            symbol,
            exc,
        )
        return None

    if hist is None or hist.empty:
        return None

    first_ts = pd.Timestamp(hist.index[0]).to_pydatetime()
    if first_ts.tzinfo is None:
        first_ts = first_ts.replace(tzinfo=timezone.utc)
    return _normalize_utc_date(first_ts)


def _resolve_yfinance_history_jump_bounds(
    *,
    symbol: str,
    timeframe: str,
    requested_count: int,
    history_start_raw: str,
    history_end_raw: str,
) -> tuple[datetime, datetime]:
    today_utc = _normalize_utc_date(datetime.now(timezone.utc))
    history_end_utc = (
        _parse_optional_anchor_date(history_end_raw, arg_name="--yfinance-history-end")
        or today_utc
    )
    history_end_utc = _normalize_utc_date(history_end_utc)
    if history_end_utc > today_utc:
        logger.warning(
            "Requested --yfinance-history-end=%s is in the future. Clamping to %s.",
            history_end_utc.date().isoformat(),
            today_utc.date().isoformat(),
        )
        history_end_utc = today_utc

    interval = _map_timeframe_to_yf_interval(timeframe)
    lookback_days = _yfinance_intraday_lookback_days(interval)
    requested_start_utc = _parse_optional_anchor_date(
        history_start_raw,
        arg_name="--yfinance-history-start",
    )
    inferred_start_utc: datetime | None = None

    if requested_start_utc is not None:
        history_start_utc = _normalize_utc_date(requested_start_utc)
    elif lookback_days is not None:
        history_start_utc = _normalize_utc_date(
            history_end_utc - timedelta(days=lookback_days)
        )
    else:
        inferred_start_utc = _infer_yfinance_first_available_date_utc(symbol)
        if inferred_start_utc is not None:
            history_start_utc = inferred_start_utc
        else:
            fallback_days = max(3650, _window_days_for_count(timeframe, requested_count) * 4)
            history_start_utc = _normalize_utc_date(
                history_end_utc - timedelta(days=fallback_days)
            )
            logger.warning(
                "Falling back to last %d days for history jump (%s -> %s).",
                fallback_days,
                history_start_utc.date().isoformat(),
                history_end_utc.date().isoformat(),
            )

    # If start is auto-detected, shift it forward so random anchors can return
    # near requested_count candles (important for 1d where weekends reduce bars).
    if requested_start_utc is None and inferred_start_utc is not None:
        full_window_days = _window_days_for_count(timeframe, requested_count)
        min_anchor_for_full_window = _normalize_utc_date(
            inferred_start_utc + timedelta(days=full_window_days)
        )
        if history_start_utc < min_anchor_for_full_window <= history_end_utc:
            logger.info(
                "Adjusted history jump start for full-window anchors: %s -> %s",
                history_start_utc.date().isoformat(),
                min_anchor_for_full_window.date().isoformat(),
            )
            history_start_utc = min_anchor_for_full_window

    if lookback_days is not None:
        min_start = _normalize_utc_date(history_end_utc - timedelta(days=lookback_days))
        if history_start_utc < min_start:
            logger.warning(
                "Intraday interval %s allows about %d days on yfinance. "
                "Clamping history start from %s to %s.",
                interval,
                lookback_days,
                history_start_utc.date().isoformat(),
                min_start.date().isoformat(),
            )
            history_start_utc = min_start

    if history_start_utc > history_end_utc:
        raise ValueError(
            "Invalid history jump range: "
            f"start={history_start_utc.date().isoformat()} "
            f"is after end={history_end_utc.date().isoformat()}."
        )

    return history_start_utc, history_end_utc


def _pick_history_jump_anchor_date(
    *,
    run_idx: int,
    history_start_utc: datetime,
    history_end_utc: datetime,
    seed: int,
) -> datetime:
    start = _normalize_utc_date(history_start_utc)
    end = _normalize_utc_date(history_end_utc)
    span_days = max(0, (end - start).days)
    if span_days == 0:
        return start

    seed_material = (
        f"{seed}:{run_idx}:{start.date().isoformat()}:{end.date().isoformat()}"
    )
    digest = hashlib.sha256(seed_material.encode("utf-8")).hexdigest()
    offset_days = int(digest[:16], 16) % (span_days + 1)
    return start + timedelta(days=offset_days)


async def _fetch_candles_yfinance(
    symbol: str,
    timeframe: str,
    requested_count: int,
    anchor_date_utc: datetime | None = None,
) -> list[CandleData]:
    try:
        import yfinance as yf  # Local optional dependency
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("yfinance is not installed. Run: pip install yfinance") from exc

    interval = _map_timeframe_to_yf_interval(timeframe)
    ticker = yf.Ticker(symbol)
    if anchor_date_utc is None:
        period = _period_for_count(timeframe, requested_count)
        logger.info(
            "Fetching yfinance candles: symbol=%s interval=%s period=%s",
            symbol,
            interval,
            period,
        )
        hist = ticker.history(
            period=period,
            interval=interval,
            auto_adjust=False,
            actions=False,
        )
    else:
        window_days = _window_days_for_count(timeframe, requested_count)
        end_dt = anchor_date_utc + timedelta(days=1)
        start_dt = end_dt - timedelta(days=window_days)
        start_str = start_dt.strftime("%Y-%m-%d")
        end_str = end_dt.strftime("%Y-%m-%d")
        logger.info(
            "Fetching yfinance candles (anchored): symbol=%s interval=%s start=%s end=%s anchor=%s",
            symbol,
            interval,
            start_str,
            end_str,
            anchor_date_utc.date().isoformat(),
        )
        hist = ticker.history(
            start=start_str,
            end=end_str,
            interval=interval,
            auto_adjust=False,
            actions=False,
        )

    if hist is None or hist.empty:
        if anchor_date_utc is not None and interval in {
            "1m",
            "2m",
            "5m",
            "15m",
            "30m",
            "60m",
            "90m",
        }:
            raise RuntimeError(
                "No yfinance data returned for anchored intraday request "
                f"(symbol={symbol}, interval={interval}, anchor={anchor_date_utc.date().isoformat()}). "
                "Hint: use a newer anchor date or timeframe 1d."
            )
        raise RuntimeError(f"No yfinance data returned for symbol={symbol}.")

    hist = hist.tail(requested_count).copy()
    hist = hist.dropna(subset=["Open", "High", "Low", "Close"])

    candles: list[CandleData] = []
    for ts, row in hist.iterrows():
        timestamp = pd.Timestamp(ts).to_pydatetime()
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        candles.append(
            CandleData(
                timestamp=timestamp,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume", 0.0) or 0.0),
            )
        )
    if not candles:
        raise RuntimeError(f"Empty normalized candle set for symbol={symbol}.")
    return candles


def _append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_iso_datetime(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_lock_info(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _acquire_lock(path: Path, stale_seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        payload = {
            "pid": os.getpid(),
            "started_utc": datetime.now(timezone.utc).isoformat(),
        }
        try:
            with path.open("x", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            return
        except FileExistsError as exc:
            existing = _read_lock_info(path)
            existing_pid = int(existing.get("pid") or 0)
            existing_started = _parse_iso_datetime(existing.get("started_utc"))
            lock_age_seconds: float | None = None
            if existing_started is not None:
                lock_age_seconds = (
                    datetime.now(timezone.utc) - existing_started
                ).total_seconds()

            stale_by_pid = not _is_pid_running(existing_pid)
            stale_by_age = (
                stale_seconds > 0
                and lock_age_seconds is not None
                and lock_age_seconds > stale_seconds
            )
            if stale_by_pid or stale_by_age:
                logger.warning(
                    "Removing stale lock file %s (pid=%s running=%s age_s=%s).",
                    path,
                    existing_pid or None,
                    _is_pid_running(existing_pid),
                    round(lock_age_seconds or 0.0, 1) if lock_age_seconds is not None else None,
                )
                try:
                    path.unlink()
                except FileNotFoundError:
                    continue
                except Exception as rm_exc:  # noqa: BLE001
                    raise RuntimeError(
                        f"Could not remove stale lock file: {path}"
                    ) from rm_exc
                continue

            raise RuntimeError(
                f"Lock file exists: {path} (existing pid={existing.get('pid')}). "
                "Another overnight run may already be active."
            ) from exc


def _release_lock(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:  # noqa: BLE001
        logger.warning("Could not remove lock file: %s", path)


def _write_health(
    path: Path,
    payload: dict[str, Any],
    *,
    retries: int,
    retry_delay_seconds: float,
) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    last_error: Exception | None = None

    attempts = max(1, retries)
    for attempt in range(1, attempts + 1):
        try:
            tmp.write_text(serialized, encoding="utf-8")
            os.replace(tmp, path)
            return True
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "Health write attempt %d/%d failed for %s: %s",
                attempt,
                attempts,
                path,
                exc,
            )
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:  # noqa: BLE001
                pass
            if attempt < attempts:
                time.sleep(max(0.0, retry_delay_seconds) * attempt)

    fallback = path.with_suffix(path.suffix + ".fallback.json")
    try:
        fallback.write_text(serialized, encoding="utf-8")
        logger.error(
            "Primary health file unavailable. Wrote fallback health file: %s",
            fallback,
        )
    except Exception as fallback_exc:  # noqa: BLE001
        logger.error(
            "Health write failed for %s and fallback %s: %s / %s",
            path,
            fallback,
            last_error,
            fallback_exc,
        )
    return False


def _dataset_fingerprint(df: pd.DataFrame, tail_rows: int) -> str:
    if df.empty:
        return "empty"
    columns = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    tail = df[columns].tail(max(1, tail_rows)).copy()
    csv_blob = tail.to_csv(index=True)
    return hashlib.sha256(csv_blob.encode("utf-8")).hexdigest()


def _evaluate_quality_gate(
    metadata: dict[str, Any],
    *,
    min_profit_factor: float,
    min_f1: float,
) -> dict[str, Any]:
    xgb_pf = _safe_float(metadata.get("xgboost_profit_factor"))
    lgb_pf = _safe_float(metadata.get("lightgbm_profit_factor"))
    xgb_f1 = _safe_float(metadata.get("xgboost_f1"))
    lgb_f1 = _safe_float(metadata.get("lightgbm_f1"))

    valid_pf = [v for v in [xgb_pf, lgb_pf] if v is not None]
    valid_f1 = [v for v in [xgb_f1, lgb_f1] if v is not None]
    best_pf = max(valid_pf) if valid_pf else None
    best_f1 = max(valid_f1) if valid_f1 else None

    pf_pass = best_pf is not None and best_pf >= min_profit_factor
    f1_pass = best_f1 is not None and best_f1 >= min_f1
    accepted = pf_pass and f1_pass

    reason_parts: list[str] = []
    if not pf_pass:
        reason_parts.append(
            f"profit_factor {best_pf} < min {min_profit_factor}"
            if best_pf is not None
            else "profit_factor missing"
        )
    if not f1_pass:
        reason_parts.append(
            f"f1 {best_f1} < min {min_f1}" if best_f1 is not None else "f1 missing"
        )

    return {
        "accepted": accepted,
        "reason": "pass" if accepted else "; ".join(reason_parts),
        "thresholds": {
            "min_profit_factor": min_profit_factor,
            "min_f1": min_f1,
        },
        "metrics": {
            "xgboost_profit_factor": xgb_pf,
            "lightgbm_profit_factor": lgb_pf,
            "xgboost_f1": xgb_f1,
            "lightgbm_f1": lgb_f1,
            "best_profit_factor": best_pf,
            "best_f1": best_f1,
        },
    }


def _atomic_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def _promote_candidate_models(candidate_dir: Path, accepted_dir: Path) -> list[str]:
    missing = [
        name
        for name in MODEL_ARTIFACT_FILES
        if not (candidate_dir / name).exists()
    ]
    if missing:
        raise RuntimeError(
            "Candidate model artifacts missing: " + ", ".join(missing)
        )

    promoted: list[str] = []
    for name in MODEL_ARTIFACT_FILES:
        src = candidate_dir / name
        dst = accepted_dir / name
        _atomic_copy(src, dst)
        promoted.append(name)
    return promoted


async def _fetch_with_retries(
    args: argparse.Namespace,
    client: CapitalComClient | None,
    *,
    yfinance_anchor_date_utc: datetime | None = None,
) -> list[CandleData]:
    last_error: Exception | None = None
    for attempt in range(1, args.fetch_retries + 1):
        try:
            if args.source == "broker":
                assert client is not None
                return await _fetch_candles_with_fallback(
                    client=client,
                    timeframe=args.timeframe,
                    requested_count=args.count,
                    allow_count_fallback=args.allow_count_fallback,
                )

            return await _fetch_candles_yfinance(
                symbol=args.symbol,
                timeframe=args.timeframe,
                requested_count=args.count,
                anchor_date_utc=yfinance_anchor_date_utc,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("Data fetch attempt %d/%d failed: %s", attempt, args.fetch_retries, exc)
            if args.source == "broker" and client is not None:
                try:
                    await client.authenticate()
                    logger.info("Broker re-authentication successful (retry path).")
                except Exception as auth_exc:  # noqa: BLE001
                    logger.warning("Broker re-authentication failed: %s", auth_exc)

            if attempt < args.fetch_retries:
                await asyncio.sleep(args.retry_delay_seconds)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Data fetch failed without explicit error.")


async def _run(args: argparse.Namespace) -> int:
    load_dotenv()

    if args.dry_run:
        logger.warning(
            "DRY-RUN active: skipping lock, health/run-log writes, "
            "model serialization and promotion. Logging planned actions only."
        )
        logger.info(
            "DRY-RUN plan: source=%s timeframe=%s count=%d hours=%.2f "
            "interval_minutes=%.2f output=%s candidate=%s run_log=%s health_file=%s",
            args.source,
            args.timeframe,
            args.count,
            args.hours,
            args.interval_minutes,
            args.output,
            args.candidate_output or f"{args.output}/candidate",
            args.run_log,
            args.health_file,
        )
        if args.source == "broker":
            try:
                _load_broker_creds()
                logger.info("DRY-RUN: broker credentials present (validated, not used).")
            except RuntimeError as exc:
                logger.error("DRY-RUN: broker credential check failed: %s", exc)
                return 1
        logger.info(
            "DRY-RUN: would train and (if quality gate passes) promote models to %s. "
            "No files written. Exiting.",
            args.output,
        )
        return 0

    log_path = Path(args.run_log)
    accepted_output_dir = Path(args.output)
    candidate_output_dir = (
        Path(args.candidate_output)
        if args.candidate_output
        else accepted_output_dir / "candidate"
    )
    lock_path = Path(args.lock_file)
    health_path = Path(args.health_file)
    accepted_output_dir.mkdir(parents=True, exist_ok=True)
    candidate_output_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    health_path.parent.mkdir(parents=True, exist_ok=True)

    trainer = ModelTrainer(
        saved_models_dir=str(candidate_output_dir),
        tp_pips=args.tp_pips,
        sl_pips=args.sl_pips,
        spread_pips=args.spread_pips,
    )

    creds: BrokerCreds | None = None
    client: CapitalComClient | None = None
    if args.source == "broker":
        creds = _load_broker_creds()
        client = CapitalComClient(
            email=creds.email,
            password=creds.password,
            api_key=creds.api_key,
            demo=creds.demo,
        )

    started_at = datetime.now(timezone.utc)
    ends_at = started_at + timedelta(hours=args.hours)
    run_idx = 1
    consecutive_errors = 0
    final_status = "finished"
    final_error: str | None = None
    last_cycle_error: str | None = None
    last_data_fingerprint: str | None = None
    last_candle_utc: str | None = None
    skipped_no_new_data = 0
    promoted_runs = 0
    health_write_failures = 0
    last_quality_gate: dict[str, Any] | None = None
    last_promotion_utc: str | None = None
    yfinance_anchor_dates = _parse_anchor_dates(args.yfinance_anchor_dates)
    yfinance_history_jump_enabled = bool(
        args.source == "yfinance" and args.yfinance_full_history_jump
    )
    yfinance_history_jump_start_utc: datetime | None = None
    yfinance_history_jump_end_utc: datetime | None = None
    yfinance_history_jump_seed: int | None = None
    active_anchor_date_utc: datetime | None = None
    yfinance_anchor_mode = "disabled"
    if args.source == "yfinance":
        if yfinance_history_jump_enabled:
            yfinance_anchor_mode = "history_jump"
        elif yfinance_anchor_dates:
            yfinance_anchor_mode = "fixed_cycle"
        else:
            yfinance_anchor_mode = "rolling_recent"

    if yfinance_history_jump_enabled:
        yfinance_history_jump_seed = (
            args.yfinance_history_seed
            if args.yfinance_history_seed is not None
            else int.from_bytes(os.urandom(8), byteorder="big")
        )
        yfinance_history_jump_start_utc, yfinance_history_jump_end_utc = (
            _resolve_yfinance_history_jump_bounds(
                symbol=args.symbol,
                timeframe=args.timeframe,
                requested_count=args.count,
                history_start_raw=args.yfinance_history_start,
                history_end_raw=args.yfinance_history_end,
            )
        )
        if yfinance_anchor_dates:
            logger.warning(
                "Both --yfinance-full-history-jump and --yfinance-anchor-dates were set. "
                "Ignoring fixed anchor dates and using history jump mode."
            )

    _acquire_lock(lock_path, stale_seconds=args.lock_stale_seconds)

    def _select_anchor_date_for_run(idx: int) -> datetime | None:
        if args.source != "yfinance":
            return None
        if yfinance_history_jump_enabled:
            assert yfinance_history_jump_start_utc is not None
            assert yfinance_history_jump_end_utc is not None
            assert yfinance_history_jump_seed is not None
            return _pick_history_jump_anchor_date(
                run_idx=idx,
                history_start_utc=yfinance_history_jump_start_utc,
                history_end_utc=yfinance_history_jump_end_utc,
                seed=yfinance_history_jump_seed,
            )
        if yfinance_anchor_dates:
            return yfinance_anchor_dates[(idx - 1) % len(yfinance_anchor_dates)]
        return None

    def emit_health(
        *,
        status: str,
        run: int,
        next_run_utc: str | None,
        last_run_status: str | None = None,
        last_run_elapsed_seconds: float | None = None,
        last_run_candles: int | None = None,
        last_error: str | None = None,
    ) -> None:
        nonlocal health_write_failures
        payload: dict[str, Any] = {
            "status": status,
            "pid": os.getpid(),
            "source": args.source,
            "symbol": args.symbol if args.source == "yfinance" else None,
            "timeframe": args.timeframe,
            "requested_count": args.count,
            "started_utc": started_at.isoformat(),
            "ends_utc": ends_at.isoformat(),
            "last_update_utc": datetime.now(timezone.utc).isoformat(),
            "run": run,
            "consecutive_errors": consecutive_errors,
            "max_consecutive_errors": args.max_consecutive_errors,
            "next_run_utc": next_run_utc,
            "last_error": last_error,
            "last_data_fingerprint": last_data_fingerprint,
            "last_candle_utc": last_candle_utc,
            "skipped_no_new_data": skipped_no_new_data,
            "promoted_runs": promoted_runs,
            "last_promotion_utc": last_promotion_utc,
            "health_write_failures": health_write_failures,
            "candidate_output_dir": str(candidate_output_dir),
            "accepted_output_dir": str(accepted_output_dir),
            "require_new_candle": args.require_new_candle,
            "yfinance_anchor_dates": [d.date().isoformat() for d in yfinance_anchor_dates],
            "active_anchor_date_utc": (
                active_anchor_date_utc.isoformat() if active_anchor_date_utc else None
            ),
            "yfinance_anchor_mode": yfinance_anchor_mode,
            "yfinance_history_jump_start_utc": (
                yfinance_history_jump_start_utc.isoformat()
                if yfinance_history_jump_start_utc
                else None
            ),
            "yfinance_history_jump_end_utc": (
                yfinance_history_jump_end_utc.isoformat()
                if yfinance_history_jump_end_utc
                else None
            ),
            "yfinance_history_jump_seed": (
                yfinance_history_jump_seed if yfinance_history_jump_enabled else None
            ),
        }
        if last_run_status is not None:
            payload["last_run_status"] = last_run_status
        if last_run_elapsed_seconds is not None:
            payload["last_run_elapsed_seconds"] = last_run_elapsed_seconds
        if last_run_candles is not None:
            payload["last_run_candles"] = last_run_candles
        if last_quality_gate is not None:
            payload["last_quality_gate"] = last_quality_gate

        ok = _write_health(
            health_path,
            payload,
            retries=args.health_write_retries,
            retry_delay_seconds=args.health_write_delay_seconds,
        )
        if not ok:
            health_write_failures += 1

    emit_health(
        status="starting",
        run=0,
        next_run_utc=started_at.isoformat(),
    )

    logger.info(
        "Overnight training started: hours=%.2f, interval=%.1f min, timeframe=%s, count=%d, mode=%s",
        args.hours,
        args.interval_minutes,
        args.timeframe,
        args.count,
        ("DEMO" if creds and creds.demo else "LIVE") if args.source == "broker" else "YFINANCE",
    )
    logger.info("Run window: %s -> %s", started_at.isoformat(), ends_at.isoformat())
    logger.info(
        "Outputs: candidate=%s -> accepted=%s",
        candidate_output_dir,
        accepted_output_dir,
    )
    logger.info(
        "Quality gate: min_profit_factor=%.3f min_f1=%.3f require_new_candle=%s",
        args.min_profit_factor,
        args.min_f1,
        args.require_new_candle,
    )
    if yfinance_anchor_dates and args.source == "yfinance":
        logger.info(
            "YFinance anchor cycling active: %s",
            ", ".join(d.date().isoformat() for d in yfinance_anchor_dates),
        )
    if yfinance_history_jump_enabled:
        assert yfinance_history_jump_start_utc is not None
        assert yfinance_history_jump_end_utc is not None
        assert yfinance_history_jump_seed is not None
        logger.info(
            "YFinance history-jump active: start=%s end=%s seed=%d",
            yfinance_history_jump_start_utc.date().isoformat(),
            yfinance_history_jump_end_utc.date().isoformat(),
            yfinance_history_jump_seed,
        )

    try:
        if args.source == "broker":
            assert client is not None
            await client.authenticate()
            logger.info("Broker authentication OK")

        if args.preflight:
            logger.info("Running preflight check...")
            preflight_anchor = _select_anchor_date_for_run(run_idx)
            preflight_candles = await _fetch_with_retries(
                args=args,
                client=client,
                yfinance_anchor_date_utc=preflight_anchor,
            )
            if len(preflight_candles) < args.min_candles:
                raise RuntimeError(
                    f"Preflight failed: candles={len(preflight_candles)} < min={args.min_candles}"
                )
            logger.info("Preflight OK (candles=%d).", len(preflight_candles))

        while True:
            now = datetime.now(timezone.utc)
            if run_idx > 1 and now >= ends_at:
                logger.info("Target duration reached. Stopping training loop.")
                break

            cycle_started = time.monotonic()
            cycle_stamp = datetime.now(timezone.utc).isoformat()
            status = "ok"
            error_msg = ""
            summary: dict[str, Any] = {}
            candle_count = 0
            latest_candle_for_run: str | None = None

            try:
                active_anchor_date_utc = _select_anchor_date_for_run(run_idx)
                candles = await _fetch_with_retries(
                    args=args,
                    client=client,
                    yfinance_anchor_date_utc=active_anchor_date_utc,
                )
                candle_count = len(candles)
                if candle_count < args.min_candles:
                    raise RuntimeError(
                        f"Too few candles returned ({candle_count} < {args.min_candles})."
                    )

                df = _candles_to_df(candles)
                latest_candle_for_run = (
                    df.index[-1].to_pydatetime().astimezone(timezone.utc).isoformat()
                    if not df.empty
                    else None
                )
                current_fingerprint = _dataset_fingerprint(
                    df, tail_rows=args.fingerprint_tail_rows
                )

                if args.require_new_candle and last_data_fingerprint == current_fingerprint:
                    status = "skipped_no_new_data"
                    skipped_no_new_data += 1
                    summary = {
                        "skip_reason": "no_new_data_fingerprint",
                        "fingerprint_tail_rows": args.fingerprint_tail_rows,
                        "latest_candle_utc": latest_candle_for_run,
                        "yfinance_anchor_date_utc": (
                            active_anchor_date_utc.isoformat()
                            if active_anchor_date_utc
                            else None
                        ),
                        "candidate_output_dir": str(candidate_output_dir),
                        "accepted_output_dir": str(accepted_output_dir),
                    }
                    logger.info(
                        "Run %d skipped: no new candle fingerprint (latest=%s).",
                        run_idx,
                        latest_candle_for_run,
                    )
                else:
                    result = trainer.train_all(df=df, timeframe=args.timeframe)
                    meta = result.get("metadata", {})
                    xgb_eval = result.get("xgboost_eval", {})
                    lgb_eval = result.get("lightgbm_eval", {})
                    xgb_trading = result.get("xgboost_trading", {})
                    lgb_trading = result.get("lightgbm_trading", {})

                    xgb_n_samples = (
                        xgb_eval.get("n_samples") if isinstance(xgb_eval, dict) else None
                    )
                    lgb_n_samples = (
                        lgb_eval.get("n_samples") if isinstance(lgb_eval, dict) else None
                    )
                    if not isinstance(xgb_n_samples, (int, float)):
                        xgb_n_samples = meta.get("n_samples_test")
                    if not isinstance(lgb_n_samples, (int, float)):
                        lgb_n_samples = meta.get("n_samples_test")

                    xgb_n_trades = (
                        xgb_trading.get("n_trades")
                        if isinstance(xgb_trading, dict)
                        else None
                    )
                    lgb_n_trades = (
                        lgb_trading.get("n_trades")
                        if isinstance(lgb_trading, dict)
                        else None
                    )
                    xgb_hold_signals = (
                        max(0, int(xgb_n_samples) - int(xgb_n_trades))
                        if isinstance(xgb_n_samples, (int, float))
                        and isinstance(xgb_n_trades, (int, float))
                        else None
                    )
                    lgb_hold_signals = (
                        max(0, int(lgb_n_samples) - int(lgb_n_trades))
                        if isinstance(lgb_n_samples, (int, float))
                        and isinstance(lgb_n_trades, (int, float))
                        else None
                    )

                    gate = _evaluate_quality_gate(
                        meta,
                        min_profit_factor=args.min_profit_factor,
                        min_f1=args.min_f1,
                    )
                    last_quality_gate = gate
                    summary = {
                        "n_samples_total": meta.get("n_samples_total"),
                        "n_features_selected": meta.get("n_features_selected"),
                        "xgboost_f1": meta.get("xgboost_f1"),
                        "lightgbm_f1": meta.get("lightgbm_f1"),
                        "xgboost_win_rate": meta.get("xgboost_win_rate"),
                        "lightgbm_win_rate": meta.get("lightgbm_win_rate"),
                        "xgboost_profit_factor": meta.get("xgboost_profit_factor"),
                        "lightgbm_profit_factor": meta.get("lightgbm_profit_factor"),
                        "n_samples_test": meta.get("n_samples_test"),
                        "label_stats": meta.get("label_stats"),
                        "yfinance_anchor_date_utc": (
                            active_anchor_date_utc.isoformat()
                            if active_anchor_date_utc
                            else None
                        ),
                        "signals": {
                            "xgboost": {
                                "buy": (
                                    xgb_trading.get("buy_signals")
                                    if isinstance(xgb_trading, dict)
                                    else None
                                ),
                                "hold": xgb_hold_signals,
                                "sell": (
                                    xgb_trading.get("sell_signals")
                                    if isinstance(xgb_trading, dict)
                                    else None
                                ),
                            },
                            "lightgbm": {
                                "buy": (
                                    lgb_trading.get("buy_signals")
                                    if isinstance(lgb_trading, dict)
                                    else None
                                ),
                                "hold": lgb_hold_signals,
                                "sell": (
                                    lgb_trading.get("sell_signals")
                                    if isinstance(lgb_trading, dict)
                                    else None
                                ),
                            },
                        },
                        "training_duration_seconds": meta.get("training_duration_seconds"),
                        "quality_gate": gate,
                        "candidate_output_dir": str(candidate_output_dir),
                        "accepted_output_dir": str(accepted_output_dir),
                    }
                    if gate["accepted"]:
                        promoted_files = _promote_candidate_models(
                            candidate_output_dir, accepted_output_dir
                        )
                        promoted_runs += 1
                        last_promotion_utc = datetime.now(timezone.utc).isoformat()
                        summary["promoted"] = True
                        summary["promoted_files"] = promoted_files
                    else:
                        status = "rejected_quality"
                        summary["promoted"] = False
                        summary["promoted_files"] = []

                    logger.info(
                        "Run %d done: candles=%d, samples=%s, features=%s, xgb_f1=%s, "
                        "lgb_f1=%s, accepted=%s",
                        run_idx,
                        candle_count,
                        summary.get("n_samples_total"),
                        summary.get("n_features_selected"),
                        summary.get("xgboost_f1"),
                        summary.get("lightgbm_f1"),
                        gate["accepted"],
                    )

                last_data_fingerprint = current_fingerprint
                last_candle_utc = latest_candle_for_run
                consecutive_errors = 0
            except Exception as exc:  # noqa: BLE001
                status = "error"
                error_msg = str(exc)
                last_cycle_error = error_msg
                consecutive_errors += 1
                logger.exception("Run %d failed: %s", run_idx, exc)
            else:
                last_cycle_error = None

            elapsed = round(time.monotonic() - cycle_started, 2)
            entry = {
                "run": run_idx,
                "timestamp_utc": cycle_stamp,
                "status": status,
                "error": error_msg or None,
                "timeframe": args.timeframe,
                "requested_count": args.count,
                "source": args.source,
                "symbol": args.symbol if args.source == "yfinance" else None,
                "yfinance_anchor_date_utc": (
                    active_anchor_date_utc.isoformat()
                    if active_anchor_date_utc
                    else None
                ),
                "yfinance_anchor_mode": yfinance_anchor_mode,
                "candles_received": candle_count,
                "elapsed_seconds": elapsed,
                "consecutive_errors": consecutive_errors,
                "summary": summary,
            }
            _append_jsonl(log_path, entry)

            if args.once:
                logger.info("Single-run mode active. Stopping after one cycle.")
                break

            remaining = (ends_at - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                logger.info("Target duration reached after run %d.", run_idx)
                break

            if consecutive_errors >= args.max_consecutive_errors:
                logger.error(
                    "Stopping after %d consecutive failed runs (max=%d).",
                    consecutive_errors,
                    args.max_consecutive_errors,
                )
                final_status = "stopped_error"
                final_error = error_msg or "consecutive failures exceeded"
                return 2

            base_sleep_seconds = max(0.0, args.interval_minutes * 60.0)
            if status == "skipped_no_new_data":
                base_sleep_seconds = max(base_sleep_seconds, args.no_new_data_sleep_seconds)
            sleep_seconds = min(base_sleep_seconds, remaining)
            next_run_utc = (
                datetime.now(timezone.utc) + timedelta(seconds=sleep_seconds)
            ).isoformat()
            emit_health(
                status="running",
                run=run_idx,
                next_run_utc=next_run_utc,
                last_run_status=status,
                last_run_elapsed_seconds=elapsed,
                last_run_candles=candle_count,
                last_error=error_msg or None,
            )
            if sleep_seconds > 0:
                logger.info("Sleeping %.2f seconds until next run...", sleep_seconds)
                await asyncio.sleep(sleep_seconds)
            else:
                await asyncio.sleep(0)
            run_idx += 1

    except Exception as exc:  # noqa: BLE001
        final_status = "failed"
        final_error = str(exc)
        raise
    finally:
        if client is not None:
            await client.close()
        emit_health(
            status=final_status,
            run=run_idx,
            next_run_utc=None,
            last_error=final_error or last_cycle_error,
        )
        _release_lock(lock_path)

    logger.info("Overnight training finished.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run repeated real-data training cycles overnight."
    )
    p.add_argument("--hours", type=float, default=8.0, help="Total run duration in hours.")
    p.add_argument(
        "--interval-minutes",
        type=float,
        default=15.0,
        help="Pause between cycles in minutes.",
    )
    p.add_argument("--timeframe", type=str, default="5m", help="Broker timeframe (e.g. 5m).")
    p.add_argument(
        "--source",
        choices=["broker", "yfinance"],
        default="broker",
        help="Market data source for training.",
    )
    p.add_argument(
        "--symbol",
        type=str,
        default="XAUUSD=X",
        help="Ticker symbol when --source yfinance is used.",
    )
    p.add_argument(
        "--yfinance-anchor-dates",
        type=str,
        default="",
        help=(
            "Comma-separated anchor dates to alternate per run for yfinance. "
            "Formats: YYYY-MM-DD or DD.MM.YYYY. "
            "Example: 2021-03-11,2025-03-31"
        ),
    )
    p.add_argument(
        "--yfinance-full-history-jump",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "For yfinance, select a different anchor date on every run across the "
            "available history (or configured start/end range)."
        ),
    )
    p.add_argument(
        "--yfinance-history-start",
        type=str,
        default="",
        help=(
            "Optional earliest date for --yfinance-full-history-jump. "
            "Formats: YYYY-MM-DD or DD.MM.YYYY."
        ),
    )
    p.add_argument(
        "--yfinance-history-end",
        type=str,
        default="",
        help=(
            "Optional latest date for --yfinance-full-history-jump. "
            "Formats: YYYY-MM-DD or DD.MM.YYYY."
        ),
    )
    p.add_argument(
        "--yfinance-history-seed",
        type=int,
        default=None,
        help=(
            "Optional deterministic seed for --yfinance-full-history-jump. "
            "If omitted, a random seed is generated per process start."
        ),
    )
    p.add_argument(
        "--count",
        type=int,
        default=1200,
        help="Requested candle count per cycle.",
    )
    p.add_argument(
        "--allow-count-fallback",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Allow automatic fallback to smaller broker candle counts "
            "when requested count fails."
        ),
    )
    p.add_argument(
        "--min-candles",
        type=int,
        default=500,
        help="Minimum candles required to run a training cycle.",
    )
    p.add_argument(
        "--output",
        type=str,
        default="ai_engine/saved_models",
        help="Accepted model output directory used by live predictor.",
    )
    p.add_argument(
        "--candidate-output",
        type=str,
        default=None,
        help=(
            "Candidate model output directory for each training run. "
            "Defaults to <output>/candidate."
        ),
    )
    p.add_argument(
        "--run-log",
        type=str,
        default="logs/overnight_training_runs.jsonl",
        help="JSONL file for per-run status.",
    )
    p.add_argument(
        "--health-file",
        type=str,
        default="logs/overnight_training_health.json",
        help="Heartbeat/health JSON file.",
    )
    p.add_argument(
        "--lock-file",
        type=str,
        default="logs/overnight_training.lock",
        help="Process lock file to prevent parallel runners.",
    )
    p.add_argument(
        "--lock-stale-seconds",
        type=float,
        default=43200.0,
        help=(
            "Treat existing lock as stale after this age (seconds) "
            "or when PID is no longer running."
        ),
    )
    p.add_argument(
        "--fetch-retries",
        type=int,
        default=3,
        help="Number of retries for data fetch per run.",
    )
    p.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=20.0,
        help="Sleep between fetch retries.",
    )
    p.add_argument(
        "--max-consecutive-errors",
        type=int,
        default=6,
        help="Stop run after this many consecutive failed cycles.",
    )
    p.add_argument(
        "--preflight",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable startup connectivity/data preflight check.",
    )
    p.add_argument(
        "--require-new-candle",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip training cycle if candle fingerprint did not change.",
    )
    p.add_argument(
        "--fingerprint-tail-rows",
        type=int,
        default=300,
        help="Number of latest rows used to compute candle fingerprint.",
    )
    p.add_argument(
        "--no-new-data-sleep-seconds",
        type=float,
        default=5.0,
        help="Sleep duration used when no new candle is available.",
    )
    p.add_argument(
        "--min-profit-factor",
        type=float,
        default=1.05,
        help="Minimum best profit factor required before promoting models.",
    )
    p.add_argument(
        "--min-f1",
        type=float,
        default=0.55,
        help="Minimum best weighted F1 required before promoting models.",
    )
    p.add_argument(
        "--health-write-retries",
        type=int,
        default=6,
        help="Retries for health file writes before fallback file is used.",
    )
    p.add_argument(
        "--health-write-delay-seconds",
        type=float,
        default=0.2,
        help="Base delay between health file write retries.",
    )
    p.add_argument("--tp-pips", type=float, default=1500.0)
    p.add_argument("--sl-pips", type=float, default=800.0)
    p.add_argument("--spread-pips", type=float, default=2.5)
    p.add_argument(
        "--once",
        action="store_true",
        help="Run only one cycle (smoke test).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Log planned actions but skip data writes (run log, health file, "
            "lock file) and skip model serialization / promotion."
        ),
    )
    return p


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    # Log to stderr (captured by the PowerShell launcher's -RedirectStandardError)
    # AND to a rotating file so overnight runs can't produce unbounded logs.
    # Historical issue: logs/overnight_training_stderr.log grew to 77 MB with no
    # rotation because the PowerShell redirect has no size limit. The rotating
    # handler below caps Python-generated log output at ~50 MB * 3 backups.
    from logging.handlers import RotatingFileHandler as _RFH

    _log_dir = Path("logs")
    _log_dir.mkdir(parents=True, exist_ok=True)
    _formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    _rotating = _RFH(
        _log_dir / "overnight_training.log",
        maxBytes=50 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    _rotating.setFormatter(_formatter)

    _stream = logging.StreamHandler()
    _stream.setFormatter(_formatter)

    _root = logging.getLogger()
    _root.setLevel(logging.INFO)
    # Avoid duplicate handlers if main() is ever re-entered.
    _root.handlers = [_stream, _rotating]

    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 130
    except Exception as exc:  # noqa: BLE001
        logger.error("Fatal error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
