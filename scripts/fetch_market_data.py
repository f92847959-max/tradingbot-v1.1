"""Download Gold and Silver OHLCV data via yfinance for training.

Free, no API key needed. Caches to data/{asset}_1h.csv.

Usage:
    python scripts/fetch_market_data.py                    # both assets, skip if cache <24h
    python scripts/fetch_market_data.py --force            # force refresh
    python scripts/fetch_market_data.py --asset gold       # only gold
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

ASSETS = {
    "gold":   {"symbol": "GC=F", "fallback": "GLD", "csv": "gold_1h.csv",   "label": "Gold"},
    "silver": {"symbol": "SI=F", "fallback": "SLV", "csv": "silver_1h.csv", "label": "Silber"},
}

CACHE_TTL_HOURS = 24

logger = logging.getLogger("fetch_market_data")


def _is_fresh(path: Path, ttl_hours: int = CACHE_TTL_HOURS) -> bool:
    if not path.exists():
        return False
    age_sec = datetime.now().timestamp() - path.stat().st_mtime
    return age_sec < ttl_hours * 3600


def _to_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize yfinance DataFrame to lowercase OHLCV with timestamp index."""
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
        "Adj Close": "adj_close",
    })
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[keep].copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df.index.name = "timestamp"
    df = df.dropna()
    return df


def fetch_one(asset_key: str, period: str = "730d", interval: str = "1h") -> pd.DataFrame:
    asset = ASSETS[asset_key]
    for symbol in (asset["symbol"], asset["fallback"]):
        logger.info("Lade %s (%s, period=%s, interval=%s)", asset["label"], symbol, period, interval)
        try:
            df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
            df = _to_ohlcv(df)
            if not df.empty:
                logger.info("  %d Kerzen erhalten von %s", len(df), symbol)
                return df
            logger.warning("  Leere Antwort von %s, versuche Fallback", symbol)
        except Exception as exc:
            logger.warning("  Fehler bei %s: %s", symbol, exc)
    raise RuntimeError(f"Keine Daten für {asset['label']} verfügbar")


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)
    logger.info("Gespeichert: %s (%d Zeilen, %.1f KB)", path, len(df), path.stat().st_size / 1024)


def fetch_assets(asset_keys: list[str], force: bool = False) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for key in asset_keys:
        csv_path = DATA_DIR / ASSETS[key]["csv"]
        if not force and _is_fresh(csv_path):
            logger.info("Cache OK für %s (%s) — übersprungen", ASSETS[key]["label"], csv_path)
            out[key] = csv_path
            continue
        df = fetch_one(key)
        save_csv(df, csv_path)
        out[key] = csv_path
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Gold + Silver OHLCV via yfinance")
    parser.add_argument("--asset", choices=["gold", "silver", "both"], default="both")
    parser.add_argument("--force", action="store_true", help="Cache ignorieren, neu laden")
    parser.add_argument("--period", default="730d", help="Zeitraum (yfinance-Syntax: 1d, 5d, 1mo, 730d, max)")
    parser.add_argument("--interval", default="1h", help="Intervall: 5m, 1h, 1d (1h empfohlen)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    keys = ["gold", "silver"] if args.asset == "both" else [args.asset]
    paths = fetch_assets(keys, force=args.force)

    print("\nFertig:")
    for key, path in paths.items():
        print(f"  {ASSETS[key]['label']}: {path}")


if __name__ == "__main__":
    main()
