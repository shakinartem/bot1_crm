from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models import Company
from app.modules.insights.schemas import CompanyInsightSnapshotCreate
from app.modules.insights.service import create_company_insight_snapshot, get_latest_company_insight, safe_load_payload
from app.modules.lead_fit.rules import calculate_lead_fit
from app.modules.lead_fit.schemas import LeadFitGroupSummary, LeadFitScore


async def recalculate_company_lead_fit(session: AsyncSession, company_id: int) -> LeadFitScore:
    company = await session.get(Company, company_id)
    if not company or company.deleted_at is not None:
        raise ValueError("Company not found")
    score = calculate_lead_fit(company)
    score.calculated_at = datetime.utcnow()
    company.lead_fit_score = score.total_score
    company.lead_fit_group = score.group
    company.lead_fit_calculated_at = score.calculated_at
    session.add(company)
    await session.commit()
    await create_company_insight_snapshot(
        session,
        CompanyInsightSnapshotCreate(
            company_id=company.id,
            insight_type="lead_fit",
            title="Lead fit",
            status="success",
            payload=score.model_dump(mode="json"),
            summary=f"{score.group_label} / {score.total_score}",
            source="lead_fit",
            version="v1",
        ),
    )
    return score


async def recalculate_companies_lead_fit(session: AsyncSession, company_ids: list[int]) -> list[LeadFitScore]:
    scores: list[LeadFitScore] = []
    for company_id in company_ids:
        try:
            scores.append(await recalculate_company_lead_fit(session, company_id))
        except ValueError:
            continue
    return scores


async def get_company_lead_fit(session: AsyncSession, company_id: int) -> LeadFitScore | None:
    snapshot = await get_latest_company_insight(session, company_id, "lead_fit")
    payload = safe_load_payload(snapshot)
    if not payload:
        return None
    return LeadFitScore.model_validate(payload)


async def list_companies_by_lead_fit_group(
    session: AsyncSession,
    group: str,
) -> list[Company]:
    result = await session.execute(
        select(Company)
        .where(
            Company.deleted_at.is_(None),
            Company.lead_fit_group == group,
        )
        .order_by(Company.lead_fit_score.desc().nullslast(), Company.created_at.desc())
    )
    return list(result.scalars().all())


async def summarize_lead_fit_groups(session: AsyncSession, company_ids: list[int] | None = None) -> LeadFitGroupSummary:
    stmt = select(Company.lead_fit_group, func.count(Company.id)).where(Company.deleted_at.is_(None))
    if company_ids:
        stmt = stmt.where(Company.id.in_(company_ids))
    stmt = stmt.group_by(Company.lead_fit_group)
    result = await session.execute(stmt)
    summary = LeadFitGroupSummary()
    for group, count in result.all():
        if not group:
            continue
        setattr(summary, group, count)
        summary.total += count
    return summary
