"""Tests for the Phase 18 WindowFeatureCache disk cache."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ai_engine.training.feature_cache import (
    WindowFeatureCache,
    compute_data_hash,
    compute_feature_config_hash,
)


def _sample_frame(seed: int = 0, rows: int = 100) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [1.0 + (seed + i) * 0.01 for i in range(rows)],
            "high": [2.0 + (seed + i) * 0.01 for i in range(rows)],
            "low": [0.5 + (seed + i) * 0.01 for i in range(rows)],
            "close": [1.5 + (seed + i) * 0.01 for i in range(rows)],
            "volume": [100 + i for i in range(rows)],
        }
    )


def test_get_miss_returns_none(tmp_path: Path) -> None:
    cache = WindowFeatureCache(cache_dir=tmp_path)
    assert cache.get("missing") is None
    assert cache.stats["misses"] == 1


def test_put_then_get_roundtrips(tmp_path: Path) -> None:
    cache = WindowFeatureCache(cache_dir=tmp_path)
    df = _sample_frame()
    cache.put("key1", df)
    loaded = cache.get("key1")
    assert loaded is not None
    pd.testing.assert_frame_equal(
        loaded.reset_index(drop=True), df.reset_index(drop=True)
    )
    assert cache.stats["hits"] == 1


def test_get_or_compute_uses_cache_second_call(tmp_path: Path) -> None:
    cache = WindowFeatureCache(cache_dir=tmp_path)
    call_count = {"n": 0}

    def expensive() -> pd.DataFrame:
        call_count["n"] += 1
        return _sample_frame(seed=42)

    first = cache.get_or_compute("k", expensive)
    second = cache.get_or_compute("k", expensive)
    assert call_count["n"] == 1
    pd.testing.assert_frame_equal(
        first.reset_index(drop=True), second.reset_index(drop=True)
    )
    assert cache.hit_rate() == 0.5  # 1 hit, 1 miss


def test_lru_eviction_below_cap(tmp_path: Path) -> None:
    # Cap small enough that the third put forces eviction.
    cache = WindowFeatureCache(cache_dir=tmp_path, max_bytes=5_000)
    cache.put("a", _sample_frame(seed=1, rows=200))
    cache.put("b", _sample_frame(seed=2, rows=200))
    cache.put("c", _sample_frame(seed=3, rows=200))
    files = sorted(p.name for p in tmp_path.iterdir() if p.is_file())
    # At least one of a/b should have been evicted.
    assert len(files) < 3, f"expected eviction; still have {files}"


def test_compute_data_hash_stable_for_same_content() -> None:
    df1 = _sample_frame(seed=10)
    df2 = _sample_frame(seed=10)
    assert compute_data_hash(df1) == compute_data_hash(df2)


def test_compute_data_hash_changes_on_modification() -> None:
    df1 = _sample_frame(seed=10)
    df2 = _sample_frame(seed=11)
    assert compute_data_hash(df1) != compute_data_hash(df2)


def test_compute_feature_config_hash_ignores_dict_order() -> None:
    a = compute_feature_config_hash({"a": 1, "b": 2, "c": [3, 4]})
    b = compute_feature_config_hash({"c": [3, 4], "b": 2, "a": 1})
    assert a == b


def test_compute_feature_config_hash_changes_on_value_change() -> None:
    a = compute_feature_config_hash({"a": 1, "b": 2})
    b = compute_feature_config_hash({"a": 1, "b": 3})
    assert a != b


def test_clear_resets_stats_and_files(tmp_path: Path) -> None:
    cache = WindowFeatureCache(cache_dir=tmp_path)
    cache.put("k", _sample_frame())
    cache.get("k")
    assert cache.stats["hits"] == 1

    cache.clear()
    assert cache.stats["hits"] == 0
    assert cache.stats["misses"] == 0
    assert list(tmp_path.iterdir()) == []
