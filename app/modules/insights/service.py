from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Select, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models import CompanyInsightSnapshot
from app.modules.insights.schemas import CompanyInsightSnapshotCreate, CompanyInsightSnapshotRead


def _serialize_payload(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Company insight payload must be valid JSON-serializable data.") from exc


def safe_load_payload(snapshot: CompanyInsightSnapshot | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    try:
        payload = json.loads(snapshot.payload_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def serialize_company_insight_snapshot(snapshot: CompanyInsightSnapshot) -> CompanyInsightSnapshotRead:
    payload = safe_load_payload(snapshot)
    if payload is None:
        payload = {}
    return CompanyInsightSnapshotRead(
        id=snapshot.id,
        company_id=snapshot.company_id,
        insight_type=snapshot.insight_type,
        title=snapshot.title,
        status=snapshot.status,
        payload=payload,
        summary=snapshot.summary,
        source=snapshot.source,
        version=snapshot.version,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
    )


async def create_company_insight_snapshot(
    session: AsyncSession,
    payload: CompanyInsightSnapshotCreate,
) -> CompanyInsightSnapshot:
    snapshot = CompanyInsightSnapshot(
        company_id=payload.company_id,
        insight_type=payload.insight_type,
        title=payload.title,
        status=payload.status,
        payload_json=_serialize_payload(payload.payload),
        summary=payload.summary,
        source=payload.source,
        version=payload.version,
    )
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    return snapshot


async def get_company_insight(
    session: AsyncSession,
    company_id: int,
    insight_id: int,
) -> CompanyInsightSnapshot | None:
    result = await session.execute(
        select(CompanyInsightSnapshot).where(
            CompanyInsightSnapshot.company_id == company_id,
            CompanyInsightSnapshot.id == insight_id,
        )
    )
    return result.scalar_one_or_none()


async def get_latest_company_insight(
    session: AsyncSession,
    company_id: int,
    insight_type: str,
) -> CompanyInsightSnapshot | None:
    result = await session.execute(
        _insight_history_stmt(company_id, insight_type=insight_type).limit(1)
    )
    return result.scalar_one_or_none()


async def get_company_insight_history(
    session: AsyncSession,
    company_id: int,
    insight_type: str | None = None,
    limit: int = 20,
) -> list[CompanyInsightSnapshot]:
    result = await session.execute(
        _insight_history_stmt(company_id, insight_type=insight_type).limit(limit)
    )
    return list(result.scalars().all())


def _insight_history_stmt(
    company_id: int,
    *,
    insight_type: str | None,
) -> Select[tuple[CompanyInsightSnapshot]]:
    stmt = (
        select(CompanyInsightSnapshot)
        .where(CompanyInsightSnapshot.company_id == company_id)
        .order_by(desc(CompanyInsightSnapshot.created_at), desc(CompanyInsightSnapshot.id))
    )
    if insight_type:
        stmt = stmt.where(CompanyInsightSnapshot.insight_type == insight_type)
    return stmt


__all__ = [
    "create_company_insight_snapshot",
    "get_company_insight",
    "get_company_insight_history",
    "get_latest_company_insight",
    "safe_load_payload",
    "serialize_company_insight_snapshot",
]
