"""Elliott Wave detection primitives.

Wave 1 scope:
    - ``find_extrema``: locate peaks and valleys via ``scipy.signal.find_peaks``
      with ATR-aware prominence and minimum spacing.
    - ``calculate_ewo``: Elliott Wave Oscillator (5/35 SMA difference on close).
      ``pandas_ta`` ships ``sma`` but no ``ewo`` helper, so we compute it
      directly. Returned series is index-aligned with the input frame and
      has ``NaN`` values at the start until the slow SMA fills.
    - ``WaveDetector``: high-level wrapper that fuses extrema + EWO into a
      time-ordered list of meaningful swings.

Threat-model mitigations (see plan T-14-01 / T-14-02):
    * Input data is validated for type, NaNs, and length bounds before any
      ``find_peaks`` call.
    * A hard cap (``MAX_INPUT_LENGTH``) prevents DoS on pathological frames.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from ai_engine.elliott_wave.models import ExtremumType, WavePoint


# Hard cap on the number of candles fed into the detector. This guards
# against accidental DoS on extreme frames; the standard EW analysis
# window for GoldBot is well under 10k candles.
MAX_INPUT_LENGTH: int = 100_000

# Minimum length required for ``find_peaks`` to do useful work. Below this
# value we return empty results rather than risk garbage extrema.
MIN_INPUT_LENGTH: int = 5


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_price_series(prices: Union[Sequence[float], np.ndarray, pd.Series]) -> np.ndarray:
    """Validate and normalise a price series to a float ``np.ndarray``.

    Raises:
        TypeError: if ``prices`` is not a sequence / array-like of numbers.
        ValueError: if NaNs are present, the array is too short, or it
            exceeds ``MAX_INPUT_LENGTH``.
    """
    if isinstance(prices, pd.Series):
        arr = prices.to_numpy(dtype=float, copy=False)
    elif isinstance(prices, np.ndarray):
        arr = prices.astype(float, copy=False)
    elif isinstance(prices, (list, tuple)):
        arr = np.asarray(prices, dtype=float)
    else:
        raise TypeError(
            f"prices must be a sequence, numpy array, or pandas Series; "
            f"got {type(prices).__name__}"
        )

    if arr.ndim != 1:
        raise ValueError(f"prices must be 1-dimensional; got shape {arr.shape}")

    if arr.size > MAX_INPUT_LENGTH:
        raise ValueError(
            f"prices length {arr.size} exceeds MAX_INPUT_LENGTH={MAX_INPUT_LENGTH}; "
            "pre-window the data before calling find_extrema."
        )

    if np.isnan(arr).any():
        raise ValueError("prices contain NaN values; clean the OHLCV frame first.")

    return arr


def _resolve_atr_scalar(atr: Union[float, Sequence[float], np.ndarray, pd.Series, None]) -> float:
    """Reduce an ATR input to a single positive scalar.

    Accepts:
        * ``None``: returns 0.0 (caller decides how to handle).
        * scalar: cast to ``float``.
        * series / array: takes the mean of the last 14 finite values,
          falling back to the global mean.
    """
    if atr is None:
        return 0.0

    if isinstance(atr, (int, float, np.floating)):
        val = float(atr)
        return val if np.isfinite(val) and val > 0 else 0.0

    if isinstance(atr, pd.Series):
        arr = atr.to_numpy(dtype=float, copy=False)
    elif isinstance(atr, np.ndarray):
        arr = atr.astype(float, copy=False)
    elif isinstance(atr, (list, tuple)):
        arr = np.asarray(atr, dtype=float)
    else:
        raise TypeError(
            f"atr must be a scalar, sequence, or pandas Series; got {type(atr).__name__}"
        )

    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return 0.0
    tail = finite[-14:] if finite.size >= 14 else finite
    val = float(tail.mean())
    return val if val > 0 else 0.0


# ---------------------------------------------------------------------------
# Public API: extrema detection
# ---------------------------------------------------------------------------


def find_extrema(
    prices: Union[Sequence[float], np.ndarray, pd.Series],
    atr: Union[float, Sequence[float], np.ndarray, pd.Series, None] = None,
    distance: int = 10,
    prominence_factor: float = 1.5,
    timestamps: Optional[Sequence] = None,
) -> List[WavePoint]:
    """Find local peaks and valleys in ``prices``.

    Peaks and valleys are detected via ``scipy.signal.find_peaks``. Valleys
    are found by inverting the price series. Both sets are merged and
    returned in chronological (index) order as :class:`WavePoint`s.

    Args:
        prices: 1-D price series (typically closing prices). Must be free
            of NaNs.
        atr: Optional ATR — used to scale the ``prominence`` threshold so
            small market noise is filtered out. If 0 / None, no prominence
            filter is applied beyond ``distance``.
        distance: Minimum number of bars between consecutive peaks (or
            consecutive valleys). Matches ``scipy.signal.find_peaks``.
        prominence_factor: Multiplier on ATR used as the prominence
            threshold. ``prominence = atr * prominence_factor``.
        timestamps: Optional iterable aligned with ``prices`` used to
            populate ``WavePoint.timestamp`` for downstream logging.

    Returns:
        Chronologically sorted list of :class:`WavePoint`s.
    """
    arr = _validate_price_series(prices)

    if arr.size < MIN_INPUT_LENGTH:
        return []

    atr_scalar = _resolve_atr_scalar(atr)
    prominence: Optional[float] = (
        atr_scalar * float(prominence_factor) if atr_scalar > 0 else None
    )

    distance = max(1, int(distance))

    peak_idx, _ = find_peaks(arr, distance=distance, prominence=prominence)
    valley_idx, _ = find_peaks(-arr, distance=distance, prominence=prominence)

    ts_list = list(timestamps) if timestamps is not None else None

    points: List[WavePoint] = []
    for idx in peak_idx:
        points.append(
            WavePoint(
                index=int(idx),
                price=float(arr[idx]),
                extremum_type=ExtremumType.PEAK,
                timestamp=_safe_ts(ts_list, idx),
            )
        )
    for idx in valley_idx:
        points.append(
            WavePoint(
                index=int(idx),
                price=float(arr[idx]),
                extremum_type=ExtremumType.VALLEY,
                timestamp=_safe_ts(ts_list, idx),
            )
        )

    points.sort(key=lambda p: p.index)
    return points


def _safe_ts(ts_list: Optional[List], idx: int) -> Optional[str]:
    if ts_list is None or idx >= len(ts_list):
        return None
    val = ts_list[idx]
    return str(val) if val is not None else None


# ---------------------------------------------------------------------------
# Public API: Elliott Wave Oscillator
# ---------------------------------------------------------------------------


def calculate_ewo(
    df: pd.DataFrame,
    fast: int = 5,
    slow: int = 35,
    column: str = "close",
) -> pd.Series:
    """Compute the Elliott Wave Oscillator on ``df[column]``.

    EWO is defined as ``SMA(close, fast) - SMA(close, slow)`` (Bill
    Williams). ``pandas_ta`` ships ``sma`` but not ``ewo``, so we compose
    the result manually. The output series is index-aligned with ``df``
    and contains ``NaN`` for the first ``slow - 1`` rows.

    Args:
        df: Source frame containing at least the ``column`` series.
        fast: Fast SMA length (default 5).
        slow: Slow SMA length (default 35).
        column: Column name to compute the oscillator on. Defaults to
            ``"close"``.

    Returns:
        ``pd.Series`` named ``EWO_<fast>_<slow>`` indexed like ``df``.

    Raises:
        TypeError: if ``df`` is not a ``pd.DataFrame``.
        KeyError: if ``column`` is missing from ``df``.
        ValueError: if ``fast``/``slow`` are non-positive or fast >= slow.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"df must be a pandas DataFrame; got {type(df).__name__}")
    if column not in df.columns:
        raise KeyError(f"df is missing required column '{column}'")
    if fast <= 0 or slow <= 0:
        raise ValueError(f"fast and slow must be positive; got fast={fast}, slow={slow}")
    if fast >= slow:
        raise ValueError(f"fast ({fast}) must be strictly less than slow ({slow})")

    close = df[column].astype(float)

    # Use pandas rolling SMA — equivalent to pandas_ta.sma but with no
    # external dependency on pandas_ta accessors which can vary between
    # versions.
    fast_sma = close.rolling(window=fast, min_periods=fast).mean()
    slow_sma = close.rolling(window=slow, min_periods=slow).mean()

    ewo = fast_sma - slow_sma
    ewo.name = f"EWO_{fast}_{slow}"
    return ewo


