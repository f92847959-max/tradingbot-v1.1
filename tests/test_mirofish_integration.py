"""Integration tests for MiroFish signal pipeline.

Verifies the full signal flow through SignalGeneratorMixin._generate_signal()
with mocked AIPredictor and MiroFishClient -- no live backend required.

The trading.signal_generator module imports database.connection at module level,
which requires sqlalchemy. We patch database.connection before importing the mixin
so these tests can run without the full project venv.

IMPORTANT: We do NOT stub the `shared` or `database` packages themselves -- only
`database.connection`, `database.models`, and `database.repositories.signal_repo`
are patched. This avoids polluting sys.modules for other test modules.

Tests cover:
1. Veto blocks BUY when swarm says SELL (and vice versa)
2. Signal passes when swarm agrees
3. Signal passes when MiroFish is disabled
4. Signal passes when no cached assessment is available
5. HOLD signals are never vetoed
6. Signal passes when _mirofish_client is None (init failed)
"""
from __future__ import annotations

import asyncio
import sys
import time
import types
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Stub ONLY the modules that pull in sqlalchemy, before any trading.* import.
# We replace only the leaf modules (connection.py, models.py, signal_repo.py)
# without touching the `database` or `shared` packages themselves.
# ---------------------------------------------------------------------------

def _stub_module(name: str, **attrs) -> types.ModuleType:
    """Create/replace a module in sys.modules with given attributes."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# Stub sqlalchemy and its submodules (only if not already present)
for _sa_mod in [
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm",
]:
    if _sa_mod not in sys.modules:
        _stub_module(_sa_mod)

# Stub only the leaf modules that signal_generator.py imports
# (leave `database` and `database.repositories` parent packages untouched
#  so they can still be imported as real packages by other test files)
_stub_module("database.connection", get_session=MagicMock())
_stub_module("database.models", Signal=MagicMock())
_stub_module("database.repositories.signal_repo", SignalRepository=MagicMock())

# Now we can safely import SignalGeneratorMixin
from trading.signal_generator import SignalGeneratorMixin  # noqa: E402
from ai_engine.mirofish_client import MiroFishClient, SwarmAssessment  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(mirofish_enabled: bool = True) -> types.SimpleNamespace:
    """Return a minimal settings namespace with all fields _generate_signal touches."""
    return types.SimpleNamespace(
        mirofish_enabled=mirofish_enabled,
        mirofish_url="http://localhost:5001",
        mirofish_cache_ttl_seconds=360,
        mirofish_poll_interval_seconds=300,
        mirofish_max_sims_per_day=48,
        mirofish_token_budget_per_day=200_000,
        mirofish_simulation_timeout_seconds=180.0,
        mirofish_max_rounds=15,
        min_confidence=0.6,
        timeframes=["5m"],
    )


def _make_df() -> pd.DataFrame:
    """Return a minimal candle DataFrame (50 rows) to pass to _generate_signal."""
    n = 50
    idx = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    rng = np.random.default_rng(42)
    close = 2045.0 + rng.standard_normal(n).cumsum() * 0.5
    return pd.DataFrame(
        {
            "timestamp": idx,
            "open": close + rng.standard_normal(n) * 0.2,
            "high": close + np.abs(rng.standard_normal(n)) * 0.3,
            "low": close - np.abs(rng.standard_normal(n)) * 0.3,
            "close": close,
            "volume": rng.uniform(500, 3000, n),
        }
    )


def _make_mock_predictor(signal_return: dict) -> MagicMock:
    """Return a mock AIPredictor that yields signal_return from predict()."""
    mock_predictor = MagicMock()
    mock_predictor.is_ready = True
    mock_predictor.load = MagicMock(return_value=True)
    mock_predictor.predict = AsyncMock(return_value=signal_return)
    return mock_predictor


def _make_mock_system(
    signal_return: dict,
    mirofish_enabled: bool = True,
    mirofish_client=None,
) -> types.SimpleNamespace:
    """Build a minimal mock TradingSystem for calling _generate_signal().

    The mock provides all attributes that SignalGeneratorMixin._generate_signal
    accesses:
    - settings
    - _ai_predictor (mock with async predict())
    - _mirofish_client
    - data (mock DataProvider)
    """
    mock_data = MagicMock()
    mock_data.get_multi_timeframe_data = AsyncMock(return_value={"5m": _make_df()})

    return types.SimpleNamespace(
        settings=_make_settings(mirofish_enabled=mirofish_enabled),
        _ai_predictor=_make_mock_predictor(signal_return),
        _mirofish_client=mirofish_client,
        data=mock_data,
    )


def _run(coro):
    """Run a coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_mirofish_client(tmp_path, direction: str, confidence: float = 0.75, no_cache: bool = False):
    """Return a MiroFishClient with a pre-set (or absent) cached assessment."""
    client = MiroFishClient(
        state_file=str(tmp_path / "state.json"),
        cost_file=str(tmp_path / "cost.json"),
        cache_ttl_seconds=3600.0,  # long TTL so cache is always valid
    )
    if not no_cache:
        client._cached = SwarmAssessment(
            direction=direction,
            confidence=confidence,
            reasoning=f"Test reasoning for {direction}",
            timestamp=time.monotonic(),
        )
    return client


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestMiroFishSignalPipeline:
    """End-to-end signal pipeline tests with mocked MiroFish."""

    def test_signal_vetoed_when_mirofish_contradicts(self, tmp_path):
        """BUY signal from ML gets vetoed to HOLD when swarm says SELL."""
        ml_signal = {"action": "BUY", "confidence": 0.85}
        mf_client = _make_mirofish_client(tmp_path, direction="SELL", confidence=0.7)

        system = _make_mock_system(
            signal_return=ml_signal,
            mirofish_enabled=True,
            mirofish_client=mf_client,
        )

        result = _run(SignalGeneratorMixin._generate_signal(system, df=_make_df(), mtf_data=None))

        assert result is not None
        assert result["action"] == "HOLD", f"Expected HOLD, got {result['action']}"
        assert result.get("mirofish_veto") is True, "Expected mirofish_veto=True"

    def test_signal_passes_when_mirofish_agrees(self, tmp_path):
        """BUY signal passes through (with metadata) when swarm also says BUY."""
        ml_signal = {"action": "BUY", "confidence": 0.85}
        mf_client = _make_mirofish_client(tmp_path, direction="BUY", confidence=0.8)

        system = _make_mock_system(
            signal_return=ml_signal,
            mirofish_enabled=True,
            mirofish_client=mf_client,
        )

        result = _run(SignalGeneratorMixin._generate_signal(system, df=_make_df(), mtf_data=None))

        assert result is not None
        assert result["action"] == "BUY", f"Expected BUY, got {result['action']}"
        assert result.get("mirofish_veto") is False, "Expected mirofish_veto=False"

    def test_signal_passes_when_mirofish_disabled(self, tmp_path):
        """BUY signal passes through without any MiroFish metadata when mirofish_enabled=False."""
        ml_signal = {"action": "BUY", "confidence": 0.85}
        mf_client = _make_mirofish_client(tmp_path, direction="SELL", confidence=0.7)

        system = _make_mock_system(
            signal_return=ml_signal,
            mirofish_enabled=False,  # Disabled -- veto check must be skipped entirely
            mirofish_client=mf_client,
        )

        result = _run(SignalGeneratorMixin._generate_signal(system, df=_make_df(), mtf_data=None))

        assert result is not None
        assert result["action"] == "BUY", f"Expected BUY (no veto when disabled), got {result['action']}"
        assert "mirofish_veto" not in result, "mirofish_veto should NOT be in result when disabled"

    def test_signal_passes_when_no_cached_assessment(self, tmp_path):
        """BUY signal passes through unchanged when MiroFish has no cached result yet."""
        ml_signal = {"action": "BUY", "confidence": 0.85}
        mf_client = _make_mirofish_client(tmp_path, direction="SELL", no_cache=True)

        system = _make_mock_system(
            signal_return=ml_signal,
            mirofish_enabled=True,
            mirofish_client=mf_client,
        )

        result = _run(SignalGeneratorMixin._generate_signal(system, df=_make_df(), mtf_data=None))

        assert result is not None
        assert result["action"] == "BUY", f"Expected BUY when no cache, got {result['action']}"
        # check_veto returns signal unchanged when no cache -- no mirofish_veto key
        assert "mirofish_veto" not in result, "mirofish_veto should NOT be set when no cache"

    def test_hold_signal_never_vetoed(self, tmp_path):
        """HOLD signals from ML are never passed to check_veto even with mirofish enabled."""
        ml_signal = {"action": "HOLD", "confidence": 0.3}
        mf_client = _make_mirofish_client(tmp_path, direction="SELL", confidence=0.8)

        system = _make_mock_system(
            signal_return=ml_signal,
            mirofish_enabled=True,
            mirofish_client=mf_client,
        )

        result = _run(SignalGeneratorMixin._generate_signal(system, df=_make_df(), mtf_data=None))

        assert result is not None
        assert result["action"] == "HOLD", f"Expected HOLD to remain HOLD, got {result['action']}"
        # HOLD signals skip the veto check entirely in _generate_signal()
        # (condition: signal.get("action") not in (None, "HOLD"))
        assert "mirofish_veto" not in result, "mirofish_veto should NOT be set for HOLD signals"

    def test_mirofish_client_not_initialized_passes_signal(self, tmp_path):
        """BUY signal passes through unchanged when _mirofish_client is None (init failed)."""
        ml_signal = {"action": "BUY", "confidence": 0.85}

        system = _make_mock_system(
            signal_return=ml_signal,
            mirofish_enabled=True,
            mirofish_client=None,  # Client never initialized
        )

        result = _run(SignalGeneratorMixin._generate_signal(system, df=_make_df(), mtf_data=None))

        assert result is not None
        assert result["action"] == "BUY", f"Expected BUY when client is None, got {result['action']}"
        assert "mirofish_veto" not in result, "mirofish_veto should NOT be set when client is None"
