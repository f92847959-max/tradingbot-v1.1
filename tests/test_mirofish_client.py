"""Unit tests for ai_engine/mirofish_client.py.

Tests cover:
- SwarmAssessment dataclass
- parse_swarm_direction function
- MiroFishCostLimiter class
- MiroFishClient cache and health check
- Veto logic (check_veto)
"""
import asyncio
import json
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Skip marker for tests that need a live MiroFish backend
MIROFISH_AVAILABLE = os.environ.get("MIROFISH_AVAILABLE", "false").lower() == "true"
requires_mirofish = pytest.mark.skipif(
    not MIROFISH_AVAILABLE,
    reason="Requires live MiroFish server (set MIROFISH_AVAILABLE=true)",
)

# -------------------------------------------------------------------------
# Imports from module under test (must succeed for tests to run)
# -------------------------------------------------------------------------
from ai_engine.mirofish_client import (  # noqa: E402
    MiroFishClient,
    MiroFishCostLimiter,
    SwarmAssessment,
    parse_swarm_direction,
)


# =========================================================================
# SwarmAssessment tests
# =========================================================================


class TestSwarmAssessment:
    def test_stores_direction_confidence_reasoning(self):
        sa = SwarmAssessment(direction="BUY", confidence=0.75, reasoning="Positive trend")
        assert sa.direction == "BUY"
        assert sa.confidence == 0.75
        assert sa.reasoning == "Positive trend"

    def test_timestamp_defaults_to_monotonic(self):
        before = time.monotonic()
        sa = SwarmAssessment(direction="NEUTRAL", confidence=0.5, reasoning="Unclear")
        after = time.monotonic()
        assert before <= sa.timestamp <= after

    def test_custom_timestamp(self):
        sa = SwarmAssessment(direction="SELL", confidence=0.8, reasoning="Bear", timestamp=123.45)
        assert sa.timestamp == 123.45


# =========================================================================
# parse_swarm_direction tests
# =========================================================================


class TestParseSwarmDirection:
    def test_buy_signal_steigende_preise(self):
        direction, confidence, reasoning = parse_swarm_direction(
            "steigende Preise und Inflationsdruck treiben Gold nach oben"
        )
        assert direction == "BUY"
        assert confidence > 0.5
        assert isinstance(reasoning, str)
        assert len(reasoning) > 0

    def test_sell_signal_dollar_staerkt(self):
        direction, confidence, reasoning = parse_swarm_direction(
            "Dollar staerkt sich, restriktive Geldpolitik drückt Goldpreis"
        )
        assert direction == "SELL"
        assert confidence > 0.5
        assert isinstance(reasoning, str)

    def test_neutral_signal_keine_klare_richtung(self):
        direction, confidence, reasoning = parse_swarm_direction("keine klare Richtung erkennbar")
        assert direction == "NEUTRAL"
        assert confidence == 0.5
        assert isinstance(reasoning, str)

    def test_empty_string_returns_neutral(self):
        direction, confidence, reasoning = parse_swarm_direction("")
        assert direction == "NEUTRAL"
        assert confidence == 0.5
        assert reasoning == "Keine klare Richtung erkennbar"

    def test_confidence_capped_at_0_9(self):
        # Many bullish keywords to test confidence cap
        text = (
            "aufwaertstrend steigende preise kaufsignal bullish preissteigerung "
            "hausse nachfrage steigt positive entwicklung zentralbank kauft "
            "geopolitische unsicherheit steigt inflationsdruck dollar schwaecht"
        )
        direction, confidence, reasoning = parse_swarm_direction(text)
        assert direction == "BUY"
        assert confidence <= 0.9

    def test_returns_tuple_of_three(self):
        result = parse_swarm_direction("aufwaertstrend")
        assert len(result) == 3

    def test_bearish_keywords_produce_sell(self):
        direction, confidence, reasoning = parse_swarm_direction(
            "abwaertstrend fallende preise verkaufssignal bearish baisse"
        )
        assert direction == "SELL"
        assert confidence > 0.5


