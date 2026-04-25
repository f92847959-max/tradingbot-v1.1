"""Repository for AI signal operations."""

import logging
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, and_, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models import Signal, ModelMetadata

logger = logging.getLogger(__name__)


class SignalRepository(BaseRepository[Signal]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Signal)

    async def add(self, entity: Signal) -> Signal:
        """Add a signal with explicit error handling (no silent failures)."""
        try:
            self.session.add(entity)
            await self.session.flush()
            return entity
        except IntegrityError as e:
            logger.warning("Signal duplicate or constraint violation: %s", e)
            await self.session.rollback()
            raise
        except OperationalError as e:
            logger.error("Database connection error saving signal: %s", e)
            raise

    async def get_latest(self, count: int = 1) -> Sequence[Signal]:
        stmt = (
            select(Signal)
            .order_by(Signal.timestamp.desc())
            .limit(count)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_date_range(
        self, start: datetime, end: datetime
    ) -> Sequence[Signal]:
        stmt = (
            select(Signal)
            .where(and_(Signal.timestamp >= start, Signal.timestamp <= end))
            .order_by(Signal.timestamp.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def mark_executed(self, signal_id: int) -> None:
        stmt = (
            update(Signal)
            .where(Signal.id == signal_id)
            .values(was_executed=True)
        )
        await self.session.execute(stmt)

    async def mark_rejected(self, signal_id: int, reason: str) -> None:
        stmt = (
            update(Signal)
            .where(Signal.id == signal_id)
            .values(was_executed=False, rejection_reason=reason)
        )
        await self.session.execute(stmt)

    async def get_execution_rate(self, days: int = 7) -> dict:
        """Get signal execution statistics for the last N days."""
        from sqlalchemy import func
        cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        from datetime import timedelta
        cutoff = cutoff - timedelta(days=days)

        total_stmt = (
            select(func.count())
            .select_from(Signal)
            .where(Signal.timestamp >= cutoff)
        )
        executed_stmt = (
            select(func.count())
            .select_from(Signal)
            .where(and_(Signal.timestamp >= cutoff, Signal.was_executed.is_(True)))
        )

        total = (await self.session.execute(total_stmt)).scalar_one()
        executed = (await self.session.execute(executed_stmt)).scalar_one()

        return {
            "total": total,
            "executed": executed,
            "rejected": total - executed,
            "execution_rate": executed / total if total > 0 else 0,
        }


class ModelMetadataRepository(BaseRepository[ModelMetadata]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ModelMetadata)

    async def get_latest_by_name(self, model_name: str) -> ModelMetadata | None:
        stmt = (
            select(ModelMetadata)
            .where(ModelMetadata.model_name == model_name)
            .order_by(ModelMetadata.trained_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_latest(self) -> Sequence[ModelMetadata]:
        """Get the latest metadata entry for each model."""
        from sqlalchemy import func

        subq = (
            select(
                ModelMetadata.model_name,
                func.max(ModelMetadata.trained_at).label("latest"),
            )
            .group_by(ModelMetadata.model_name)
            .subquery()
        )
        stmt = select(ModelMetadata).join(
            subq,
            and_(
                ModelMetadata.model_name == subq.c.model_name,
                ModelMetadata.trained_at == subq.c.latest,
            ),
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
