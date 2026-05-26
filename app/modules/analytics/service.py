from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.modules.analytics.schemas import (
    AnalyticsExportResult,
    CityAnalyticsItem,
    ColdBaseItem,
    FunnelAnalyticsRead,
    LeadScoreRead,
    SourceAnalyticsItem,
)
from app.modules.analytics.scoring import calculate_lead_score
from app.modules.crm.constants import CompanyStatus, TaskStatus
from app.modules.crm.models import Company, FollowUpTask, LeadInteraction


STATUS_ORDER = [
    CompanyStatus.NEW.value,
    CompanyStatus.RESEARCH_NEEDED.value,
    CompanyStatus.PREPARED.value,
    CompanyStatus.CALL_PLANNED.value,
    CompanyStatus.CALLED.value,
    CompanyStatus.NO_ANSWER.value,
    CompanyStatus.INTERESTED.value,
    CompanyStatus.CONSULTATION_PLANNED.value,
    CompanyStatus.PROPOSAL_SENT.value,
    CompanyStatus.DEAL_WON.value,
    CompanyStatus.DEAL_LOST.value,
    CompanyStatus.DO_NOT_CONTACT.value,
]

CLOSED_STATUSES = {
    CompanyStatus.DEAL_WON.value,
    CompanyStatus.DEAL_LOST.value,
    CompanyStatus.DO_NOT_CONTACT.value,
}

ANALYTICS_EXPORT_TYPES = {"funnel", "sources", "cities", "scores", "cold_base"}


@dataclass(slots=True)
class AnalyticsFilters:
    status: str | None = None
    source: str | None = None
    city: str | None = None
    limit: int | None = None


async def build_funnel_analytics(
    session: AsyncSession,
    *,
    status: str | None = None,
    source: str | None = None,
    city: str | None = None,
) -> FunnelAnalyticsRead:
    companies = await _load_companies(session, AnalyticsFilters(status=status, source=source, city=city))
    counts = {code: 0 for code in STATUS_ORDER}
    for company in companies:
        counts[company.status] = counts.get(company.status, 0) + 1

    return FunnelAnalyticsRead(
        total_companies=len(companies),
        new_count=counts[CompanyStatus.NEW.value],
        research_needed_count=counts[CompanyStatus.RESEARCH_NEEDED.value],
        prepared_count=counts[CompanyStatus.PREPARED.value],
        call_planned_count=counts[CompanyStatus.CALL_PLANNED.value],
        called_count=counts[CompanyStatus.CALLED.value],
        no_answer_count=counts[CompanyStatus.NO_ANSWER.value],
        interested_count=counts[CompanyStatus.INTERESTED.value],
        consultation_planned_count=counts[CompanyStatus.CONSULTATION_PLANNED.value],
        proposal_sent_count=counts[CompanyStatus.PROPOSAL_SENT.value],
        deal_won_count=counts[CompanyStatus.DEAL_WON.value],
        deal_lost_count=counts[CompanyStatus.DEAL_LOST.value],
        do_not_contact_count=counts[CompanyStatus.DO_NOT_CONTACT.value],
        new_to_interested_conversion=_conversion(
            counts[CompanyStatus.NEW.value],
            counts[CompanyStatus.INTERESTED.value],
        ),
        interested_to_consultation_conversion=_conversion(
            counts[CompanyStatus.INTERESTED.value],
            counts[CompanyStatus.CONSULTATION_PLANNED.value],
        ),
        consultation_to_proposal_conversion=_conversion(
            counts[CompanyStatus.CONSULTATION_PLANNED.value],
            counts[CompanyStatus.PROPOSAL_SENT.value],
        ),
        proposal_to_won_conversion=_conversion(
            counts[CompanyStatus.PROPOSAL_SENT.value],
            counts[CompanyStatus.DEAL_WON.value],
        ),
    )


async def build_source_analytics(
    session: AsyncSession,
    *,
    status: str | None = None,
    source: str | None = None,
    city: str | None = None,
    limit: int = 50,
    best_first: bool = True,
) -> list[SourceAnalyticsItem]:
    companies = await _load_companies(session, AnalyticsFilters(status=status, source=source, city=city))
    buckets: dict[str, list[Company]] = {}
    for company in companies:
        bucket = company.source or "Unknown"
        buckets.setdefault(bucket, []).append(company)

    items = [_build_source_item(name, bucket_companies) for name, bucket_companies in buckets.items()]
    items.sort(
        key=lambda item: (
            -(item.conversion_to_interested or 0),
            -item.deal_won_count,
            -item.total_companies,
        ) if best_first else (
            item.conversion_to_interested or 0,
            item.deal_won_count,
            -item.total_companies,
        )
    )
    return items[:limit]


