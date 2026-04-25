"""
Tests for model versioning utilities.

Tests create_version_dir, write_version_json, update_production_pointer,
and cleanup_old_versions from ai_engine.training.model_versioning.
"""

import json
import os
import time


from ai_engine.training.model_versioning import (
    cleanup_old_versions,
    create_version_dir,
    update_production_pointer,
    write_version_json,
)


class TestCreateVersionDir:
    """Tests for create_version_dir."""

    def test_create_version_dir_first(self, tmp_path):
        """Creates v001 directory when none exist."""
        version_dir = create_version_dir(str(tmp_path))
        dirname = os.path.basename(version_dir)
        assert dirname.startswith("v001_")
        assert os.path.isdir(version_dir)

    def test_create_version_dir_sequential(self, tmp_path):
        """Creates v002 when v001 exists."""
        v1 = create_version_dir(str(tmp_path))
        # Small delay to avoid timestamp collision
        time.sleep(0.01)
        v2 = create_version_dir(str(tmp_path))
        v1_name = os.path.basename(v1)
        v2_name = os.path.basename(v2)
        assert v1_name.startswith("v001_")
        assert v2_name.startswith("v002_")
        assert os.path.isdir(v1)
        assert os.path.isdir(v2)


class TestWriteVersionJson:
    """Tests for write_version_json."""

    def test_write_version_json(self, tmp_path):
        """Writes valid JSON with all required fields."""
        version_dir = str(tmp_path / "v001_20260306_143022")
        os.makedirs(version_dir)

        version_data = {
            "training_date": "2026-03-06T14:30:22",
            "timeframe": "5m",
            "n_samples_total": 12000,
            "n_features_original": 60,
            "n_features_selected": 14,
            "feature_names": ["rsi_14", "ema_9"],
            "label_params": {"tp_pips": 1500.0, "sl_pips": 800.0},
            "training_duration_seconds": 45.2,
            "version": "v001",
            "version_dir": "v001_20260306_143022",
            "data_range": {"n_candles": 12000, "months_of_data": 14.2},
            "walk_forward": {
                "n_windows": 3,
                "window_type": "expanding",
                "purge_gap_candles": 60,
                "windows": [
                    {
                        "window_id": 0,
                        "train_samples": 2000,
                        "test_samples": 500,
                        "metrics": {
                            "xgboost": {
                                "accuracy": 0.55,
                                "f1": 0.52,
                                "win_rate": 0.58,
                                "profit_factor": 1.4,
                                "expectancy": 2.3,
                                "n_trades": 100,
                            },
                            "lightgbm": {
                                "accuracy": 0.57,
                                "f1": 0.54,
                                "win_rate": 0.60,
                                "profit_factor": 1.6,
                                "expectancy": 3.1,
                                "n_trades": 120,
                            },
                        },
                    }
                ],
            },
            "aggregate_metrics": {
                "xgboost": {
                    "win_rate": 0.56,
                    "profit_factor": 1.35,
                    "expectancy": 1.8,
                    "n_trades": 450,
                },
                "lightgbm": {
                    "win_rate": 0.59,
                    "profit_factor": 1.52,
                    "expectancy": 2.5,
                    "n_trades": 520,
                },
            },
            "xgboost_accuracy": 0.55,
            "xgboost_f1": 0.52,
        }

        json_path = write_version_json(version_dir, version_data)
        assert os.path.exists(json_path)

        with open(json_path, "r") as f:
            loaded = json.load(f)

        assert loaded["version"] == "v001"
        assert loaded["training_date"] == "2026-03-06T14:30:22"
        assert loaded["walk_forward"]["n_windows"] == 3
        assert loaded["aggregate_metrics"]["xgboost"]["win_rate"] == 0.56
        assert loaded["n_features_original"] == 60
        assert loaded["feature_names"] == ["rsi_14", "ema_9"]


