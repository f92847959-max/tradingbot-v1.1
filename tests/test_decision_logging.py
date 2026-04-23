"""Tests for governance decision persistence and retrieval."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database.models import Base
from database.repositories.governance_repo import GovernanceDecisionRepository
import trading.trading_loop as trading_loop_module
from trading.trading_loop import TradingLoopMixin


class DummyTradingSystem(TradingLoopMixin):
    pass


@asynccontextmanager
async def governance_session_ctx():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def _sample_signal(
    *,
    final_action: str = "HOLD",
    gate_decision: str = "block",
    threshold_source: str = "ranging:BUY",
    gate_reasons: list[str] | None = None,
) -> dict:
    reasons = gate_reasons or ["global_confidence 0.42 < min 0.55"]
    return {
        "action": final_action,
        "confidence": 0.42 if final_action == "HOLD" else 0.77,
        "final_aggregation": {
            "global_score": 0.41 if final_action == "BUY" else 0.09,
            "conflict_ratio": 0.18,
            "threshold_source": threshold_source,
            "gate_decision": gate_decision,
            "regime": "ranging",
            "decision_audit": {
                "preliminary_action": "BUY",
                "final_action": final_action,
                "gate_decision": gate_decision,
                "gate_reasons": reasons,
                "threshold_source": threshold_source,
                "threshold_confidence": 0.55,
                "threshold_margin": 0.05,
                "conflict_ratio": 0.18,
                "confidence_before": 0.77,
                "final_confidence": 0.42 if final_action == "HOLD" else 0.77,
                "global_score": 0.41,
                "regime": "ranging",
            },
        },
    }


@pytest.mark.asyncio
async def test_persist_hold_decision_saves_audit_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    models_dir = tmp_path / "saved_models"
    models_dir.mkdir()
    (models_dir / "production.json").write_text(
        json.dumps(
            {
                "version_dir": "v007_20260423_210000",
                "path": "C:/unsafe/absolute/v007_20260423_210000",
            }
        ),
        encoding="utf-8",
    )

    system = DummyTradingSystem()
    system._ai_predictor = SimpleNamespace(
        _predictor=SimpleNamespace(saved_models_dir=str(models_dir))
    )

    async with governance_session_ctx() as governance_session:
        @asynccontextmanager
        async def fake_get_session():
            yield governance_session

        monkeypatch.setattr(trading_loop_module, "get_session", fake_get_session)

        await system._persist_governance_decision(
            _sample_signal(),
            executed=False,
            rejection_reason="AI_HOLD",
        )

        repo = GovernanceDecisionRepository(governance_session)
        rows = await repo.get_recent(limit=1)
        assert len(rows) == 1
        row = rows[0]
        assert row.final_action == "HOLD"
        assert row.gate_decision == "block"
        assert row.threshold_source == "ranging:BUY"
        assert row.gate_reasons == ["global_confidence 0.42 < min 0.55"]
        assert row.artifact_version == "v007_20260423_210000"
        assert row.rejection_reason == "AI_HOLD"


@pytest.mark.asyncio
async def test_recent_decisions_return_newest_first_with_execution_state():
    async with governance_session_ctx() as governance_session:
        repo = GovernanceDecisionRepository(governance_session)

        await repo.add_decision(
            audit=_sample_signal(final_action="HOLD")["final_aggregation"]["decision_audit"],
            was_executed=False,
            rejection_reason="RISK_LIMIT",
            artifact_version="C:/models/v001_20260423",
        )
        await repo.add_decision(
            audit=_sample_signal(final_action="BUY", gate_decision="pass")["final_aggregation"]["decision_audit"],
            was_executed=True,
            artifact_version="C:/models/v002_20260423",
            evaluation_summary={"promotion": {"promote": False}},
        )

        rows = await repo.get_recent(limit=2)
        assert [row.artifact_version for row in rows] == [
            "v002_20260423",
            "v001_20260423",
        ]
        assert rows[0].was_executed is True
        assert rows[0].evaluation_summary == {"promotion": {"promote": False}}
        assert rows[1].rejection_reason == "RISK_LIMIT"


@pytest.mark.asyncio
async def test_artifact_version_is_sanitized_before_storage():
    async with governance_session_ctx() as governance_session:
        repo = GovernanceDecisionRepository(governance_session)
        await repo.add_decision(
            audit=_sample_signal()["final_aggregation"]["decision_audit"],
            artifact_version="C:\\outside\\models\\nested\\v099_unsafe",
        )

        rows = await repo.get_recent(limit=1)
        assert rows[0].artifact_version == "v099_unsafe"