# =========================================================================
# MiroFishCostLimiter tests
# =========================================================================


class TestMiroFishCostLimiter:
    def test_can_run_returns_true_when_fresh(self, tmp_path):
        state_file = str(tmp_path / "cost.json")
        limiter = MiroFishCostLimiter(
            state_file=state_file,
            max_sims_per_day=48,
            token_budget_per_day=200_000,
        )
        allowed, reason = limiter.can_run()
        assert allowed is True
        assert reason == ""

    def test_can_run_blocked_when_sim_count_exceeded(self, tmp_path):
        state_file = str(tmp_path / "cost.json")
        limiter = MiroFishCostLimiter(
            state_file=state_file,
            max_sims_per_day=3,
            token_budget_per_day=200_000,
        )
        for _ in range(3):
            limiter.record_run(tokens_used=100)
        allowed, reason = limiter.can_run()
        assert allowed is False
        assert len(reason) > 0

    def test_can_run_blocked_when_token_budget_exceeded(self, tmp_path):
        state_file = str(tmp_path / "cost.json")
        limiter = MiroFishCostLimiter(
            state_file=state_file,
            max_sims_per_day=48,
            token_budget_per_day=1000,
        )
        limiter.record_run(tokens_used=1001)
        allowed, reason = limiter.can_run()
        assert allowed is False
        assert len(reason) > 0

    def test_resets_on_new_day(self, tmp_path):
        state_file = str(tmp_path / "cost.json")
        limiter = MiroFishCostLimiter(
            state_file=state_file,
            max_sims_per_day=3,
            token_budget_per_day=200_000,
        )
        for _ in range(3):
            limiter.record_run(tokens_used=100)

        # Simulate old date in state file
        with open(state_file, "r") as f:
            state = json.load(f)
        state["date"] = "2000-01-01"  # old date
        with open(state_file, "w") as f:
            json.dump(state, f)

        # Reload limiter -- should see new day and reset
        limiter2 = MiroFishCostLimiter(
            state_file=state_file,
            max_sims_per_day=3,
            token_budget_per_day=200_000,
        )
        allowed, reason = limiter2.can_run()
        assert allowed is True

    def test_record_run_increments_sim_count_and_tokens(self, tmp_path):
        state_file = str(tmp_path / "cost.json")
        limiter = MiroFishCostLimiter(
            state_file=state_file,
            max_sims_per_day=48,
            token_budget_per_day=200_000,
        )
        limiter.record_run(tokens_used=5000)
        state = limiter._load()
        assert state["sim_count"] == 1
        assert state["tokens_used"] == 5000

    def test_record_run_accumulates(self, tmp_path):
        state_file = str(tmp_path / "cost.json")
        limiter = MiroFishCostLimiter(
            state_file=state_file,
            max_sims_per_day=48,
            token_budget_per_day=200_000,
        )
        limiter.record_run(tokens_used=3000)
        limiter.record_run(tokens_used=2000)
        state = limiter._load()
        assert state["sim_count"] == 2
        assert state["tokens_used"] == 5000


# =========================================================================
# MiroFishClient cache and health check tests
# =========================================================================


class TestMiroFishClientCache:
    def test_get_cached_assessment_returns_none_when_empty(self, tmp_path):
        client = MiroFishClient(
            state_file=str(tmp_path / "state.json"),
            cost_file=str(tmp_path / "cost.json"),
        )
        assert client.get_cached_assessment() is None

    def test_get_cached_assessment_returns_within_ttl(self, tmp_path):
        client = MiroFishClient(
            cache_ttl_seconds=3600.0,  # long TTL
            state_file=str(tmp_path / "state.json"),
            cost_file=str(tmp_path / "cost.json"),
        )
        assessment = SwarmAssessment(direction="BUY", confidence=0.8, reasoning="Test")
        client._cached = assessment
        result = client.get_cached_assessment()
        assert result is assessment

    def test_get_cached_assessment_returns_none_when_expired(self, tmp_path):
        client = MiroFishClient(
            cache_ttl_seconds=1.0,  # very short TTL
            state_file=str(tmp_path / "state.json"),
            cost_file=str(tmp_path / "cost.json"),
        )
        old_assessment = SwarmAssessment(
            direction="BUY",
            confidence=0.8,
            reasoning="Old",
            timestamp=time.monotonic() - 10.0,  # 10 seconds ago -- expired
        )
        client._cached = old_assessment
        result = client.get_cached_assessment()
        assert result is None


