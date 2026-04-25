"""Base repository with common CRUD operations."""

from typing import Generic, Sequence, TypeVar

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    def __init__(self, session: AsyncSession, model: type[T]) -> None:
        self.session = session
        self.model = model

    async def get_by_id(self, id: int) -> T | None:
        return await self.session.get(self.model, id)

    async def get_all(self, limit: int = 100, offset: int = 0) -> Sequence[T]:
        stmt = select(self.model).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def add(self, entity: T) -> T:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def add_many(self, entities: list[T]) -> list[T]:
        self.session.add_all(entities)
        await self.session.flush()
        return entities

    async def delete_by_id(self, id: int) -> None:
        stmt = delete(self.model).where(self.model.id == id)
        await self.session.execute(stmt)

    async def count(self) -> int:
        from sqlalchemy import func
        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar_one()