async def build_city_analytics(
    session: AsyncSession,
    *,
    status: str | None = None,
    source: str | None = None,
    city: str | None = None,
    limit: int = 50,
    best_first: bool = True,
) -> list[CityAnalyticsItem]:
    companies = await _load_companies(session, AnalyticsFilters(status=status, source=source, city=city))
    buckets: dict[tuple[str, str | None], list[Company]] = {}
    for company in companies:
        city_name = company.city or company.region or "Unknown"
        buckets.setdefault((city_name, company.region), []).append(company)

    items = [_build_city_item(city_name, region, bucket_companies) for (city_name, region), bucket_companies in buckets.items()]
    items.sort(
        key=lambda item: (
            -(item.conversion_to_interested or 0),
            -item.deal_won_count,
            item.overdue_tasks,
        ) if best_first else (
            -item.overdue_tasks,
            -(item.stale_leads),
            item.conversion_to_interested or 0,
        )
    )
    return items[:limit]


async def list_lead_scores(
    session: AsyncSession,
    *,
    limit: int = 20,
    status: str | None = None,
    source: str | None = None,
    city: str | None = None,
    grade: str | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
    without_tasks: bool = False,
    overdue_only: bool = False,
) -> list[LeadScoreRead]:
    companies = await _load_companies(session, AnalyticsFilters(status=status, source=source, city=city))
    items = [build_company_lead_score(company) for company in companies]
    filtered = [
        item
        for item in items
        if (grade is None or item.grade == grade)
        and (min_score is None or item.score >= min_score)
        and (max_score is None or item.score <= max_score)
        and (not without_tasks or not item.has_open_task)
        and (not overdue_only or item.has_overdue_task)
    ]
    filtered.sort(
        key=lambda item: (
            -item.score,
            0 if item.has_overdue_task else 1,
            0 if item.has_open_task else 1,
            item.company_name.lower(),
        )
    )
    return filtered[:limit]


async def get_company_lead_score(session: AsyncSession, company_id: int) -> LeadScoreRead | None:
    company = await _load_company(session, company_id)
    if not company:
        return None
    return build_company_lead_score(company)


def build_company_lead_score(company: Company) -> LeadScoreRead:
    return calculate_lead_score(_company_context(company))


def format_company_card_with_score(company: Company) -> str:
    from app.modules.crm.service import format_company_card

    score = build_company_lead_score(company)
    lines = [
        format_company_card(company),
        "",
        "🔥 <b>Скоринг:</b>",
        f"Оценка: {score.score}/100 — {escape(score.grade)}",
        "Почему:",
        *[f"- {escape(reason)}" for reason in score.reasons[:3]],
    ]
    if score.risks:
        lines.extend(
            [
                "Риски:",
                *[f"- {escape(risk)}" for risk in score.risks[:2]],
            ]
        )
    lines.extend(
        [
            "Следующий шаг:",
            escape(score.next_best_action),
        ]
    )
    if score.proposal_recommendation:
        lines.append(escape(score.proposal_recommendation))
    return "\n".join(lines)


async def build_cold_base(
    session: AsyncSession,
    *,
    limit: int = 50,
    source: str | None = None,
    city: str | None = None,
) -> list[ColdBaseItem]:
    scores = await list_lead_scores(
        session,
        limit=200,
        source=source,
        city=city,
        max_score=24,
    )
    items: list[ColdBaseItem] = []
    for item in scores:
        if item.status not in {CompanyStatus.NEW.value, CompanyStatus.RESEARCH_NEEDED.value}:
            continue
        if item.has_open_task:
            continue
        missing_fields = _missing_fields(item)
        if not missing_fields and item.last_interaction_result:
            continue
        items.append(
            ColdBaseItem(
                company_id=item.company_id,
                company_name=item.company_name,
                city=item.city,
                status=item.status,
                score=item.score,
                missing_fields=missing_fields,
                next_best_action=item.next_best_action,
                reasons=item.risks[:3] or item.reasons[:2],
            )
        )
    items.sort(key=lambda item: (item.score, item.company_name.lower()))
    return items[:limit]


