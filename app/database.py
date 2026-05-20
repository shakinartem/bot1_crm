from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def create_db_schema() -> None:
    from app.modules.calls.models import CallRecord  # noqa: F401
    from app.modules.crm.models import (  # noqa: F401
        Company,
        ContactPoint,
        DecisionMaker,
        FollowUpTask,
        LeadInteraction,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
