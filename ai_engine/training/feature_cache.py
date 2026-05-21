"""LRU disk cache for engineered feature matrices.

Phase 18 — efficiency layer. Provides a content-addressed cache so a second
training run on the same data + same feature configuration can skip the
~minute-long feature-engineering step entirely.

**TRAIN-02 compliance:** this cache stores *engineered features*, not
*scaled features*. The per-window ``FeatureScaler`` is still fit fresh on
each window's training slice — that rule from Phase 2 is preserved.
Cache hits only short-circuit the deterministic feature-engineering
pipeline, which is leakage-safe because feature engineering is a pure
function of OHLCV history (plus the static feature config).

Storage format: parquet (small, portable, columnar). Falls back to pickle
if the host pandas install lacks a parquet engine.

Eviction: simple LRU by access time. When ``put()`` would push the cache
size past ``max_bytes``, the least-recently-accessed entries are deleted
until the cache fits again.

**Status (Phase 18-03):** module ships standalone with full test coverage.
Wiring into ``walk_forward.WalkForwardValidator`` / ``trainer.ModelTrainer``
is deferred to a follow-up plan — the cache can be exercised externally
today via the public helpers ``compute_data_hash``, ``compute_feature_config_hash``,
``WindowFeatureCache.get_or_compute``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import time
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def compute_data_hash(df: pd.DataFrame) -> str:
    """SHA256 of the dataframe contents as a stable cache-key component.

    Stable across runs as long as values + column order are unchanged.
    Index is reset before hashing so equivalent frames with different
    index labels hash identically.
    """
    payload = df.reset_index(drop=True).to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compute_feature_config_hash(config: dict[str, Any]) -> str:
    """SHA256 over sorted JSON of the feature-engineering configuration.

    Order-insensitive — ``{"a": 1, "b": 2}`` and ``{"b": 2, "a": 1}`` hash
    identically. Non-JSON-serialisable values fall back to ``repr()``.
    """
    serialised = json.dumps(config, sort_keys=True, default=repr).encode("utf-8")
    return hashlib.sha256(serialised).hexdigest()


def _build_key(
    data_hash: str,
    feature_config_hash: str,
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
) -> str:
    if window_start is None and window_end is None:
        return f"{data_hash}_{feature_config_hash}"
    return f"{data_hash}_{feature_config_hash}_{window_start}_{window_end}"


class WindowFeatureCache:
    """LRU disk cache for feature matrices.

    Renamed from ``FeatureCache`` to avoid collision with the runtime
    in-memory tick cache in ``ai_engine.features.feature_engineer``.
    """

    DEFAULT_CACHE_DIR = Path("data") / ".feature_cache"
    DEFAULT_MAX_BYTES = 4 * 1024**3  # 4 GiB

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        max_bytes: int | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else self.DEFAULT_CACHE_DIR
        self.max_bytes = max_bytes if max_bytes is not None else self.DEFAULT_MAX_BYTES
        self._hits = 0
        self._misses = 0

    # ----- core API -------------------------------------------------------

    def get(self, key: str) -> pd.DataFrame | None:
        """Return cached DataFrame for ``key`` or ``None`` on miss."""
        path = self._path_for(key)
        if not path.exists():
            self._misses += 1
            return None
        try:
            if path.suffix == ".parquet":
                df = pd.read_parquet(path)
            else:
                with open(path, "rb") as handle:
                    df = pickle.load(handle)
        except Exception as exc:  # corruption — treat as miss
            logger.warning("WindowFeatureCache.get(%s) failed: %s", key, exc)
            self._misses += 1
            return None
        # Bump access time so LRU eviction keeps it warm.
        try:
            os.utime(path, None)
        except OSError:
            pass
        self._hits += 1
        return df

    def put(self, key: str, df: pd.DataFrame) -> None:
        """Persist ``df`` under ``key`` and evict if total bytes exceed cap."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._preferred_path(key)
        try:
            df.to_parquet(path)
        except Exception as exc:
            logger.info(
                "WindowFeatureCache parquet write failed (%s) — falling back to pickle",
                exc,
            )
            path = self.cache_dir / f"{key}.pkl"
            with open(path, "wb") as handle:
                pickle.dump(df, handle, protocol=pickle.HIGHEST_PROTOCOL)
        self._evict_if_needed()

    def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], pd.DataFrame],
    ) -> pd.DataFrame:
        cached = self.get(key)
        if cached is not None:
            return cached
        computed = compute_fn()
        self.put(key, computed)
        return computed

    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total else 0.0

    @property
    def stats(self) -> dict[str, int | float]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate(),
            "total_bytes": self._total_bytes(),
            "max_bytes": self.max_bytes,
        }

    def clear(self) -> None:
        if not self.cache_dir.exists():
            return
        for path in self.cache_dir.iterdir():
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("WindowFeatureCache.clear: %s -> %s", path, exc)
        self._hits = 0
        self._misses = 0

    # ----- internals ------------------------------------------------------

    def _preferred_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.parquet"

    def _path_for(self, key: str) -> Path:
        # Try parquet first, then pickle fallback.
        parquet = self.cache_dir / f"{key}.parquet"
        if parquet.exists():
            return parquet
        return self.cache_dir / f"{key}.pkl"

    def _total_bytes(self) -> int:
        if not self.cache_dir.exists():
            return 0
        return sum(
            path.stat().st_size
            for path in self.cache_dir.iterdir()
            if path.is_file()
        )

    def _evict_if_needed(self) -> None:
        if self.max_bytes <= 0:
            return
        total = self._total_bytes()
        if total <= self.max_bytes:
            return
        entries = sorted(
            (p for p in self.cache_dir.iterdir() if p.is_file()),
            key=lambda p: p.stat().st_atime,
        )
        for path in entries:
            try:
                total -= path.stat().st_size
                path.unlink()
                logger.info("WindowFeatureCache evicted %s", path.name)
            except OSError as exc:
                logger.warning("WindowFeatureCache eviction failed: %s", exc)
                continue
            if total <= self.max_bytes:
                break
        # Reset access-time bumps that confuse the next pass.
        time.sleep(0)
