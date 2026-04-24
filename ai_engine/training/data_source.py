"""
Datenquellen-Adapter fuer AI-Training.

Unterstuetzt:
- DB-Quelle (PostgreSQL candles Tabelle)
- Datei-Quelle (CSV/Parquet/JSON)
- Auto-Modus (DB -> Datei-Fallback)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from sqlalchemy import select, text

from database.connection import get_engine, get_session
from database.models import Candle
from database.repositories.candle_repo import CandleRepository

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
CORE_INDICATOR_COLUMNS = ["rsi_14", "ema_9", "ema_21", "atr_14", "stoch_k", "stoch_d"]


class DataSourceError(RuntimeError):
    """Fehler beim Laden oder Validieren von Trainingsdaten."""


@dataclass
class DataLoadResult:
    """Ergebnisobjekt fuer geladene Daten."""

    source: str
    timeframe: str
    dataframe: pd.DataFrame
    details: Dict[str, Any]


async def check_db_connection() -> None:
    """Prueft, ob die DB erreichbar ist."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("select 1"))
    except Exception as exc:
        raise DataSourceError(f"DB nicht erreichbar: {exc}") from exc


async def get_db_candle_counts() -> Dict[str, int]:
    """Liefert Candle-Anzahl pro Timeframe aus der DB."""
    await check_db_connection()

    query = text(
        """
        select timeframe, count(*) as n
        from candles
        group by timeframe
        order by timeframe
        """
    )
    async with get_engine().connect() as conn:
        result = await conn.execute(query)
        rows = result.fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


async def load_from_db(
    timeframe: str = "5m",
    count: Optional[int] = None,
    with_indicators: bool = True,
) -> DataLoadResult:
    """
    Laedt Candle-Daten aus der DB.

    Args:
        timeframe: Ziel-Timeframe (z. B. 5m)
        count: Optionales Limit auf letzte N Kerzen
        with_indicators: Technische Indikatoren berechnen, falls nicht vorhanden
    """
    await check_db_connection()

    async with get_session() as session:
        repo = CandleRepository(session)
        if count is not None:
            candles = await repo.get_latest(timeframe=timeframe, count=int(count))
        else:
            stmt = (
                select(Candle)
                .where(Candle.timeframe == timeframe)
                .order_by(Candle.timestamp.asc())
            )
            result = await session.execute(stmt)
            candles = result.scalars().all()

    rows = [
        {
            "timestamp": c.timestamp,
            "open": float(c.open),
            "high": float(c.high),
            "low": float(c.low),
            "close": float(c.close),
            "volume": float(c.volume) if c.volume is not None else 0.0,
        }
        for c in candles
    ]
    df = pd.DataFrame(rows)
    df = _normalize_dataframe(df, with_indicators=with_indicators)
    details = summarize_dataframe(df, source="db", timeframe=timeframe)
    return DataLoadResult(source="db", timeframe=timeframe, dataframe=df, details=details)


