from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.modules.research.service import run_company_research
from app.modules.research_queue.models import ResearchJob
from app.modules.research_queue.schemas import ResearchJobRead, ResearchQueueStatusRead


OPEN_JOB_STATUSES = {"pending", "running"}
FINAL_JOB_STATUSES = {"success", "failed", "blocked", "needs_manual_review", "cancelled"}


async def create_research_jobs_for_companies(
    session: AsyncSession,
    company_ids: list[int],
    job_type: str = "full_research",
    priority: str = "medium",
    max_attempts: int = 3,
) -> list[ResearchJob]:
    unique_ids = list(dict.fromkeys(company_ids))
    if not unique_ids:
        return []
    result = await session.execute(
        select(ResearchJob).where(
            ResearchJob.company_id.in_(unique_ids),
            ResearchJob.job_type == job_type,
            ResearchJob.status.in_(OPEN_JOB_STATUSES),
        )
    )
    existing_by_company = {job.company_id for job in result.scalars().all()}
    jobs: list[ResearchJob] = []
    for company_id in unique_ids:
        if company_id in existing_by_company:
            continue
        job = ResearchJob(
            company_id=company_id,
            job_type=job_type,
            status="pending",
            priority=priority,
            max_attempts=max_attempts,
        )
        session.add(job)
        jobs.append(job)
    await session.commit()
    for job in jobs:
        await session.refresh(job)
    return jobs


async def get_pending_jobs(session: AsyncSession, limit: int = 100) -> list[ResearchJob]:
    result = await session.execute(
        select(ResearchJob)
        .where(ResearchJob.status == "pending")
        .order_by(ResearchJob.created_at.asc(), ResearchJob.id.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_research_jobs(session: AsyncSession, limit: int = 100) -> list[ResearchJob]:
    result = await session.execute(
        select(ResearchJob).order_by(ResearchJob.created_at.desc(), ResearchJob.id.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def run_research_job(session: AsyncSession, job_id: int) -> ResearchJob:
    job = await session.get(ResearchJob, job_id)
    if not job:
        raise ValueError("Research job not found")
    if job.status == "cancelled":
        return job
    job.status = "running"
    job.attempts += 1
    job.started_at = datetime.now()
    await session.commit()

    try:
        result = await run_company_research(session, job.company_id)
        job.status = result.status
        job.result_json = result.model_dump_json()
        job.error_message = result.error_message or result.blocked_reason
    except Exception as exc:  # pragma: no cover
        job.error_message = str(exc)
        job.status = "pending" if job.attempts < job.max_attempts else "failed"
    if job.status in FINAL_JOB_STATUSES - {"pending", "running"}:
        job.finished_at = datetime.now()
    await session.commit()
    await session.refresh(job)
    return job


async def run_research_batch(
    session_factory: async_sessionmaker[AsyncSession],
    concurrency: int = 5,
    limit: int = 100,
) -> list[ResearchJob]:
    async with session_factory() as session:
        pending = await get_pending_jobs(session, limit=limit)
    if not pending:
        return []

    semaphore = asyncio.Semaphore(max(1, concurrency))
    delay_seconds = get_settings().research_request_delay_ms / 1000
    completed_ids: list[int] = []

    async def _runner(job_id: int) -> None:
        async with semaphore:
            async with session_factory() as batch_session:
                await run_research_job(batch_session, job_id)
            completed_ids.append(job_id)
            await asyncio.sleep(delay_seconds)

    await asyncio.gather(*[_runner(job.id) for job in pending])

    async with session_factory() as session:
        result = await session.execute(select(ResearchJob).where(ResearchJob.id.in_(completed_ids)))
        return list(result.scalars().all())


async def cancel_job(session: AsyncSession, job_id: int) -> ResearchJob | None:
    job = await session.get(ResearchJob, job_id)
    if not job:
        return None
    if job.status in FINAL_JOB_STATUSES:
        return job
    job.status = "cancelled"
    await session.commit()
    await session.refresh(job)
    return job


async def get_queue_status(session: AsyncSession) -> ResearchQueueStatusRead:
    result = await session.execute(select(ResearchJob.status, func.count(ResearchJob.id)).group_by(ResearchJob.status))
    counts = Counter({status: count for status, count in result.all()})
    total = sum(counts.values())
    return ResearchQueueStatusRead(
        total=total,
        pending=counts.get("pending", 0),
        running=counts.get("running", 0),
        success=counts.get("success", 0),
        failed=counts.get("failed", 0),
        blocked=counts.get("blocked", 0),
        needs_manual_review=counts.get("needs_manual_review", 0),
        cancelled=counts.get("cancelled", 0),
    )


def serialize_job(job: ResearchJob) -> ResearchJobRead:
    from app.modules.enrichment.schemas import parse_json_text

    return ResearchJobRead(
        id=job.id,
        company_id=job.company_id,
        job_type=job.job_type,
        status=job.status,
        priority=job.priority,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_message=job.error_message,
        result=parse_json_text(job.result_json, None),
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