# ---------------------------------------------------------------------------
# WaveDetector
# ---------------------------------------------------------------------------


@dataclass
class WaveDetector:
    """High-level helper that fuses extrema and EWO into meaningful swings.

    The detector is intentionally stateless beyond its configuration —
    callers feed an OHLCV frame to :meth:`detect_swings` and receive a
    chronological list of :class:`WavePoint`s suitable for the rule
    engine.
    """

    distance: int = 10
    prominence_factor: float = 1.5
    ewo_fast: int = 5
    ewo_slow: int = 35
    ewo_filter: bool = False  # When True, drop extrema where |EWO| is below median.

    def detect_swings(
        self,
        df: pd.DataFrame,
        price_column: str = "close",
        atr: Union[float, Sequence[float], np.ndarray, pd.Series, None] = None,
    ) -> List[WavePoint]:
        """Return a chronologically ordered list of meaningful swings.

        Args:
            df: OHLCV-like frame.
            price_column: Column to use as the price series for extrema
                detection (default ``"close"``).
            atr: ATR series / scalar for prominence scaling. If omitted,
                a coarse internal estimate (rolling std) is used.
        """
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"df must be a pandas DataFrame; got {type(df).__name__}")
        if price_column not in df.columns:
            raise KeyError(f"df is missing required column '{price_column}'")
        if len(df) > MAX_INPUT_LENGTH:
            raise ValueError(
                f"df length {len(df)} exceeds MAX_INPUT_LENGTH={MAX_INPUT_LENGTH}; "
                "pre-window the data before calling detect_swings."
            )

        prices = df[price_column].to_numpy(dtype=float, copy=False)
        if np.isnan(prices).any():
            raise ValueError("price_column contains NaN values; clean the frame first.")

        atr_effective: Union[float, np.ndarray, None] = atr
        if atr_effective is None:
            # Fallback prominence: rolling stdev gives a noise-aware
            # estimate without requiring caller-supplied ATR.
            window = max(2, min(14, len(df) // 4))
            if window >= 2:
                atr_effective = (
                    df[price_column].rolling(window=window, min_periods=window).std().to_numpy()
                )

        timestamps: Optional[Iterable]
        if isinstance(df.index, pd.DatetimeIndex):
            timestamps = [ts.isoformat() for ts in df.index]
        else:
            timestamps = None

        points = find_extrema(
            prices,
            atr=atr_effective,
            distance=self.distance,
            prominence_factor=self.prominence_factor,
            timestamps=timestamps,
        )

        if self.ewo_filter and len(df) >= self.ewo_slow:
            ewo = calculate_ewo(df, fast=self.ewo_fast, slow=self.ewo_slow, column=price_column)
            ewo_abs = ewo.abs()
            median_strength = float(ewo_abs.median(skipna=True))
            if np.isfinite(median_strength) and median_strength > 0:
                points = [
                    p for p in points
                    if p.index < len(ewo_abs)
                    and np.isfinite(ewo_abs.iloc[p.index])
                    and ewo_abs.iloc[p.index] >= median_strength
                ]

        # Enforce strict alternation peak/valley/peak — if two same-type
        # extrema are adjacent, keep the more extreme one.
        return _enforce_alternation(points)


def _enforce_alternation(points: List[WavePoint]) -> List[WavePoint]:
    """Collapse consecutive same-type extrema, keeping the dominant one.

    Two adjacent peaks degenerate the wave count, so we keep the higher
    peak (resp. lower valley) and drop the other.
    """
    if not points:
        return points

    cleaned: List[WavePoint] = [points[0]]
    for p in points[1:]:
        last = cleaned[-1]
        if p.extremum_type == last.extremum_type:
            if p.extremum_type == ExtremumType.PEAK:
                if p.price > last.price:
                    cleaned[-1] = p
            else:  # VALLEY
                if p.price < last.price:
                    cleaned[-1] = p
        else:
            cleaned.append(p)
    return cleaned


__all__ = [
    "MAX_INPUT_LENGTH",
    "MIN_INPUT_LENGTH",
    "WaveDetector",
    "calculate_ewo",
    "find_extrema",
]
