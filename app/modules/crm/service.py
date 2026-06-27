import re
from datetime import datetime, timedelta
from html import escape

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.crm.constants import (
    BOT2_READY_STATUS,
    BOT2_RESULT_TO_COMPANY_STATUS,
    BOT2_RESULT_TO_INTERACTION_RESULT,
    COMPANY_STATUS_LABELS,
    CONTACT_TYPE_LABELS,
    INTERACTION_RESULT_LABELS,
    INTERACTION_TYPE_LABELS,
    PRIORITY_LABELS,
    CompanyStatus,
    ContactType,
    InteractionResult,
    InteractionType,
    LeadPriority,
    TaskStatus,
)
from app.modules.crm.models import AuditLog, Company, ContactPoint, DecisionMaker, FollowUpTask, LeadInteraction
from app.modules.crm.schemas import (
    Bot2AssignmentContext,
    Bot2CompanyContext,
    Bot2ConsultationContextRead,
    Bot2ConsultationResultCreate,
    Bot2ContactContext,
    Bot2DecisionMakerContext,
    Bot2InteractionContext,
    Bot2SalesIntelligenceContext,
    Bot2TaskContext,
    CitySummary,
    CompanyCreate,
    CompanyManualUpdate,
    RegionSummary,
    CompanyUpdate,
    ContactPointCreate,
    DecisionMakerCreate,
    FollowUpTaskCreate,
    FollowUpTaskUpdate,
    InteractionCreate,
)
from app.modules.users.service import build_display_name
from app.modules.legal_discovery.checko_parser import is_real_checko_profile_url
from app.modules.research.phone_parser import normalize_phone_ru


CALL_RESULT_STATUS_MAP = {
    "недозвон": CompanyStatus.NO_ANSWER.value,
    "no_answer": CompanyStatus.NO_ANSWER.value,
    "отказ": CompanyStatus.DEAL_LOST.value,
    "rejected": CompanyStatus.DEAL_LOST.value,
    "интересно": CompanyStatus.INTERESTED.value,
    "interested": CompanyStatus.INTERESTED.value,
    "перезвонить": CompanyStatus.CALL_PLANNED.value,
    "callback_requested": CompanyStatus.CALL_PLANNED.value,
    "назначена консультация": CompanyStatus.CONSULTATION_PLANNED.value,
    "consultation_booked": CompanyStatus.CONSULTATION_PLANNED.value,
    "запросили кп": CompanyStatus.PROPOSAL_SENT.value,
    "proposal_requested": CompanyStatus.PROPOSAL_SENT.value,
    "сделка": CompanyStatus.DEAL_WON.value,
    "deal_won": CompanyStatus.DEAL_WON.value,
}

CALL_RESULT_INTERACTION_MAP = {
    "недозвон": InteractionResult.NO_ANSWER.value,
    "no_answer": InteractionResult.NO_ANSWER.value,
    "отказ": InteractionResult.REJECTED.value,
    "rejected": InteractionResult.REJECTED.value,
    "интересно": InteractionResult.INTERESTED.value,
    "interested": InteractionResult.INTERESTED.value,
    "перезвонить": InteractionResult.CALLBACK_REQUESTED.value,
    "callback_requested": InteractionResult.CALLBACK_REQUESTED.value,
    "назначена консультация": InteractionResult.CONSULTATION_BOOKED.value,
    "consultation_booked": InteractionResult.CONSULTATION_BOOKED.value,
    "запросили кп": InteractionResult.PROPOSAL_REQUESTED.value,
    "proposal_requested": InteractionResult.PROPOSAL_REQUESTED.value,
    "сделка": InteractionResult.DEAL_WON.value,
    "deal_won": InteractionResult.DEAL_WON.value,
}

CALL_RESULT_NEXT_ACTION_MAP = {
    "no_answer": "Перезвонить позже",
    "callback_requested": "Перезвонить позже",
    "interested": "Продолжить диалог с клиникой",
    "consultation_booked": "Подготовить консультацию",
    "proposal_requested": "Подготовить и отправить КП",
    "deal_won": "Передать клиента в следующий сценарий",
}


async def create_company(session: AsyncSession, payload: CompanyCreate) -> Company:
    company = Company(**payload.model_dump())
    session.add(company)
    await session.commit()
    return await get_company(session, company.id) or company


async def list_companies(
    session: AsyncSession,
    limit: int = 20,
    offset: int = 0,
    *,
    status: str | None = None,
    city: str | None = None,
    priority: str | None = None,
) -> list[Company]:
    stmt = select(Company).order_by(Company.created_at.desc()).limit(limit).offset(offset)
    stmt = stmt.where(Company.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Company.status == status)
    if city:
        stmt = stmt.where(Company.city == city)
    if priority:
        stmt = stmt.where(Company.priority == priority)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_companies(
    session: AsyncSession,
    *,
    status: str | None = None,
    city: str | None = None,
    priority: str | None = None,
) -> int:
    stmt = select(func.count(Company.id)).where(Company.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Company.status == status)
    if city:
        stmt = stmt.where(Company.city == city)
    if priority:
        stmt = stmt.where(Company.priority == priority)
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def count_all_companies(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(Company.id)))
    return int(result.scalar_one() or 0)


async def count_deleted_companies(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(Company.id)).where(Company.deleted_at.is_not(None)))
    return int(result.scalar_one() or 0)


async def get_company_regions(session: AsyncSession) -> list[RegionSummary]:
    result = await session.execute(
        select(
            Company.region,
            func.count(Company.id),
            func.sum(case((Company.status.not_in([CompanyStatus.DEAL_LOST.value, CompanyStatus.DO_NOT_CONTACT.value]), 1), else_=0)),
            func.sum(case((Company.phone.is_not(None), 1), else_=0)),
            func.sum(case((Company.website.is_not(None), 1), else_=0)),
        )
        .where(Company.deleted_at.is_(None), Company.region.is_not(None), Company.region != "")
        .group_by(Company.region)
        .order_by(func.count(Company.id).desc(), Company.region.asc())
    )
    return [
        RegionSummary(region=region, total=total, active=active, with_phone=with_phone, with_website=with_website)
        for region, total, active, with_phone, with_website in result.all()
    ]