def load_from_file(
    file_path: str,
    timeframe: str = "5m",
    with_indicators: bool = True,
) -> DataLoadResult:
    """
    Laedt Candle-Daten aus Datei.

    Unterstuetzte Formate:
    - .csv
    - .parquet
    - .json (records oder array)
    """
    path = Path(file_path)
    if not path.exists():
        raise DataSourceError(f"Datei nicht gefunden: {file_path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix == ".parquet":
        df = pd.read_parquet(path)
    elif suffix == ".json":
        df = pd.read_json(path)
    else:
        raise DataSourceError(
            f"Nicht unterstuetztes Dateiformat '{suffix}'. Erlaubt: .csv, .parquet, .json"
        )

    if "timeframe" in df.columns:
        filtered = df[df["timeframe"].astype(str) == timeframe].copy()
        if filtered.empty:
            available = sorted(df["timeframe"].dropna().astype(str).unique().tolist())
            raise DataSourceError(
                f"Keine Daten fuer Timeframe '{timeframe}' in Datei gefunden. "
                f"Verfuegbar: {available or ['<leer>']}"
            )
        df = filtered

    df = _normalize_dataframe(df, with_indicators=with_indicators)
    details = summarize_dataframe(df, source="file", timeframe=timeframe)
    details["file_path"] = str(path)
    return DataLoadResult(source="file", timeframe=timeframe, dataframe=df, details=details)


async def load_auto(
    timeframe: str = "5m",
    count: Optional[int] = None,
    file_path: Optional[str] = None,
    with_indicators: bool = True,
) -> DataLoadResult:
    """
    Auto-Ladepfad:
    1) Versuche DB
    2) Falls DB nicht nutzbar: Datei-Fallback
    """
    errors = []

    try:
        counts = await get_db_candle_counts()
        n = int(counts.get(timeframe, 0))
        if n > 0:
            logger.info("Auto-Quelle: nutze DB (%s: %d Kerzen)", timeframe, n)
            return await load_from_db(
                timeframe=timeframe,
                count=count,
                with_indicators=with_indicators,
            )
        errors.append(f"DB enthaelt keine Kerzen fuer Timeframe '{timeframe}'")
    except Exception as exc:
        errors.append(str(exc))

    if file_path:
        logger.info("Auto-Quelle: nutze Datei-Fallback (%s)", file_path)
        return load_from_file(
            file_path=file_path,
            timeframe=timeframe,
            with_indicators=with_indicators,
        )

    error_text = "; ".join(errors) if errors else "Keine Datenquelle verfuegbar"
    raise DataSourceError(
        f"Auto-Laden fehlgeschlagen: {error_text}. "
        "Gib --file-path an oder stelle DB-Daten bereit."
    )


def summarize_dataframe(df: pd.DataFrame, source: str, timeframe: str) -> Dict[str, Any]:
    """Erzeugt eine kompakte Datensatz-Zusammenfassung."""
    rows = int(len(df))
    start_ts = _to_iso(df["timestamp"].iloc[0]) if rows > 0 else None
    end_ts = _to_iso(df["timestamp"].iloc[-1]) if rows > 0 else None
    return {
        "source": source,
        "timeframe": timeframe,
        "rows": rows,
        "start_timestamp": start_ts,
        "end_timestamp": end_ts,
        "columns": list(df.columns),
    }


def ensure_min_rows(df: pd.DataFrame, min_rows: int) -> None:
    """Validiert Mindestanzahl an Zeilen fuer Training."""
    if len(df) < int(min_rows):
        raise DataSourceError(
            f"Zu wenige Daten fuer Training: {len(df)} Zeilen (min. {min_rows})."
        )


def normalize_training_dataframe(df: pd.DataFrame, with_indicators: bool = True) -> pd.DataFrame:
    """Public wrapper fuer die interne DataFrame-Normalisierung."""
    return _normalize_dataframe(df, with_indicators=with_indicators)


def _normalize_dataframe(df: pd.DataFrame, with_indicators: bool) -> pd.DataFrame:
    """Normalisiert und validiert Candle-Daten."""
    out = df.copy()

    if "timestamp" not in out.columns:
        if isinstance(out.index, pd.DatetimeIndex):
            out["timestamp"] = out.index
        else:
            raise DataSourceError("Pflichtspalte 'timestamp' fehlt.")

    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    out = out.dropna(subset=["timestamp"]).copy()

    for col in ["open", "high", "low", "close", "volume"]:
        if col not in out.columns:
            raise DataSourceError(f"Pflichtspalte '{col}' fehlt.")
        out[col] = pd.to_numeric(out[col], errors="coerce")

    invalid_ohlc_nan = out[["open", "high", "low", "close"]].isna().any(axis=1)
    if invalid_ohlc_nan.any():
        raise DataSourceError(
            f"Ungueltige OHLC-Daten: {int(invalid_ohlc_nan.sum())} Zeile(n) mit NaN-Werten."
        )
    out["volume"] = out["volume"].fillna(0.0)

    # OHLC-Konsistenz
    invalid_mask = (out["high"] < out["low"]) | (out["open"] < out["low"]) | (out["open"] > out["high"]) | (
        out["close"] < out["low"]
    ) | (out["close"] > out["high"])
    if invalid_mask.any():
        raise DataSourceError(
            f"Ungueltige OHLC-Beziehung in {int(invalid_mask.sum())} Zeile(n) erkannt."
        )

    out = out.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
    out.index = pd.to_datetime(out["timestamp"], utc=True)

    if with_indicators and not _has_core_indicators(out):
        try:
            from market_data.indicators import calculate_indicators

            out = calculate_indicators(out)
        except Exception as exc:
            logger.warning("Indikator-Berechnung fehlgeschlagen: %s", exc)

    return out


def _has_core_indicators(df: pd.DataFrame) -> bool:
    return all(col in df.columns for col in CORE_INDICATOR_COLUMNS)


def _to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        ts = pd.to_datetime(value, utc=True, errors="coerce")
    except Exception:
        return None
    if pd.isna(ts):
        return None
    return ts.isoformat()
