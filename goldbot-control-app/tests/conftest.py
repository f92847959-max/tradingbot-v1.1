"""Pytest fixtures for control app tests."""

from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Provide TestClient with isolated SQLite file per test."""
    db_path = tmp_path / "control_app_test.db"
    source_db_path = tmp_path / "gold_trader_test.db"
    with sqlite3.connect(source_db_path) as connection:
        connection.execute(
            """
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY,
                deal_id TEXT,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                direction TEXT NOT NULL,
                status TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                exit_price REAL,
                lot_size REAL,
                net_pnl REAL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO trades (
                id, deal_id, opened_at, closed_at, direction, status,
                entry_price, stop_loss, take_profit, exit_price, lot_size, net_pnl
            ) VALUES (
                1, 'D-TEST-1', '2026-03-02T12:00:00+00:00', NULL, 'BUY', 'OPEN',
                2050.5, 2046.0, 2058.5, NULL, 0.5, NULL
            )
            """
        )
        connection.commit()

    monkeypatch.setenv("CONTROL_APP_DB_PATH", str(db_path))
    monkeypatch.setenv("CONTROL_APP_SOURCE_DB_PATH", str(source_db_path))
    monkeypatch.setenv("CONTROL_APP_RETENTION_DAYS", "30")
    monkeypatch.setenv("CONTROL_APP_ACCESS_TOKEN", "test-token")

    for module_name in list(sys.modules):
        if module_name.startswith("backend.app") or module_name.startswith("integration"):
            del sys.modules[module_name]

    backend_main = importlib.import_module("backend.app.main")
    app = backend_main.create_app()

    with TestClient(app) as test_client:
        yield test_client