class TestUpdateProductionPointer:
    """Tests for update_production_pointer."""

    def test_update_production_pointer(self, tmp_path):
        """Creates production.json and copies model files to base dir."""
        base_dir = str(tmp_path)
        version_dir = os.path.join(base_dir, "v001_20260306_143022")
        os.makedirs(version_dir)

        # Create fake model files in version dir
        for filename in [
            "xgboost_gold.pkl",
            "lightgbm_gold.pkl",
            "feature_scaler.pkl",
        ]:
            with open(os.path.join(version_dir, filename), "wb") as f:
                f.write(b"fake model data for " + filename.encode())

        # Create version.json in version dir
        version_data = {"version": "v001", "training_date": "2026-03-06"}
        with open(os.path.join(version_dir, "version.json"), "w") as f:
            json.dump(version_data, f)

        update_production_pointer(base_dir, version_dir)

        # Check production.json was created
        pointer_path = os.path.join(base_dir, "production.json")
        assert os.path.exists(pointer_path)
        with open(pointer_path, "r") as f:
            pointer = json.load(f)
        assert pointer["version_dir"] == "v001_20260306_143022"
        assert "updated" in pointer
        assert "path" in pointer

        # Check model files were copied to base dir
        for filename in [
            "xgboost_gold.pkl",
            "lightgbm_gold.pkl",
            "feature_scaler.pkl",
        ]:
            assert os.path.exists(os.path.join(base_dir, filename))

        # Check version.json was copied as model_metadata.json
        meta_path = os.path.join(base_dir, "model_metadata.json")
        assert os.path.exists(meta_path)
        with open(meta_path, "r") as f:
            meta = json.load(f)
        assert meta["version"] == "v001"


class TestCleanupOldVersions:
    """Tests for cleanup_old_versions."""

    def test_cleanup_old_versions(self, tmp_path):
        """Keeps 5 most recent, deletes older ones."""
        base_dir = str(tmp_path)
        # Create 7 version directories
        for i in range(1, 8):
            os.makedirs(os.path.join(base_dir, f"v{i:03d}_20260306_14000{i}"))

        deleted = cleanup_old_versions(base_dir, keep=5)

        assert len(deleted) == 2
        assert "v001_20260306_140001" in deleted
        assert "v002_20260306_140002" in deleted

        # Verify remaining directories
        remaining = [
            d
            for d in os.listdir(base_dir)
            if os.path.isdir(os.path.join(base_dir, d))
        ]
        assert len(remaining) == 5
        assert "v003_20260306_140003" in remaining
        assert "v007_20260306_140007" in remaining

    def test_cleanup_with_fewer_than_keep(self, tmp_path):
        """No deletion when < 5 versions exist."""
        base_dir = str(tmp_path)
        for i in range(1, 4):
            os.makedirs(os.path.join(base_dir, f"v{i:03d}_20260306_14000{i}"))

        deleted = cleanup_old_versions(base_dir, keep=5)

        assert len(deleted) == 0
        remaining = [
            d
            for d in os.listdir(base_dir)
            if os.path.isdir(os.path.join(base_dir, d))
        ]
        assert len(remaining) == 3


class TestVersionJsonExtendsMetadata:
    """Tests that version.json contains all fields from old model_metadata.json."""

    def test_version_json_extends_metadata(self, tmp_path):
        """version.json contains all fields from old model_metadata.json format."""
        version_dir = str(tmp_path / "v001_test")
        os.makedirs(version_dir)

        # These are the fields that existed in the old model_metadata.json
        old_metadata_fields = [
            "training_date",
            "timeframe",
            "n_samples_total",
            "n_features_original",
            "n_features_selected",
            "feature_names",
            "label_params",
            "training_duration_seconds",
        ]

        version_data = {
            # Old metadata fields
            "training_date": "2026-03-06T14:30:22",
            "timeframe": "5m",
            "n_samples_total": 12000,
            "n_features_original": 60,
            "n_features_selected": 14,
            "feature_names": ["rsi_14"],
            "label_params": {"tp_pips": 1500.0},
            "training_duration_seconds": 45.2,
            # New version fields
            "version": "v001",
            "version_dir": "v001_test",
            "data_range": {"n_candles": 12000},
            "walk_forward": {"n_windows": 3, "window_type": "expanding"},
            "aggregate_metrics": {"xgboost": {"win_rate": 0.56}},
            # Backward-compat flat metrics
            "xgboost_accuracy": 0.55,
            "xgboost_f1": 0.52,
        }

        write_version_json(version_dir, version_data)

        with open(os.path.join(version_dir, "version.json"), "r") as f:
            loaded = json.load(f)

        # Verify ALL old metadata fields are present
        for field in old_metadata_fields:
            assert field in loaded, f"Missing old metadata field: {field}"

        # Verify NEW fields are also present
        assert "version" in loaded
        assert "version_dir" in loaded
        assert "data_range" in loaded
        assert "walk_forward" in loaded
        assert "aggregate_metrics" in loaded

        # Verify backward-compat flat metrics
        assert "xgboost_accuracy" in loaded
        assert "xgboost_f1" in loaded
