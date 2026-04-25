"""Capital.com quote-flow helpers for optional order-flow enrichment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class QuoteFlowRecord:
    """Normalized single-quote order-flow observation."""

    timestamp: pd.Timestamp
    bid: float
    ofr: float
    bid_qty: float
    ofr_qty: float
    flow_l1_imbalance: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ofr) / 2.0

    @property
    def spread(self) -> float:
        return max(self.ofr - self.bid, 0.0)


class QuoteFlowAggregator:
    """Aggregate Capital.com L1 quote imbalance into candle buckets."""

    def __init__(self, timeframe: str = "5min") -> None:
        self.timeframe = _normalise_timeframe(timeframe)
        self._records: list[QuoteFlowRecord] = []

    def add_payload(self, payload: dict[str, Any]) -> QuoteFlowRecord | None:
        """Normalize and store a quote payload; invalid payloads are ignored."""
        record = normalize_quote_payload(payload)
        if record is None:
            return None
        self._records.append(record)
        return record

    def clear(self) -> None:
        self._records.clear()

    def to_frame(self) -> pd.DataFrame:
        """Return candle-aligned quote-flow enrichment columns."""
        if not self._records:
            return pd.DataFrame(
                columns=[
                    "timestamp",
                    "flow_l1_imbalance",
                    "flow_l1_imbalance_ema_10",
                    "quote_count",
                    "l1_mid",
                    "l1_spread",
                ]
            )

        rows = []
        for record in self._records:
            bucket = record.timestamp.floor(self.timeframe)
            rows.append(
                {
                    "timestamp": bucket,
                    "flow_l1_imbalance": record.flow_l1_imbalance,
                    "quote_count": 1,
                    "l1_mid": record.mid,
                    "l1_spread": record.spread,
                }
            )

        frame = pd.DataFrame(rows)
        grouped = (
            frame.groupby("timestamp", as_index=False)
            .agg(
                {
                    "flow_l1_imbalance": "mean",
                    "quote_count": "sum",
                    "l1_mid": "mean",
                    "l1_spread": "mean",
                }
            )
            .sort_values("timestamp")
            .reset_index(drop=True)
        )
        grouped["flow_l1_imbalance"] = grouped["flow_l1_imbalance"].clip(-1.0, 1.0)
        grouped["flow_l1_imbalance_ema_10"] = (
            grouped["flow_l1_imbalance"].ewm(span=10, adjust=False).mean()
        )
        return grouped.set_index("timestamp", drop=False)


def compute_l1_imbalance(bid_qty: Any, ofr_qty: Any) -> float:
    """Return bounded L1 bid/offer quantity imbalance."""
    bid = _optional_float(bid_qty)
    offer = _optional_float(ofr_qty)
    if bid is None or offer is None:
        return 0.0
    total = bid + offer
    if not np.isfinite(total) or total <= 1e-9:
        return 0.0
    imbalance = (bid - offer) / total
    return float(np.clip(imbalance, -1.0, 1.0))


def normalize_quote_payload(payload: dict[str, Any]) -> QuoteFlowRecord | None:
    """Normalize a Capital.com quote payload into a feature-ready record."""
    timestamp = _parse_timestamp(payload.get("timestamp") or payload.get("time"))
    bid = _optional_float(payload.get("bid"))
    ofr = _optional_float(payload.get("ofr", payload.get("ask")))
    if timestamp is None or bid is None or ofr is None:
        return None

    bid_qty = _optional_float(payload.get("bidQty")) or 0.0
    ofr_qty = _optional_float(payload.get("ofrQty", payload.get("askQty"))) or 0.0
    return QuoteFlowRecord(
        timestamp=timestamp,
        bid=bid,
        ofr=ofr,
        bid_qty=bid_qty,
        ofr_qty=ofr_qty,
        flow_l1_imbalance=compute_l1_imbalance(bid_qty, ofr_qty),
    )


def _safe_float(value: Any) -> float:
    parsed = _optional_float(value)
    return 0.0 if parsed is None else parsed


def _optional_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if np.isfinite(parsed) else None


def _parse_timestamp(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        unit = "ms" if abs(float(value)) > 10_000_000_000 else "s"
        ts = pd.to_datetime(value, unit=unit, utc=True, errors="coerce")
    else:
        ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts)


def _normalise_timeframe(timeframe: str) -> str:
    mapping = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
    }
    return mapping.get(timeframe, timeframe)
