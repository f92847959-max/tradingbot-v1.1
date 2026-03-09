"""Shared utility functions for the Gold Intraday Trading System."""

from datetime import datetime, time, timezone
from typing import Optional

from shared.constants import (
    CONTRACT_SIZE,
    PIP_SIZE,
    LONDON_OPEN_HOUR,
    LONDON_CLOSE_HOUR,
    LONDON_CLOSE_MINUTE,
    NY_OPEN_HOUR,
    NY_CLOSE_HOUR,
    NY_CLOSE_MINUTE,
)


def pip_value(price_diff: float) -> float:
    """Convert absolute price difference to pips."""
    return abs(price_diff) / PIP_SIZE


def pips_to_price(pips: float) -> float:
    """Convert pips to price units."""
    return pips * PIP_SIZE


def format_price(price: float) -> str:
    return f"{price:.2f}"


def format_pnl(pnl: float) -> str:
    sign = "+" if pnl >= 0 else ""
    return f"{sign}{pnl:.2f}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_trading_hours(dt: Optional[datetime] = None) -> bool:
    """Return True if dt is within Mon-Fri London open to NY close (07:00-22:00 UTC)."""
    if dt is None:
        dt = utc_now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt.weekday() >= 5:
        return False
    t = dt.time()
    return time(LONDON_OPEN_HOUR, 0) <= t < time(NY_CLOSE_HOUR, NY_CLOSE_MINUTE)


def current_session(dt: Optional[datetime] = None) -> str:
    """Return trading session name based on UTC time."""
    if dt is None:
        dt = utc_now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt.weekday() >= 5:
        return "Off"

    t = dt.time()
    london = time(LONDON_OPEN_HOUR, 0) <= t < time(LONDON_CLOSE_HOUR, LONDON_CLOSE_MINUTE)
    ny = time(NY_OPEN_HOUR, 0) <= t < time(NY_CLOSE_HOUR, NY_CLOSE_MINUTE)

    if london and ny:
        return "Overlap"
    if london:
        return "London"
    if ny:
        return "NewYork"
    return "Off"


def calculate_pip_pnl(direction: str, entry: float, exit_price: float) -> float:
    """Return PnL in pips."""
    if direction == "BUY":
        return (exit_price - entry) / PIP_SIZE
    return (entry - exit_price) / PIP_SIZE


def calculate_gross_pnl(
    direction: str,
    entry: float,
    exit_price: float,
    lot_size: float,
) -> float:
    """Return gross PnL in USD (before spread/commission)."""
    pips = calculate_pip_pnl(direction, entry, exit_price)
    return pips * PIP_SIZE * lot_size * CONTRACT_SIZE


def clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, value))


def cleanup_dataframe_features(
    df,
    feature_columns: list[str] | None = None,
):
    """Replace inf with NaN and fill NaN with 0.0 in feature columns.

    Centralizes the NaN/Inf cleanup logic used across feature engineers.

    Args:
        df: pandas DataFrame to clean (modified in-place and returned)
        feature_columns: specific columns to clean. If None, cleans all numeric columns.

    Returns:
        The cleaned DataFrame
    """
    import numpy as np
    import pandas as pd

    if feature_columns is None:
        feature_columns = df.select_dtypes(include=["number"]).columns.tolist()
    else:
        feature_columns = [c for c in feature_columns if c in df.columns]

    if feature_columns:
        df[feature_columns] = df[feature_columns].replace([np.inf, -np.inf], np.nan)
        df[feature_columns] = df[feature_columns].fillna(0.0)

    return df
