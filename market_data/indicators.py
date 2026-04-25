"""Technical indicators for Gold trading using pandas-ta."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)
_PANDAS = None
_PANDAS_TA = None


def _get_indicator_libs():
    """Import indicator libraries lazily to reduce first-start latency."""
    global _PANDAS, _PANDAS_TA
    if _PANDAS is None or _PANDAS_TA is None:
        import pandas as pd
        import pandas_ta as ta

        _PANDAS = pd
        _PANDAS_TA = ta
    return _PANDAS, _PANDAS_TA


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all technical indicators on a candle DataFrame.

    Expected columns: timestamp, open, high, low, close, volume
    Returns DataFrame with all indicator columns added.
    """
    if len(df) < 50:
        logger.warning("Only %d candles — some indicators may be NaN", len(df))

    pd, ta = _get_indicator_libs()

    # -- Trend Indicators ---------------------------------------------------

    # EMA (Exponential Moving Average)
    df["ema_9"] = ta.ema(df["close"], length=9)
    df["ema_21"] = ta.ema(df["close"], length=21)
    df["ema_50"] = ta.ema(df["close"], length=50)
    df["ema_200"] = ta.ema(df["close"], length=200)

    # SMA
    df["sma_20"] = ta.sma(df["close"], length=20)
    df["sma_50"] = ta.sma(df["close"], length=50)

    # MACD
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd is not None:
        df["macd"] = macd.iloc[:, 0]
        df["macd_histogram"] = macd.iloc[:, 1]
        df["macd_signal"] = macd.iloc[:, 2]

    # ADX (Average Directional Index)
    adx = ta.adx(df["high"], df["low"], df["close"], length=14)
    if adx is not None:
        df["adx"] = adx.iloc[:, 0]
        df["di_plus"] = adx.iloc[:, 1]
        df["di_minus"] = adx.iloc[:, 2]

    # -- Momentum Indicators ------------------------------------------------

    # RSI (Relative Strength Index)
    df["rsi_14"] = ta.rsi(df["close"], length=14)

    # Stochastic Oscillator
    stoch = ta.stoch(df["high"], df["low"], df["close"], k=14, d=3)
    if stoch is not None:
        df["stoch_k"] = stoch.iloc[:, 0]
        df["stoch_d"] = stoch.iloc[:, 1]

    # CCI (Commodity Channel Index) — good for Gold
    df["cci_20"] = ta.cci(df["high"], df["low"], df["close"], length=20)

    # Williams %R
    df["willr_14"] = ta.willr(df["high"], df["low"], df["close"], length=14)

    # -- Volatility Indicators ----------------------------------------------

    # Bollinger Bands
    # pandas_ta.bbands returns columns in order: [BBL, BBM, BBU, BBB, BBP]
    # i.e. Lower, Middle, Upper, Bandwidth, Percent.
    bb = ta.bbands(df["close"], length=20, std=2)
    if bb is not None:
        df["bb_lower"] = bb.iloc[:, 0]
        df["bb_middle"] = bb.iloc[:, 1]
        df["bb_upper"] = bb.iloc[:, 2]
        df["bb_bandwidth"] = bb.iloc[:, 3] if bb.shape[1] > 3 else None
        df["bb_percent"] = bb.iloc[:, 4] if bb.shape[1] > 4 else None

    # ATR (Average True Range)
    df["atr_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)

    # -- Volume Indicators --------------------------------------------------

    if df["volume"].sum() > 0:
        # OBV (On Balance Volume)
        df["obv"] = ta.obv(df["close"], df["volume"])

        # VWAP requires a sorted DatetimeIndex
        had_datetime_index = isinstance(df.index, pd.DatetimeIndex)
        if not had_datetime_index and "timestamp" in df.columns:
            original_index = df.index
            df.index = pd.to_datetime(df["timestamp"], utc=True)
            df = df.sort_index()
            try:
                df["vwap"] = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
            except Exception as e:
                logger.warning("VWAP calculation failed: %s", e)
                df["vwap"] = float("nan")
            df.index = original_index
        else:
            if not df.index.is_monotonic_increasing:
                df = df.sort_index()
            try:
                df["vwap"] = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
            except Exception as e:
                logger.warning("VWAP calculation failed: %s", e)
                df["vwap"] = float("nan")

    # -- Derived Signals ----------------------------------------------------

    # EMA Crossover signals
    df["ema_cross_9_21"] = (df["ema_9"].astype(float) > df["ema_21"].astype(float)).astype(int)
    df["ema_cross_21_50"] = (df["ema_21"].astype(float) > df["ema_50"].astype(float)).astype(int)

    # RSI zones
    df["rsi_oversold"] = (df["rsi_14"].astype(float) < 30).astype(int)
    df["rsi_overbought"] = (df["rsi_14"].astype(float) > 70).astype(int)

    # Trend strength
    if "adx" in df.columns:
        df["strong_trend"] = (df["adx"].astype(float) > 25).astype(int)

    return df


def get_indicator_summary(df: pd.DataFrame) -> dict:
    """Get a summary of the latest indicator values."""
    pd, _ = _get_indicator_libs()

    if df.empty:
        return {}

    last = df.iloc[-1]
    summary = {}

    indicator_cols = [
        "ema_9", "ema_21", "ema_50", "sma_20",
        "rsi_14", "macd", "macd_signal", "macd_histogram",
        "adx", "di_plus", "di_minus",
        "bb_upper", "bb_middle", "bb_lower",
        "atr_14", "stoch_k", "stoch_d", "cci_20",
    ]

    for col in indicator_cols:
        if col in last.index and pd.notna(last[col]):
            summary[col] = round(float(last[col]), 4)

    # Add trend assessment
    if "ema_9" in summary and "ema_21" in summary:
        summary["short_trend"] = "BULLISH" if summary["ema_9"] > summary["ema_21"] else "BEARISH"

    if "rsi_14" in summary:
        rsi = summary["rsi_14"]
        if rsi > 70:
            summary["rsi_zone"] = "OVERBOUGHT"
        elif rsi < 30:
            summary["rsi_zone"] = "OVERSOLD"
        else:
            summary["rsi_zone"] = "NEUTRAL"

    return summary