async def export_analytics_csv(
    session: AsyncSession,
    export_type: str,
    *,
    limit: int = 200,
    status: str | None = None,
    source: str | None = None,
    city: str | None = None,
    grade: str | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
) -> AnalyticsExportResult:
    export_key = export_type.lower().replace("-", "_")
    if export_key not in ANALYTICS_EXPORT_TYPES:
        raise ValueError(f"Unsupported analytics export type: {export_type}")

    rows: list[dict[str, object]]
    if export_key == "funnel":
        funnel = await build_funnel_analytics(session, status=status, source=source, city=city)
        rows = [funnel.model_dump()]
    elif export_key == "sources":
        rows = [item.model_dump() for item in await build_source_analytics(session, status=status, source=source, city=city, limit=limit)]
    elif export_key == "cities":
        rows = [item.model_dump() for item in await build_city_analytics(session, status=status, source=source, city=city, limit=limit)]
    elif export_key == "scores":
        rows = [
            item.model_dump()
            for item in await list_lead_scores(
                session,
                limit=limit,
                status=status,
                source=source,
                city=city,
                grade=grade,
                min_score=min_score,
                max_score=max_score,
            )
        ]
    else:
        rows = [item.model_dump() for item in await build_cold_base(session, limit=limit, source=source, city=city)]

    analytics_dir = _analytics_exports_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{export_key}_{timestamp}.csv"
    file_path = analytics_dir / filename
    fieldnames = list(rows[0].keys()) if rows else ["empty"]

    with file_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        if rows:
            writer.writerows(rows)

    return AnalyticsExportResult(
        export_type=export_key,
        file_path=str(file_path),
        filename=filename,
        total_exported=len(rows),
        created_at=datetime.now().isoformat(),
    )


async def _load_companies(session: AsyncSession, filters: AnalyticsFilters) -> list[Company]:
    stmt = (
        select(Company)
        .options(
            selectinload(Company.decision_makers),
            selectinload(Company.contacts),
            selectinload(Company.interactions),
            selectinload(Company.tasks),
        )
        .order_by(Company.created_at.desc())
    )
    if filters.status:
        stmt = stmt.where(Company.status == filters.status)
    if filters.source:
        stmt = stmt.where(Company.source.ilike(f"%{filters.source}%"))
    if filters.city:
        stmt = stmt.where(Company.city.ilike(f"%{filters.city}%"))
    if filters.limit:
        stmt = stmt.limit(filters.limit)

    result = await session.execute(stmt)
    return list(result.scalars().unique().all())


async def _load_company(session: AsyncSession, company_id: int) -> Company | None:
    result = await session.execute(
        select(Company)
        .where(Company.id == company_id)
        .options(
            selectinload(Company.decision_makers),
            selectinload(Company.contacts),
            selectinload(Company.interactions),
            selectinload(Company.tasks),
        )
    )
    return result.scalar_one_or_none()


def _company_context(company: Company) -> dict:
    now = datetime.now()
    interactions = sorted(company.interactions, key=lambda item: item.created_at or datetime.min, reverse=True)
    tasks = [task for task in company.tasks if task.status == TaskStatus.OPEN.value]
    last_interaction = interactions[0] if interactions else None
    days_without_interaction = None
    if last_interaction and last_interaction.created_at:
        days_without_interaction = max((now.date() - last_interaction.created_at.date()).days, 0)
    elif company.created_at:
        days_without_interaction = max((now.date() - company.created_at.date()).days, 0)

    return {
        "company_id": company.id,
        "company_name": company.name,
        "city": company.city,
        "source": company.source,
        "status": company.status,
        "priority": company.priority,
        "has_website": bool((company.website or "").strip()),
        "has_phone": bool((company.phone or "").strip()),
        "has_decision_maker": bool(company.decision_makers),
        "has_city": bool((company.city or "").strip()),
        "has_notes_or_history": bool((company.notes or "").strip() or company.interactions),
        "last_interaction_result": last_interaction.result if last_interaction else None,
        "days_without_interaction": days_without_interaction,
        "has_task_today": any(task.due_at and task.due_at.date() == now.date() for task in tasks),
        "has_open_task": bool(tasks),
        "has_overdue_task": any(task.due_at and task.due_at < now for task in tasks),
    }


