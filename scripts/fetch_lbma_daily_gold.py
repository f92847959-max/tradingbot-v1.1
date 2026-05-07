"""Download LBMA PM daily gold history and write a training CSV."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_URL = "https://prices.lbma.org.uk/json/gold_pm.json"


def download_lbma_json(url: str) -> list[dict]:
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise ValueError("LBMA response is not a list")
    return payload


def lbma_to_ohlcv(rows: list[dict]) -> pd.DataFrame:
    records = []
    for row in rows:
        values = row.get("v") or []
        if not values or values[0] is None:
            continue
        records.append(
            {
                "timestamp": pd.Timestamp(row["d"], tz="UTC"),
                "open": float(values[0]),
                "high": float(values[0]),
                "low": float(values[0]),
                "close": float(values[0]),
                "volume": 0.0,
                "source": "lbma_gold_pm_usd",
            }
        )
    if not records:
        raise ValueError("LBMA response contained no USD gold prices")
    df = pd.DataFrame.from_records(records).sort_values("timestamp")
    return df.drop_duplicates(subset=["timestamp"], keep="last")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch LBMA PM daily gold history")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", default=str(ROOT / "data" / "gold_1d.csv"))
    args = parser.parse_args()

    rows = download_lbma_json(args.url)
    df = lbma_to_ohlcv(rows)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)
    first = df["timestamp"].iloc[0].isoformat()
    last = df["timestamp"].iloc[-1].isoformat()
    print(f"Wrote {len(df)} LBMA daily rows -> {output}")
    print(f"Range: {first} -> {last}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
