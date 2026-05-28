from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.research_queue.models import ResearchJob
from app.modules.research_queue.service import run_research_batch


async def run_batch_worker(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    concurrency: int = 5,
    limit: int = 100,
) -> list[ResearchJob]:
    return await run_research_batch(session_factory, concurrency=concurrency, limit=limit)
