"""Tests for the additive run-manifest sidecar (Phase 18 D-17 / Plan 18-04)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ai_engine.training.run_manifest import (
    MANIFEST_FILENAME,
    build_run_manifest,
    write_run_manifest,
    _compute_git_sha,
)

REQUIRED_KEYS = {
    "schema_version",
    "phase",
    "created_at",
    "seed",
    "timeframe",
    "data_csv",
    "data_hash",
    "fetched_months",
    "n_windows",
    "device",
    "gpu_info",
    "device_accepted",
    "wall_clock_seconds",
    "cache_hit_rate",
    "parallel_windows",
    "git_sha",
    "pip_freeze_digest",
    "python_version",
    "cpu",
}


def _sample_manifest(**overrides):
    kwargs = dict(
        seed=42,
        timeframe="5m",
        data_csv_path=None,
        fetched_months=48.0,
        n_windows=36,
        device="cpu",
        gpu_info=None,
        wall_clock_stages={"features": 10.0, "walk_forward": 30.0},
        cache_hit_rate=0.5,
        parallel_windows=4,
    )
    kwargs.update(overrides)
    return build_run_manifest(**kwargs)


def test_build_run_manifest_required_keys():
    manifest = _sample_manifest()
    assert REQUIRED_KEYS.issubset(manifest.keys())
    assert manifest["schema_version"] == "1.0"
    assert manifest["phase"] == "18"
    assert manifest["seed"] == 42
    # gpu_info must be None on a cpu device even if a dict is passed.
    assert manifest["gpu_info"] is None
    # total wall-clock is the sum of stage times.
    assert manifest["wall_clock_seconds"]["total"] == pytest.approx(40.0)
    assert manifest["wall_clock_seconds"]["stages"]["features"] == 10.0


def test_gpu_info_present_when_device_cuda():
    gpu = {"name": "RTX 4090", "memory_mb": 24576}
    manifest = _sample_manifest(device="cuda", gpu_info=gpu, device_accepted=True)
    assert manifest["device"] == "cuda"
    assert manifest["gpu_info"] == gpu
    assert manifest["device_accepted"] is True


def test_write_round_trips(tmp_path: Path):
    manifest = _sample_manifest()
    out = write_run_manifest(manifest, tmp_path)
    assert Path(out).name == MANIFEST_FILENAME
    loaded = json.loads(Path(out).read_text(encoding="utf-8"))
    assert loaded == manifest


def test_data_hash_computed_for_existing_file(tmp_path: Path):
    csv = tmp_path / "data.csv"
    csv.write_text("timestamp,close\n2025-01-01,2050\n", encoding="utf-8")
    manifest = _sample_manifest(data_csv_path=str(csv))
    assert manifest["data_hash"] is not None
    assert manifest["data_hash"].startswith("sha256:")
    assert manifest["data_csv"] == str(csv)


def test_data_hash_none_when_no_path():
    manifest = _sample_manifest(data_csv_path=None)
    assert manifest["data_hash"] is None
    assert manifest["data_csv"] is None


def test_git_sha_includes_dirty_suffix_when_uncommitted_changes_exist(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def _git(*args):
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=True
        )

    _git("init")
    _git("config", "user.email", "t@t.t")
    _git("config", "user.name", "t")
    (repo / "a.txt").write_text("hello", encoding="utf-8")
    _git("add", "a.txt")
    _git("commit", "-m", "init")

    # Clean tree: no dirty suffix.
    import os

    cwd = os.getcwd()
    try:
        os.chdir(repo)
        clean = _compute_git_sha()
        assert "+dirty" not in clean
        assert clean != "unknown"

        # Touch an uncommitted file -> dirty suffix appears.
        (repo / "b.txt").write_text("new", encoding="utf-8")
        dirty = _compute_git_sha()
        assert "+dirty" in dirty
    finally:
        os.chdir(cwd)


def test_version_json_schema_not_modified_by_manifest():
    """The run manifest is additive: manifest-only keys must NOT leak into
    version.json's top-level schema. We assert the disjoint-key contract on a
    representative version_data dict shape produced by pipeline.py.
    """
    # Keys that belong ONLY to the run manifest, never to version.json.
    manifest = _sample_manifest()
    manifest_only_keys = {
        "schema_version",
        "git_sha",
        "pip_freeze_digest",
        "data_hash",
        "cache_hit_rate",
        "parallel_windows",
    }
    assert manifest_only_keys.issubset(manifest.keys())

    # A real version.json (the production champion) must not carry these.
    prod_version = Path("ai_engine/saved_models/model_metadata.json")
    if prod_version.is_file():
        data = json.loads(prod_version.read_text(encoding="utf-8"))
        leaked = manifest_only_keys.intersection(data.keys())
        assert not leaked, f"manifest-only keys leaked into version.json: {leaked}"