async def get_company_cities(session: AsyncSession, region: str | None = None) -> list[CitySummary]:
    stmt = (
        select(
            Company.city,
            Company.region,
            func.count(Company.id),
            func.sum(case((Company.status.not_in([CompanyStatus.DEAL_LOST.value, CompanyStatus.DO_NOT_CONTACT.value]), 1), else_=0)),
            func.sum(case((Company.phone.is_not(None), 1), else_=0)),
            func.sum(case((Company.website.is_not(None), 1), else_=0)),
        )
        .where(Company.deleted_at.is_(None), Company.city.is_not(None), Company.city != "")
        .group_by(Company.city, Company.region)
        .order_by(func.count(Company.id).desc(), Company.city.asc())
    )
    if region:
        stmt = stmt.where(Company.region == region)
    result = await session.execute(stmt)
    return [
        CitySummary(city=city, region=city_region, total=total, active=active, with_phone=with_phone, with_website=with_website)
        for city, city_region, total, active, with_phone, with_website in result.all()
    ]


async def list_companies_by_region_city(
    session: AsyncSession,
    region: str | None = None,
    city: str | None = None,
    limit: int = 50,
) -> list[Company]:
    stmt = select(Company).order_by(Company.created_at.desc()).limit(limit)
    stmt = stmt.where(Company.deleted_at.is_(None))
    if region:
        stmt = stmt.where(Company.region == region)
    if city:
        stmt = stmt.where(Company.city == city)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_companies_by_status(
    session: AsyncSession,
    status: str,
    *,
    limit: int = 20,
    offset: int = 0,
) -> list[Company]:
    result = await session.execute(
        select(Company)
        .where(Company.deleted_at.is_(None), Company.status == status)
        .order_by(Company.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def list_bot2_consultation_ready(
    session: AsyncSession,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[Company]:
    return await list_companies_by_status(
        session,
        BOT2_READY_STATUS,
        limit=limit,
        offset=offset,
    )


async def get_company(session: AsyncSession, company_id: int) -> Company | None:
    result = await session.execute(
        select(Company)
        .where(Company.id == company_id, Company.deleted_at.is_(None))
        .options(
            selectinload(Company.decision_makers),
            selectinload(Company.contacts),
            selectinload(Company.interactions),
            selectinload(Company.tasks),
            selectinload(Company.calls),
            selectinload(Company.enrichment_snapshots),
            selectinload(Company.intelligence_snapshots),
            selectinload(Company.insight_snapshots),
            selectinload(Company.research_jobs),
            selectinload(Company.assigned_user),
            selectinload(Company.created_by_user),
            selectinload(Company.updated_by_user),
        )
    )
    return result.scalar_one_or_none()


async def get_company_full_context(session: AsyncSession, company_id: int) -> Company | None:
    return await get_company(session, company_id)


async def update_company(session: AsyncSession, company_id: int, payload: CompanyManualUpdate) -> Company | None:
    company = await get_company(session, company_id)
    if not company:
        return None
    await update_company_manual_fields(session, company_id, payload, user_id=None)
    return await get_company(session, company_id)


async def update_company_manual_fields(
    session: AsyncSession,
    company_id: int,
    payload: CompanyManualUpdate,
    user_id: int | None,
) -> Company | None:
    company = await get_company(session, company_id)
    if not company:
        return None

    data = payload.model_dump(exclude_unset=True)
    changes: list[tuple[str, str | None, str | None]] = []

    def track_change(field_name: str, old_value: str | None, new_value: str | None) -> None:
        if (old_value or "") != (new_value or ""):
            changes.append((field_name, old_value, new_value))

    if "display_name" in data:
        new_value = _clean_manual_text(data.pop("display_name"))
        track_change("name", company.name, new_value)
        company.name = new_value or company.name
        if new_value is None:
            raise ValueError("Company name cannot be empty")

    if "name" in data:
        new_value = _clean_manual_text(data.pop("name"))
        if not new_value:
            raise ValueError("Company name cannot be empty")
        track_change("name", company.name, new_value)
        company.name = new_value

    if "legal_name" in data:
        new_value = _clean_manual_text(data.pop("legal_name"))
        track_change("legal_name", company.legal_name, new_value)
        company.legal_name = new_value

    if "city" in data:
        new_value = _clean_manual_text(data.pop("city"))
        track_change("city", company.city, new_value)
        company.city = new_value

    if "region" in data:
        new_value = _clean_manual_text(data.pop("region"))
        track_change("region", company.region, new_value)
        company.region = new_value

    if "address" in data:
        new_value = _clean_manual_text(data.pop("address"))
        track_change("address", company.address, new_value)
        company.address = new_value

    if "website" in data:
        new_value = _normalize_manual_website(data.pop("website"))
        track_change("website", company.website, new_value)
        company.website = new_value

    if "checko_profile_url" in data:
        new_value = _normalize_checko_profile_url(data.pop("checko_profile_url"))
        track_change("checko_profile_url", company.checko_profile_url, new_value)
        company.checko_profile_url = new_value

    if "map_url" in data:
        new_value = _normalize_map_url(data.pop("map_url"))
        track_change("maps_url", company.maps_url, new_value)
        company.maps_url = new_value

    if "maps_url" in data:
        new_value = _normalize_map_url(data.pop("maps_url"))
        track_change("maps_url", company.maps_url, new_value)
        company.maps_url = new_value

    if "phone" in data:
        new_value = _normalize_phone_value(data.pop("phone"))
        track_change("phone", company.phone, new_value)
        company.phone = new_value

    if "status" in data:
        new_value = _normalize_status_value(data.pop("status"))
        if new_value is None:
            raise ValueError("Status cannot be empty")
        track_change("status", company.status, new_value)
        company.status = new_value

    if "priority" in data:
        new_value = _normalize_priority_value(data.pop("priority"))
        if new_value is None:
            raise ValueError("Priority cannot be empty")
        track_change("priority", company.priority, new_value)
        company.priority = new_value

    if "notes" in data:
        new_value = _clean_manual_text(data.pop("notes"))
        track_change("notes", company.notes, new_value)
        company.notes = new_value

    if "email" in data:
        new_value = _normalize_email_value(data.pop("email"))
        old_value = _first_contact_value(company, ContactType.EMAIL.value)
        await _replace_company_contact_value(session, company.id, ContactType.EMAIL.value, new_value, label="manual_edit")
        track_change("email", old_value, new_value)

    if "source" in data:
        new_value = _clean_manual_text(data.pop("source"))
        track_change("source", company.source, new_value)
        company.source = new_value

    if data:
        raise ValueError(f"Unsupported fields: {', '.join(sorted(data))}")

    company.updated_by_user_id = user_id or company.updated_by_user_id
    session.add(company)
    if changes:
        for field_name, old_value, new_value in changes:
            session.add(
                AuditLog(
                    company_id=company.id,
                    user_id=user_id,
                    action="manual_edit",
                    field_name=field_name,
                    old_value=old_value,
                    new_value=new_value,
                )
            )
    await session.commit()
    await session.refresh(company)
    return company


async def delete_company(session: AsyncSession, company_id: int, *, deleted_by_user_id: int | None = None) -> bool:
    company = await get_company(session, company_id)
    if not company:
        return False

    company.deleted_at = datetime.utcnow()
    company.deleted_by_user_id = deleted_by_user_id
    session.add(
        LeadInteraction(
            company_id=company_id,
            type=InteractionType.NOTE.value,
            summary="Company soft deleted",
            created_by="api",
            created_by_user_id=deleted_by_user_id,
        )
    )
    await session.commit()
    return True


async def search_companies(session: AsyncSession, query: str, limit: int = 10) -> list[Company]:
    pattern = f"%{query}%"
    result = await session.execute(
        select(Company)
        .outerjoin(DecisionMaker)
        .outerjoin(ContactPoint)
        .where(
            or_(
                Company.name.ilike(pattern),
                Company.legal_name.ilike(pattern),
                Company.phone.ilike(pattern),
                Company.inn.ilike(pattern),
                Company.website.ilike(pattern),
                Company.city.ilike(pattern),
                DecisionMaker.full_name.ilike(pattern),
                ContactPoint.value.ilike(pattern),
            )
        )
        .where(Company.deleted_at.is_(None))
        .order_by(Company.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().unique().all())


async def add_decision_maker(session: AsyncSession, payload: DecisionMakerCreate) -> DecisionMaker:
    if payload.is_primary:
        existing = await session.execute(
            select(DecisionMaker).where(DecisionMaker.company_id == payload.company_id)
        )
        for item in existing.scalars():
            item.is_primary = False

    dm = DecisionMaker(**payload.model_dump())
    session.add(dm)
    await session.commit()
    await session.refresh(dm)
    return dm


async def list_decision_makers(session: AsyncSession, company_id: int) -> list[DecisionMaker]:
    result = await session.execute(
        select(DecisionMaker)
        .where(DecisionMaker.company_id == company_id)
        .order_by(DecisionMaker.is_primary.desc(), DecisionMaker.created_at.desc())
    )
    return list(result.scalars().all())


async def add_contact_point(session: AsyncSession, payload: ContactPointCreate) -> ContactPoint:
    if payload.is_primary:
        existing = await session.execute(
            select(ContactPoint).where(ContactPoint.company_id == payload.company_id)
        )
        for item in existing.scalars():
            item.is_primary = False

    contact = ContactPoint(**payload.model_dump())
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


async def list_contact_points(session: AsyncSession, company_id: int) -> list[ContactPoint]:
    result = await session.execute(
        select(ContactPoint)
        .where(ContactPoint.company_id == company_id)
        .order_by(ContactPoint.is_primary.desc(), ContactPoint.created_at.desc())
    )
    return list(result.scalars().all())


async def add_interaction(session: AsyncSession, payload: InteractionCreate) -> LeadInteraction:
    data = payload.model_dump()
    interaction = LeadInteraction(**data, next_step=data.get("next_action"))
    session.add(interaction)
    await session.commit()
    result = await session.execute(
        select(LeadInteraction)
        .where(LeadInteraction.id == interaction.id)
        .options(selectinload(LeadInteraction.created_by_user))
    )
    return result.scalar_one()


async def list_interactions(
    session: AsyncSession,
    company_id: int,
    limit: int | None = None,
    offset: int = 0,
) -> list[LeadInteraction]:
    stmt = (
        select(LeadInteraction)
        .where(LeadInteraction.company_id == company_id)
        .order_by(LeadInteraction.created_at.desc())
        .offset(offset)
    )
    if limit is not None:
        stmt = stmt.limit(limit)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_company_last_interactions(
    session: AsyncSession,
    company_id: int,
    *,
    limit: int = 10,
) -> list[LeadInteraction]:
    return await list_interactions(session, company_id, limit=limit)


async def get_company_last_interaction(session: AsyncSession, company_id: int) -> LeadInteraction | None:
    interactions = await get_company_last_interactions(session, company_id, limit=1)
    return interactions[0] if interactions else None


async def create_note_interaction(
    session: AsyncSession,
    company_id: int,
    summary: str,
    *,
    created_by: str | None = "telegram",
    created_by_user_id: int | None = None,
    next_action: str | None = None,
) -> LeadInteraction:
    payload = InteractionCreate(
        company_id=company_id,
        type=InteractionType.NOTE,
        summary=summary,
        next_action=next_action,
        created_by=created_by,
        created_by_user_id=created_by_user_id,
    )
    return await add_interaction(session, payload)


async def save_company_note(
    session: AsyncSession,
    company_id: int,
    text: str,
    *,
    created_by: str | None = "telegram",
    created_by_user_id: int | None = None,
) -> LeadInteraction:
    return await create_note_interaction(
        session,
        company_id,
        text,
        created_by=created_by,
        created_by_user_id=created_by_user_id,
    )


async def save_proposal_draft(
    session: AsyncSession,
    company_id: int,
    text: str,
    *,
    created_by: str | None = "telegram",
    created_by_user_id: int | None = None,
) -> LeadInteraction:
    payload = InteractionCreate(
        company_id=company_id,
        type=InteractionType.PROPOSAL,
        summary=text,
        created_by=created_by,
        created_by_user_id=created_by_user_id,
    )
    return await add_interaction(session, payload)


async def change_company_status(
    session: AsyncSession,
    company_id: int,
    new_status: str,
    *,
    created_by: str | None = "telegram",
    created_by_user_id: int | None = None,
) -> Company | None:
    company = await get_company(session, company_id)
    if not company:
        return None

    old_status = company.status
    company.status = new_status
    company.updated_by_user_id = created_by_user_id or company.updated_by_user_id
    session.add(company)
    session.add(
        LeadInteraction(
            company_id=company_id,
            type=InteractionType.NOTE.value,
            summary=(
                f"Статус изменен: "
                f"{humanize_company_status(old_status)} -> {humanize_company_status(new_status)}"
            ),
            created_by=created_by,
            created_by_user_id=created_by_user_id,
        )
    )
    await session.commit()
    return await get_company(session, company_id)


async def create_task(session: AsyncSession, payload: FollowUpTaskCreate) -> FollowUpTask:
    data = payload.model_dump()
    task = FollowUpTask(**data, due_date=data.get("due_at"))
    session.add(task)
    await session.commit()
    return await get_task(session, task.id) or task


async def apply_bot2_consultation_result(
    session: AsyncSession,
    company_id: int,
    payload: Bot2ConsultationResultCreate,
) -> Company | None:
    company = await get_company(session, company_id)
    if not company:
        return None

    company.status = BOT2_RESULT_TO_COMPANY_STATUS[payload.result]
    session.add(company)

    summary = payload.summary
    if payload.result == "contract_sent":
        summary = (
            f"{payload.summary}\n\n"
            "Рекомендация: Сформировать КП/договор в разделе КП / Договор."
        )
    elif payload.result == "signed":
        summary = "Клиент подписал договор"

    interaction = LeadInteraction(
        company_id=company_id,
        type=InteractionType.CONSULTATION.value,
        result=BOT2_RESULT_TO_INTERACTION_RESULT[payload.result],
        summary=summary,
        created_by=payload.source or "bot2",
    )
    session.add(interaction)

    if payload.result == "thinking":
        due_at = datetime.utcnow() + timedelta(days=3)
        session.add(
            FollowUpTask(
                company_id=company_id,
                title="Повторно связаться после консультации",
                description=payload.summary,
                due_at=due_at,
                due_date=due_at,
                status=TaskStatus.OPEN.value,
                priority=LeadPriority.MEDIUM.value,
            )
        )
    elif payload.result == "contract_sent":
        due_at = datetime.utcnow() + timedelta(days=2)
        session.add(
            FollowUpTask(
                company_id=company_id,
                title="Подготовить/проверить КП и договор",
                description=summary,
                due_at=due_at,
                due_date=due_at,
                status=TaskStatus.OPEN.value,
                priority=LeadPriority.MEDIUM.value,
            )
        )

    await session.commit()
    await session.refresh(company)
    return company


async def create_company_task(
    session: AsyncSession,
    company_id: int,
    title: str,
    description: str | None,
    due_at: datetime | None,
    *,
    priority: str = LeadPriority.MEDIUM.value,
    assigned_user_id: int | None = None,
    created_by_user_id: int | None = None,
) -> FollowUpTask:
    payload = FollowUpTaskCreate(
        company_id=company_id,
        title=title,
        description=description,
        due_at=due_at,
        priority=LeadPriority(priority),
        assigned_user_id=assigned_user_id,
        created_by_user_id=created_by_user_id,
    )
    return await create_task(session, payload)


async def list_tasks(session: AsyncSession, status: str | None = None) -> list[FollowUpTask]:
    stmt = (
        select(FollowUpTask)
        .options(
            selectinload(FollowUpTask.company),
            selectinload(FollowUpTask.assigned_user),
            selectinload(FollowUpTask.created_by_user),
        )
        .order_by(FollowUpTask.due_at.asc().nulls_last(), FollowUpTask.created_at.desc())
    )
    if status:
        stmt = stmt.where(FollowUpTask.status == status)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_company_open_tasks(session: AsyncSession, company_id: int) -> list[FollowUpTask]:
    result = await session.execute(
        select(FollowUpTask)
        .where(
            FollowUpTask.company_id == company_id,
            FollowUpTask.status == TaskStatus.OPEN.value,
        )
        .options(selectinload(FollowUpTask.assigned_user))
        .order_by(FollowUpTask.due_at.asc().nulls_last(), FollowUpTask.created_at.desc())
    )
    return list(result.scalars().all())


async def get_company_next_task(session: AsyncSession, company_id: int) -> FollowUpTask | None:
    tasks = await get_company_open_tasks(session, company_id)
    return tasks[0] if tasks else None


async def get_task(session: AsyncSession, task_id: int) -> FollowUpTask | None:
    result = await session.execute(
        select(FollowUpTask)
        .where(FollowUpTask.id == task_id)
        .options(
            selectinload(FollowUpTask.company),
            selectinload(FollowUpTask.assigned_user),
            selectinload(FollowUpTask.created_by_user),
        )
    )
    return result.scalar_one_or_none()


async def update_task(session: AsyncSession, task_id: int, payload: FollowUpTaskUpdate) -> FollowUpTask | None:
    task = await get_task(session, task_id)
    if not task:
        return None

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
        if field == "due_at":
            task.due_date = value

    if task.status == TaskStatus.DONE.value and task.completed_at is None:
        task.completed_at = datetime.utcnow()

    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def _log_touch_workflow(
    session: AsyncSession,
    company_id: int,
    result: str | None = None,
    comment: str | None = None,
    next_due_at: datetime | None = None,
    user_id: int | None = None,
) -> FollowUpTask | None:
    interaction_result = InteractionResult.OTHER.value
    if result == "contact_made":
        interaction_result = InteractionResult.INTERESTED.value
    elif result == "no_answer":
        interaction_result = InteractionResult.NO_ANSWER.value

    summary = "Касание: "
    if result == "contact_made":
        summary += "Дозвонился / есть контакт"
    elif result == "no_answer":
        summary += "Не дозвонился"
    else:
        summary += "Заметка"
    if comment:
        summary += f". {comment}"

    interaction = LeadInteraction(
        company_id=company_id,
        type=InteractionType.CALL.value if result == "contact_made" else InteractionType.NOTE.value,
        result=interaction_result,
        summary=summary,
        next_action="Следующее касание" if next_due_at else None,
        next_action_at=next_due_at,
        created_by="telegram",
        created_by_user_id=user_id,
    )
    session.add(interaction)

    tasks = await get_company_open_tasks(session, company_id)
    completed = None
    if tasks:
        completed = tasks[0]
        completed.status = TaskStatus.DONE.value
        completed.completed_at = datetime.now()
        session.add(completed)

    next_task = None
    if next_due_at:
        next_task = FollowUpTask(
            company_id=company_id,
            title="Следующее касание (7-touch workflow)",
            description=comment,
            due_at=next_due_at,
            due_date=next_due_at,
            status=TaskStatus.OPEN.value,
            priority=LeadPriority.MEDIUM.value,
            assigned_user_id=user_id,
        )
        session.add(next_task)

    await session.commit()
    return completed or next_task


async def complete_task(session: AsyncSession, task_id: int) -> FollowUpTask | None:
    task = await get_task(session, task_id)
    if not task:
        return None

    task.status = TaskStatus.DONE.value
    task.completed_at = datetime.utcnow()
    session.add(task)
    session.add(
        LeadInteraction(
            company_id=task.company_id,
            type=InteractionType.NOTE.value,
            summary=f"Задача выполнена: {task.title}",
            created_by="telegram",
        )
    )
    await session.commit()
    return await get_task(session, task_id)


async def snooze_task(
    session: AsyncSession,
    task_id: int,
    due_at: datetime,
    *,
    created_by: str | None = "telegram",
) -> FollowUpTask | None:
    task = await get_task(session, task_id)
    if not task:
        return None

    task.due_at = due_at
    task.due_date = due_at
    session.add(task)
    session.add(
        LeadInteraction(
            company_id=task.company_id,
            type=InteractionType.NOTE.value,
            summary=f"Задача перенесена: {task.title} -> {format_datetime(due_at)}",
            created_by=created_by,
        )
    )
    await session.commit()
    return await get_task(session, task_id)


async def get_task_dashboard(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    upcoming_limit: int = 5,
) -> dict[str, list[FollowUpTask]]:
    tasks = await list_tasks(session, status=TaskStatus.OPEN.value)
    now = now or datetime.now()
    today = now.date()

    overdue = [task for task in tasks if task.due_at and task.due_at.date() < today]
    today_tasks = [task for task in tasks if task.due_at and task.due_at.date() == today]
    upcoming = [task for task in tasks if task.due_at and task.due_at.date() > today][:upcoming_limit]

    return {
        "overdue": overdue,
        "today": today_tasks,
        "upcoming": upcoming,
    }


async def get_crm_statistics(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, int | dict[str, int]]:
    now = now or datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = now - timedelta(days=7)

    total_companies = await session.scalar(select(func.count(Company.id)))
    status_rows = await session.execute(
        select(Company.status, func.count(Company.id))
        .group_by(Company.status)
    )
    status_counts = {status: count for status, count in status_rows.all()}

    open_tasks = await session.scalar(
        select(func.count(FollowUpTask.id)).where(FollowUpTask.status == TaskStatus.OPEN.value)
    )
    dashboard = await get_task_dashboard(session, now=now)

    interactions_today = await session.scalar(
        select(func.count(LeadInteraction.id)).where(LeadInteraction.created_at >= today_start)
    )
    interactions_seven_days = await session.scalar(
        select(func.count(LeadInteraction.id)).where(LeadInteraction.created_at >= seven_days_ago)
    )

    return {
        "total_companies": total_companies or 0,
        "status_counts": status_counts,
        "open_tasks": open_tasks or 0,
        "overdue_tasks": len(dashboard["overdue"]),
        "today_tasks": len(dashboard["today"]),
        "touches_today": interactions_today or 0,
        "touches_last_7_days": interactions_seven_days or 0,
    }


async def record_call_result(
    session: AsyncSession,
    company_id: int,
    result: str,
    *,
    comment: str | None = None,
    created_by: str | None = "telegram",
) -> tuple[Company | None, LeadInteraction | None]:
    company = await get_company(session, company_id)
    if not company:
        return None, None

    normalized = normalize_call_result(result)
    company.status = CALL_RESULT_STATUS_MAP.get(normalized, company.status)
    session.add(company)

    result_label = humanize_interaction_result(
        CALL_RESULT_INTERACTION_MAP.get(normalized, InteractionResult.OTHER.value)
    )
    summary = f"Звонок — {result_label}"
    if comment:
        summary = f"{summary}. {comment}"

    next_action = CALL_RESULT_NEXT_ACTION_MAP.get(normalized)
    interaction = LeadInteraction(
        company_id=company_id,
        type=InteractionType.CALL.value,
        summary=summary,
        result=CALL_RESULT_INTERACTION_MAP.get(normalized, InteractionResult.OTHER.value),
        next_action=next_action,
        next_step=next_action,
        created_by=created_by,
    )
    session.add(interaction)

    await session.commit()
    await session.refresh(company)
    await session.refresh(interaction)
    return company, interaction


async def update_call_result(session: AsyncSession, company_id: int, result: str) -> Company | None:
    company, _ = await record_call_result(session, company_id, result)
    return company


async def get_latest_proposal_draft(session: AsyncSession, company_id: int) -> LeadInteraction | None:
    result = await session.execute(
        select(LeadInteraction)
        .where(
            LeadInteraction.company_id == company_id,
            LeadInteraction.type == InteractionType.PROPOSAL.value,
        )
        .order_by(LeadInteraction.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def build_bot2_consultation_context(
    session: AsyncSession,
    company_id: int,
) -> Bot2ConsultationContextRead | None:
    from app.modules.enrichment.service import build_enrichment_context_for_company
    from app.modules.intelligence.service import build_intelligence_context_for_company
    from app.modules.research.service import build_research_context_for_company
    from app.modules.sales_intelligence.service import generate_cold_call_plan, get_latest_sales_intelligence

    company = await get_company(session, company_id)
    if not company:
        return None

    decision_makers = sorted(
        company.decision_makers,
        key=lambda item: (not item.is_primary, item.created_at or datetime.min),
    )
    contacts = sorted(
        company.contacts,
        key=lambda item: (not item.is_primary, item.created_at or datetime.min),
    )
    interactions = sorted(
        company.interactions,
        key=lambda item: item.created_at or datetime.min,
        reverse=True,
    )
    recent_interactions = interactions[:15]
    open_tasks = sorted(
        [task for task in company.tasks if task.status == TaskStatus.OPEN.value],
        key=lambda item: (item.due_at is None, item.due_at or datetime.max, item.created_at or datetime.min),
    )

    latest_proposal = next((item for item in interactions if item.type == InteractionType.PROPOSAL.value), None)
    latest_call_result = next((item for item in interactions if item.type == InteractionType.CALL.value), None)
    latest_interaction_with_action = next((item for item in interactions if item.next_action), None)

    recommended_next_step = "Провести консультацию и уточнить узкое место digital-воронки."
    if open_tasks:
        recommended_next_step = open_tasks[0].title
    elif latest_interaction_with_action and latest_interaction_with_action.next_action:
        recommended_next_step = latest_interaction_with_action.next_action

    last_call_summary = "нет данных"
    if latest_call_result:
        last_call_summary = latest_call_result.summary or humanize_interaction_result(latest_call_result.result or "") or "нет данных"

    company_name = company.name
    city_text = company.city or "не указан"
    status_text = humanize_company_status(company.status)
    priority_text = humanize_priority(company.priority)
    source_text = company.source or "не указан"
    open_task_titles = ", ".join(task.title for task in open_tasks[:3]) if open_tasks else "открытых задач нет"
    notes_text = company.notes or "без заметок"
    sales_summary = (
        f"Компания: {company_name}. "
        f"Город: {city_text}. "
        f"Статус: {status_text}. "
        f"Приоритет: {priority_text}. "
        f"Источник: {source_text}. "
        f"Последняя коммуникация: {last_call_summary}. "
        f"Следующий шаг: {recommended_next_step}. "
        f"Заметки: {notes_text}. "
        f"Открытые задачи: {open_task_titles}."
    )

    latest_sales_intelligence = await get_latest_sales_intelligence(session, company_id)
    cold_call_plan = latest_sales_intelligence.cold_call_plan
    if cold_call_plan is None:
        cold_call_plan = await generate_cold_call_plan(
            session,
            company_id,
            use_ai=False,
            persist=False,
        )
    sales_intelligence = Bot2SalesIntelligenceContext(
        material_score=latest_sales_intelligence.material_score.model_dump(mode="json"),
        closing_criteria=latest_sales_intelligence.closing_criteria.model_dump(mode="json"),
        cold_call_plan_summary=cold_call_plan.copyable_short_script,
        soprano_questions=latest_sales_intelligence.soprano_questions.model_dump(mode="json"),
        first_offer=cold_call_plan.first_offer,
        risks=list(
            dict.fromkeys(
                [
                    *latest_sales_intelligence.material_score.risks[:3],
                    *latest_sales_intelligence.closing_criteria.risks[:3],
                ]
            )
        ),
        generation_mode=cold_call_plan.generation_mode,
    )
    assignment = Bot2AssignmentContext(
        assigned_user_id=company.assigned_user_id,
        assigned_user_name=build_display_name(company.assigned_user),
        assigned_user_role=company.assigned_user.role if company.assigned_user else None,
        created_by_user_id=company.created_by_user_id,
    )

    return Bot2ConsultationContextRead(
        company=Bot2CompanyContext.model_validate(company),
        decision_makers=[Bot2DecisionMakerContext.model_validate(item) for item in decision_makers],
        contacts=[Bot2ContactContext.model_validate(item) for item in contacts],
        recent_interactions=[Bot2InteractionContext.model_validate(item) for item in recent_interactions],
        open_tasks=[Bot2TaskContext.model_validate(item) for item in open_tasks],
        latest_proposal=Bot2InteractionContext.model_validate(latest_proposal) if latest_proposal else None,
        latest_call_result=Bot2InteractionContext.model_validate(latest_call_result) if latest_call_result else None,
        recommended_next_step=recommended_next_step,
        sales_summary=sales_summary,
        assignment=assignment,
        enrichment=await build_enrichment_context_for_company(session, company_id),
        intelligence=await build_intelligence_context_for_company(session, company_id),
        research=await build_research_context_for_company(session, company_id),
        sales_intelligence=sales_intelligence,
    )


async def build_company_consultation_package(session: AsyncSession, company_id: int) -> dict[str, str] | None:
    company = await get_company_full_context(session, company_id)
    if not company:
        return None

    from app.modules.ai.service import prepare_cold_call  # local import to avoid circular dependency

    interactions = await get_company_last_interactions(session, company_id, limit=10)
    next_task = await get_company_next_task(session, company_id)
    latest_proposal = await get_latest_proposal_draft(session, company_id)
    ai_call_prep = await prepare_cold_call(session, company_id)

    next_step = "Уточнить следующий шаг вручную."
    if next_task:
        next_step = next_task.title
        if next_task.due_at:
            next_step = f"{next_step} ({format_datetime(next_task.due_at)})"
    elif interactions and interactions[0].next_action:
        next_step = interactions[0].next_action

    decision_makers_text = "\n".join(
        [
            f"- {dm.full_name}; {dm.role or 'роль не указана'}; "
            f"телефон: {dm.phone or 'нет'}; email: {dm.email or 'нет'}; "
            f"telegram: {dm.telegram or 'нет'}; комментарии: {dm.notes or 'нет'}"
            for dm in company.decision_makers[:10]
        ]
    ) or "- нет"

    contacts_text = "\n".join(
        [
            f"- {humanize_contact_type(contact.type)}: {contact.value}"
            f"{f' ({contact.label})' if contact.label else ''}"
            for contact in company.contacts[:10]
        ]
    ) or "- нет"

    history_text = "\n".join(
        [
            f"- {format_datetime(item.created_at)} | {humanize_interaction_type(item.type)}"
            f"{f' | {humanize_interaction_result(item.result)}' if item.result else ''}"
            f" | {item.summary or 'без комментария'}"
            for item in interactions
        ]
    ) or "- касаний пока нет"

    task_text = (
        f"{next_task.title} ({format_datetime(next_task.due_at) if next_task and next_task.due_at else 'без срока'})"
        if next_task
        else "нет"
    )
    latest_proposal_text = latest_proposal.summary if latest_proposal else "еще не сгенерирован"

    plain_text = (
        f"📦 Пакет консультации: {company.name}\n\n"
        f"1. Данные клиники\n"
        f"- Название: {company.name}\n"
        f"- Юр. название: {company.legal_name or 'нет'}\n"
        f"- ИНН: {company.inn or 'нет'}\n"
        f"- Город: {company.city or 'нет'}\n"
        f"- Адрес: {company.address or 'нет'}\n"
        f"- Сайт: {company.website or 'нет'}\n"
        f"- Телефон: {company.phone or 'нет'}\n"
        f"- Источник: {company.source or 'не указан'}\n\n"
        f"2. ЛПР\n{decision_makers_text}\n\n"
        f"3. Контакты\n{contacts_text}\n\n"
        f"4. История касаний\n{history_text}\n\n"
        f"5. Текущий статус продажи\n"
        f"- Статус: {humanize_company_status(company.status)}\n"
        f"- Приоритет: {humanize_priority(company.priority)}\n"
        f"- Следующая задача: {task_text}\n"
        f"- Заметки менеджера: {company.notes or 'нет'}\n\n"
        f"6. AI-подготовка к звонку\n{ai_call_prep or 'нет'}\n\n"
        f"7. Рекомендация следующего шага\n{next_step}\n\n"
        f"8. Мини-аудит / КП\n{latest_proposal_text}"
    )

    markdown_text = (
        "# Пакет консультации\n\n"
        "## Компания\n"
        f"- Название: {company.name}\n"
        f"- Юр. название: {company.legal_name or 'нет'}\n"
        f"- ИНН: {company.inn or 'нет'}\n"
        f"- Город: {company.city or 'нет'}\n"
        f"- Регион: {company.region or 'нет'}\n"
        f"- Адрес: {company.address or 'нет'}\n"
        f"- Телефон: {company.phone or 'нет'}\n"
        f"- Сайт: {company.website or 'нет'}\n"
        f"- Источник: {company.source or 'не указан'}\n"
        f"- Статус: {humanize_company_status(company.status)}\n"
        f"- Приоритет: {humanize_priority(company.priority)}\n\n"
        f"## ЛПР\n{decision_makers_text}\n\n"
        f"## Контакты\n{contacts_text}\n\n"
        f"## История касаний\n{history_text}\n\n"
        f"## Задачи\n- Следующая задача: {task_text}\n\n"
        f"## AI-подготовка\n{ai_call_prep or 'нет'}\n\n"
        f"## Мини-аудит / КП\n{latest_proposal_text}\n"
    )

    return {
        "title": f"Пакет консультации: {company.name}",
        "text": plain_text,
        "markdown": markdown_text,
        "recommended_next_step": next_step,
        "ai_call_prep": ai_call_prep or "",
        "latest_proposal": latest_proposal_text,
    }


def normalize_call_result(value: str) -> str:
    return value.strip().lower()


def _clean_manual_text(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text or text == "-":
        return None
    return text


def _normalize_phone_value(value: str | None) -> str | None:
    text = _clean_manual_text(value)
    if text is None:
        return None
    normalized = normalize_phone_ru(text)
    if not normalized:
        raise ValueError("Invalid phone number")
    return normalized


def _normalize_email_value(value: str | None) -> str | None:
    text = _clean_manual_text(value)
    if text is None:
        return None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text):
        raise ValueError("Invalid email")
    return text.lower()


def _normalize_manual_website(value: str | None) -> str | None:
    text = _clean_manual_text(value)
    if text is None:
        return None
    from app.modules.research.website_resolver import is_denied_website_url, normalize_website_url

    normalized = normalize_website_url(text)
    if is_denied_website_url(normalized):
        raise ValueError("Denied website URL")
    return normalized


def _normalize_checko_profile_url(value: str | None) -> str | None:
    text = _clean_manual_text(value)
    if text is None:
        return None
    if not is_real_checko_profile_url(text):
        raise ValueError("Invalid Checko profile URL")
    return text


def _normalize_map_url(value: str | None) -> str | None:
    text = _clean_manual_text(value)
    if text is None:
        return None
    normalized = text if "://" in text else f"https://{text}"
    lowered = normalized.lower()
    if any(domain in lowered for domain in ["2gis.ru", "yandex.ru/maps", "yandex.com/maps", "maps.google.com", "google.com/maps"]):
        return normalized
    if "maps" in lowered:
        return normalized
    raise ValueError("Invalid map URL")


def _normalize_status_value(value: str | None) -> str | None:
    text = _clean_manual_text(value)
    if text is None:
        return None
    normalized = text.strip().lower()
    label_to_value = {label.lower(): raw_value for raw_value, label in COMPANY_STATUS_LABELS.items()}
    if normalized in COMPANY_STATUS_LABELS:
        return normalized
    if normalized in label_to_value:
        return label_to_value[normalized]
    raise ValueError("Invalid status")


def _normalize_priority_value(value: str | None) -> str | None:
    text = _clean_manual_text(value)
    if text is None:
        return None
    normalized = text.strip().lower()
    label_to_value = {label.lower(): raw_value for raw_value, label in PRIORITY_LABELS.items()}
    if normalized in PRIORITY_LABELS:
        return normalized
    if normalized in label_to_value:
        return label_to_value[normalized]
    raise ValueError("Invalid priority")


async def _replace_company_contact_value(
    session: AsyncSession,
    company_id: int,
    contact_type: str,
    value: str | None,
    *,
    label: str | None = None,
) -> None:
    result = await session.execute(
        select(ContactPoint).where(ContactPoint.company_id == company_id, ContactPoint.type == contact_type)
    )
    for item in result.scalars().all():
        await session.delete(item)
    if not value:
        return
    session.add(
        ContactPoint(
            company_id=company_id,
            type=contact_type,
            value=value,
            label=label,
            is_primary=True,
        )
    )


def _first_contact_value(company: Company, contact_type: str) -> str | None:
    for contact in company.contacts:
        if contact.type == contact_type:
            return contact.value
    return None


def _build_manual_edit_note(changes: list[tuple[str, str | None, str | None]], *, user_id: int | None) -> str:
    user_part = f" by user_id={user_id}" if user_id is not None else ""
    parts = [f"{field}: {old or '—'} -> {new or '—'}" for field, old, new in changes[:5]]
    return f"Manual edit{user_part}; " + "; ".join(parts)


def _shorten_url(url: str | None, limit: int = 64) -> str:
    value = (url or "").strip()
    if not value:
        return "нет"
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3].rstrip()}..."


def _format_link_section(title: str, items: list[tuple[str, str | None]]) -> str:
    lines = [f"{title}:"]
    visible = [(label, value) for label, value in items if value]
    if not visible:
        lines.append("нет")
        return "\n".join(lines)
    for label, value in visible:
        lines.append(f"- {label}: {_shorten_url(value)}")
    return "\n".join(lines)


def suggest_next_task_title(result: str) -> str:
    normalized = normalize_call_result(result)
    suggestions = {
        "no_answer": "Перезвонить клиенту",
        "callback_requested": "Перезвонить клиенту",
        "interested": "Подготовить следующий контакт",
        "consultation_booked": "Подготовить консультацию",
        "proposal_requested": "Подготовить и отправить КП",
        "deal_won": "Передать клиента в следующий сценарий",
        "rejected": "Зафиксировать отказ и закрыть сделку",
    }
    return suggestions.get(normalized, "Следующее действие по компании")


def parse_due_at_input(value: str, *, now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    raw = value.strip()
    normalized = raw.lower()

    if normalized == "сегодня":
        return now.replace(hour=18, minute=0, second=0, microsecond=0)

    if normalized == "завтра":
        return (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)

    if normalized.startswith("завтра "):
        time_part = normalized.replace("завтра", "", 1).strip()
        hours, minutes = _parse_time_part(time_part)
        return (now + timedelta(days=1)).replace(hour=hours, minute=minutes, second=0, microsecond=0)

    hours_match = re.fullmatch(r"через\s+(\d+)\s+час(?:а|ов)?", normalized)
    if hours_match:
        return now + timedelta(hours=int(hours_match.group(1)))

    try:
        return datetime.strptime(raw, "%d.%m.%Y %H:%M")
    except ValueError as exc:
        raise ValueError(
            "Используйте один из форматов: сегодня, завтра, завтра 12:00, "
            "через 2 часа, 21.05.2026 15:30"
        ) from exc


def format_company_card(company: Company) -> str:
    decision_makers = sorted(
        company.decision_makers,
        key=lambda item: (not item.is_primary, item.created_at or datetime.min),
    )
    contacts = sorted(
        company.contacts,
        key=lambda item: (not item.is_primary, item.created_at or datetime.min),
    )
    interactions = sorted(
        company.interactions,
        key=lambda item: item.created_at or datetime.min,
        reverse=True,
    )
    open_tasks = sorted(
        [task for task in company.tasks if task.status == TaskStatus.OPEN.value],
        key=lambda item: (item.due_at is None, item.due_at or datetime.max),
    )

    lpr_block = (
        "\n".join(
            (
                f"- {escape(dm.full_name)} — "
                f"{escape(dm.role or 'роль не указана')}, "
                f"{escape(dm.phone or dm.email or dm.telegram or 'контакт не указан')}"
            )
            for dm in decision_makers[:5]
        )
        or "— нет"
    )
    contacts_block = (
        "\n".join(
            (
                f"- {escape(humanize_contact_type(contact.type))}: "
                f"{escape(contact.value)}"
                f"{f' ({escape(contact.label)})' if contact.label else ''}"
            )
            for contact in contacts[:5]
        )
        or "— нет"
    )

    latest_interaction = interactions[0] if interactions else None
    latest_interaction_text = "нет"
    if latest_interaction:
        interaction_bits = [humanize_interaction_type(latest_interaction.type)]
        if latest_interaction.result:
            interaction_bits.append(humanize_interaction_result(latest_interaction.result))
        if latest_interaction.created_at:
            interaction_bits.append(format_datetime(latest_interaction.created_at))
        latest_interaction_text = " — ".join(interaction_bits)
        if latest_interaction.summary:
            latest_interaction_text = (
                f"{latest_interaction_text}\n"
                f"{escape(latest_interaction.summary)}"
            )

    next_action_text = "нет"
    if open_tasks:
        next_task = open_tasks[0]
        due_part = f" ({format_datetime(next_task.due_at)})" if next_task.due_at else ""
        next_action_text = f"{escape(next_task.title)}{due_part}"
    elif latest_interaction and latest_interaction.next_action:
        next_action_text = escape(latest_interaction.next_action)

    return (
        f"🏥 <b>Клиника:</b> {escape(company.name)}\n"
        f"Юр. название: {escape(company.legal_name or 'нет')}\n"
        f"ИНН: {escape(company.inn or 'нет')}\n"
        f"Город: {escape(company.city or 'нет')}\n"
        f"Адрес: {escape(company.address or 'нет')}\n"
        f"Телефон: {escape(company.phone or 'нет')}\n"
        f"Email: {escape(next((contact.value for contact in contacts if contact.type == ContactType.EMAIL.value), 'нет'))}\n"
        f"ЛПР телефон: {escape(next((contact.value for contact in contacts if contact.type == ContactType.PHONE.value), 'нет'))}\n"
        f"Сайт компании: {escape(_shorten_url(company.website))}\n"
        f"Checko: {escape(_shorten_url(company.checko_profile_url))}\n"
        f"Карты: {escape(_shorten_url(company.maps_url))}\n\n"
        f"Соцсети: VK={escape(_shorten_url(company.vk_url))}, "
        f"Instagram={escape(_shorten_url(company.instagram_url))}, "
        f"Telegram={escape(_shorten_url(company.telegram_url))}\n\n"
        f"Статус: {escape(humanize_company_status(company.status))}\n"
        f"Приоритет: {escape(humanize_priority(company.priority))}\n"
        f"Источник: {escape(company.source or 'не указан')}\n\n"
        f"👤 <b>ЛПР:</b>\n{lpr_block}\n\n"
        f"📞 <b>Контакты:</b>\n{contacts_block}\n\n"
        f"🕓 <b>Последнее касание:</b>\n{escape(latest_interaction_text)}\n\n"
        f"📌 <b>Следующее действие:</b>\n{next_action_text}\n\n"
        f"📝 <b>Заметки:</b>\n{escape(company.notes or 'нет')}"
    )


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "без даты"
    return value.strftime("%d.%m.%Y %H:%M")


def humanize_company_status(value: str) -> str:
    return COMPANY_STATUS_LABELS.get(value, value)


def humanize_priority(value: str) -> str:
    return PRIORITY_LABELS.get(value, value)


def humanize_contact_type(value: str) -> str:
    return CONTACT_TYPE_LABELS.get(value, value)


def humanize_interaction_type(value: str) -> str:
    return INTERACTION_TYPE_LABELS.get(value, value)


def humanize_interaction_result(value: str) -> str:
    return INTERACTION_RESULT_LABELS.get(value, value)


def _parse_time_part(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value)
    if not match:
        raise ValueError("Время должно быть в формате HH:MM.")

    hours = int(match.group(1))
    minutes = int(match.group(2))
    if hours > 23 or minutes > 59:
        raise ValueError("Время должно быть в диапазоне 00:00-23:59.")
    return hours, minutes
