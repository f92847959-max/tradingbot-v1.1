"""Repository helpers for governance decision audit rows."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models import GovernanceDecision


def _sanitize_artifact_version(value: str | None) -> str | None:
    if not value:
        return None
    normalized = str(value).replace("\\", "/").rstrip("/")
    candidate = os.path.basename(normalized)
    if not candidate or candidate in {".", ".."}:
        return None
    return candidate[:120]


class GovernanceDecisionRepository(BaseRepository[GovernanceDecision]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GovernanceDecision)

    async def add_decision(
        self,
        *,
        audit: dict[str, Any],
        was_executed: bool = False,
        rejection_reason: str | None = None,
        artifact_version: str | None = None,
        evaluation_summary: dict[str, Any] | None = None,
    ) -> GovernanceDecision:
        entity = GovernanceDecision(
            preliminary_action=str(
                audit.get("preliminary_action") or audit.get("final_action") or "HOLD"
            ),
            final_action=str(audit.get("final_action") or "HOLD"),
            gate_decision=str(audit.get("gate_decision") or "pass"),
            regime=str(audit.get("regime") or "ranging"),
            confidence_before=float(audit.get("confidence_before", 0.0)),
            final_confidence=float(audit.get("final_confidence", 0.0)),
            conflict_ratio=float(audit.get("conflict_ratio", 0.0)),
            global_score=float(audit.get("global_score", 0.0)),
            gate_reasons=list(audit.get("gate_reasons") or []),
            threshold_source=str(audit.get("threshold_source") or "defaults"),
            threshold_confidence=float(audit.get("threshold_confidence", 0.0)),
            threshold_margin=float(audit.get("threshold_margin", 0.0)),
            artifact_version=_sanitize_artifact_version(artifact_version),
            was_executed=bool(was_executed),
            rejection_reason=rejection_reason or None,
            evaluation_summary=evaluation_summary or None,
        )
        return await self.add(entity)

    async def get_recent(self, limit: int = 20) -> Sequence[GovernanceDecision]:
        stmt = (
            select(GovernanceDecision)
            .order_by(
                GovernanceDecision.timestamp.desc(),
                GovernanceDecision.id.desc(),
            )
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_date_range(
        self,
        start: datetime,
        end: datetime,
        *,
        limit: int = 100,
    ) -> Sequence[GovernanceDecision]:
        stmt = (
            select(GovernanceDecision)
            .where(
                and_(
                    GovernanceDecision.timestamp >= start,
                    GovernanceDecision.timestamp <= end,
                )
            )
            .order_by(
                GovernanceDecision.timestamp.desc(),
                GovernanceDecision.id.desc(),
            )
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