def _build_source_item(source: str, companies: list[Company]) -> SourceAnalyticsItem:
    total = len(companies)
    open_tasks = sum(_open_task_count(company) for company in companies)
    interactions_total = sum(len(company.interactions) for company in companies)
    interested = sum(1 for company in companies if company.status == CompanyStatus.INTERESTED.value)
    consultation = sum(1 for company in companies if company.status == CompanyStatus.CONSULTATION_PLANNED.value)
    proposal = sum(1 for company in companies if company.status == CompanyStatus.PROPOSAL_SENT.value)
    won = sum(1 for company in companies if company.status == CompanyStatus.DEAL_WON.value)
    lost = sum(1 for company in companies if company.status == CompanyStatus.DEAL_LOST.value)
    new_count = sum(1 for company in companies if company.status == CompanyStatus.NEW.value)
    return SourceAnalyticsItem(
        source=source,
        total_companies=total,
        new_count=new_count,
        interested_count=interested,
        consultation_planned_count=consultation,
        proposal_sent_count=proposal,
        deal_won_count=won,
        deal_lost_count=lost,
        open_tasks=open_tasks,
        interactions_total=interactions_total,
        conversion_to_interested=_conversion(total, interested),
        conversion_to_consultation=_conversion(total, consultation),
        conversion_to_won=_conversion(total, won),
    )


def _build_city_item(city: str, region: str | None, companies: list[Company]) -> CityAnalyticsItem:
    total = len(companies)
    interested = sum(1 for company in companies if company.status == CompanyStatus.INTERESTED.value)
    consultation = sum(1 for company in companies if company.status == CompanyStatus.CONSULTATION_PLANNED.value)
    proposal = sum(1 for company in companies if company.status == CompanyStatus.PROPOSAL_SENT.value)
    won = sum(1 for company in companies if company.status == CompanyStatus.DEAL_WON.value)
    lost = sum(1 for company in companies if company.status == CompanyStatus.DEAL_LOST.value)
    open_tasks = sum(_open_task_count(company) for company in companies)
    stale_leads = sum(1 for company in companies if _is_stale(company))
    overdue_tasks = sum(_overdue_task_count(company) for company in companies)
    return CityAnalyticsItem(
        city=city,
        region=region,
        total_companies=total,
        interested_count=interested,
        consultation_planned_count=consultation,
        proposal_sent_count=proposal,
        deal_won_count=won,
        deal_lost_count=lost,
        open_tasks=open_tasks,
        stale_leads=stale_leads,
        overdue_tasks=overdue_tasks,
        conversion_to_interested=_conversion(total, interested),
        conversion_to_consultation=_conversion(total, consultation),
    )


def _open_task_count(company: Company) -> int:
    return sum(1 for task in company.tasks if task.status == TaskStatus.OPEN.value)


def _overdue_task_count(company: Company) -> int:
    now = datetime.now()
    return sum(
        1
        for task in company.tasks
        if task.status == TaskStatus.OPEN.value and task.due_at and task.due_at < now
    )


def _is_stale(company: Company, *, threshold_days: int = 7) -> bool:
    if company.status in CLOSED_STATUSES:
        return False
    interactions = sorted(company.interactions, key=lambda item: item.created_at or datetime.min, reverse=True)
    anchor = interactions[0].created_at if interactions and interactions[0].created_at else company.created_at
    if not anchor:
        return False
    return (datetime.now().date() - anchor.date()).days >= threshold_days


def _conversion(base: int, target: int) -> float | None:
    if base <= 0:
        return None
    return round((target / base) * 100, 1)


def _missing_fields(item: LeadScoreRead) -> list[str]:
    missing: list[str] = []
    risk_text = " ".join(item.risks).lower()
    if "телефон" in risk_text:
        missing.append("телефон")
    if "сайта" in risk_text or "сайт" in risk_text:
        missing.append("сайт")
    if "лпр" in risk_text:
        missing.append("ЛПР")
    if "контекста" in risk_text:
        missing.append("история касаний")
    return missing


def _analytics_exports_dir() -> Path:
    export_dir = get_settings().storage_path / "exports" / "analytics"
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir
