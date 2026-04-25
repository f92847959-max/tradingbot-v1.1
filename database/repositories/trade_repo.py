"""Repository for trade and order log operations."""

from datetime import datetime, timedelta, date, timezone
from typing import Sequence

from sqlalchemy import select, and_, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models import Trade, OrderLog


class TradeRepository(BaseRepository[Trade]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Trade)

    async def get_open_trades(self) -> Sequence[Trade]:
        stmt = (
            select(Trade)
            .where(Trade.status == "OPEN")
            .order_by(Trade.opened_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_deal_id(self, deal_id: str) -> Trade | None:
        stmt = select(Trade).where(Trade.deal_id == deal_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        pnl_pips: float,
        pnl_euros: float,
        net_pnl: float,
        close_reason: str,
        closed_at: datetime | None = None,
    ) -> None:
        now = closed_at or datetime.now(timezone.utc)
        stmt = (
            update(Trade)
            .where(Trade.id == trade_id)
            .values(
                exit_price=exit_price,
                pnl_pips=pnl_pips,
                pnl_euros=pnl_euros,
                net_pnl=net_pnl,
                close_reason=close_reason,
                closed_at=now,
                status="CLOSED",
            )
        )
        await self.session.execute(stmt)

    async def get_today_trades(self) -> Sequence[Trade]:
        today = date.today()
        stmt = (
            select(Trade)
            .where(func.date(Trade.opened_at) == today)
            .order_by(Trade.opened_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_today(self) -> int:
        today = date.today()
        stmt = (
            select(func.count())
            .select_from(Trade)
            .where(func.date(Trade.opened_at) == today)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_today_pnl(self) -> float:
        today = date.today()
        stmt = (
            select(func.coalesce(func.sum(Trade.net_pnl), 0))
            .where(
                and_(
                    func.date(Trade.opened_at) == today,
                    Trade.status == "CLOSED",
                )
            )
        )
        result = await self.session.execute(stmt)
        return float(result.scalar_one())

    async def get_consecutive_losses(self) -> int:
        """Count current consecutive losing trades (most recent first)."""
        stmt = (
            select(Trade.net_pnl)
            .where(Trade.status == "CLOSED")
            .order_by(Trade.closed_at.desc())
            .limit(50)
        )
        result = await self.session.execute(stmt)
        losses = 0
        for (pnl,) in result:
            if pnl is not None and pnl < 0:
                losses += 1
            else:
                break
        return losses

    async def get_history(self, days: int = 7) -> Sequence[Trade]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(Trade)
            .where(Trade.opened_at >= cutoff)
            .order_by(Trade.opened_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def has_open_in_direction(self, direction: str) -> bool:
        stmt = (
            select(func.count())
            .select_from(Trade)
            .where(and_(Trade.status == "OPEN", Trade.direction == direction))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def get_weekly_pnl(self) -> float:
        """Get total net P&L for the current calendar week (Mon-Sun, UTC)."""
        today = datetime.now(timezone.utc).date()
        monday = today - timedelta(days=today.weekday())
        stmt = (
            select(func.coalesce(func.sum(Trade.net_pnl), 0))
            .where(
                and_(
                    func.date(Trade.opened_at) >= monday,
                    Trade.status == "CLOSED",
                )
            )
        )
        result = await self.session.execute(stmt)
        return float(result.scalar_one())


class OrderLogRepository(BaseRepository[OrderLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OrderLog)

    async def log_action(
        self, action: str, deal_id: str | None = None, details: dict | None = None
    ) -> OrderLog:
        entry = OrderLog(action=action, deal_id=deal_id, details=details)
        return await self.add(entry)

    async def get_by_deal_id(self, deal_id: str) -> Sequence[OrderLog]:
        stmt = (
            select(OrderLog)
            .where(OrderLog.deal_id == deal_id)
            .order_by(OrderLog.timestamp.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