class TestMiroFishClientHealthCheck:
    def test_health_check_returns_true_on_200(self, tmp_path):
        client = MiroFishClient(
            base_url="http://localhost:5001",
            state_file=str(tmp_path / "state.json"),
            cost_file=str(tmp_path / "cost.json"),
        )

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client_ctx)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client_ctx.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client_ctx):
            result = asyncio.get_event_loop().run_until_complete(client.health_check())

        assert result is True

    def test_health_check_returns_false_on_connection_error(self, tmp_path):
        import httpx

        client = MiroFishClient(
            base_url="http://localhost:5001",
            state_file=str(tmp_path / "state.json"),
            cost_file=str(tmp_path / "cost.json"),
        )

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client_ctx)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client_ctx.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        with patch("httpx.AsyncClient", return_value=mock_client_ctx):
            result = asyncio.get_event_loop().run_until_complete(client.health_check())

        assert result is False


# =========================================================================
# Veto check tests (Task 2)
# =========================================================================


class TestCheckVeto:
    def _make_client(self, tmp_path):
        return MiroFishClient(
            state_file=str(tmp_path / "state.json"),
            cost_file=str(tmp_path / "cost.json"),
        )

    def test_veto_buy_blocked_by_sell(self, tmp_path):
        client = self._make_client(tmp_path)
        client._cached = SwarmAssessment(direction="SELL", confidence=0.8, reasoning="Bearish")
        result = client.check_veto({"action": "BUY", "confidence": 0.8})
        assert result["action"] == "HOLD"
        assert result["mirofish_veto"] is True

    def test_veto_sell_blocked_by_buy(self, tmp_path):
        client = self._make_client(tmp_path)
        client._cached = SwarmAssessment(direction="BUY", confidence=0.8, reasoning="Bullish")
        result = client.check_veto({"action": "SELL", "confidence": 0.7})
        assert result["action"] == "HOLD"
        assert result["mirofish_veto"] is True

    def test_veto_neutral_passthrough(self, tmp_path):
        client = self._make_client(tmp_path)
        client._cached = SwarmAssessment(direction="NEUTRAL", confidence=0.5, reasoning="Unclear")
        result = client.check_veto({"action": "BUY", "confidence": 0.75})
        assert result["action"] == "BUY"
        assert result["mirofish_veto"] is False

    def test_veto_agreement_passthrough(self, tmp_path):
        client = self._make_client(tmp_path)
        client._cached = SwarmAssessment(direction="BUY", confidence=0.85, reasoning="Bullish")
        result = client.check_veto({"action": "BUY", "confidence": 0.75})
        assert result["action"] == "BUY"
        assert result["mirofish_veto"] is False
        assert result["mirofish_direction"] == "BUY"
        assert result["mirofish_confidence"] == 0.85

    def test_veto_no_cache_passthrough(self, tmp_path):
        client = self._make_client(tmp_path)
        # No cached assessment
        signal = {"action": "BUY", "confidence": 0.75}
        result = client.check_veto(signal)
        assert result == signal
        assert "mirofish_veto" not in result

    def test_veto_hold_signal_unchanged(self, tmp_path):
        client = self._make_client(tmp_path)
        client._cached = SwarmAssessment(direction="SELL", confidence=0.8, reasoning="Bearish")
        result = client.check_veto({"action": "HOLD", "confidence": 0.5})
        assert result["action"] == "HOLD"
        assert result.get("mirofish_veto") is False  # HOLD is not vetoed (no contradiction)
