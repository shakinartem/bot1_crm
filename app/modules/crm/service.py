from datetime import datetime, timedelta
from html import escape

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.crm.constants import CompanyStatus, InteractionResult, InteractionType, TaskStatus
from app.modules.crm.models import Company, ContactPoint, DecisionMaker, FollowUpTask, LeadInteraction
from app.modules.crm.schemas import (
    CompanyCreate,
    CompanyUpdate,
    ContactPointCreate,
    DecisionMakerCreate,
    FollowUpTaskCreate,
    FollowUpTaskUpdate,
    InteractionCreate,
)


async def create_company(session: AsyncSession, payload: CompanyCreate) -> Company:
    company = Company(**payload.model_dump())
    session.add(company)
    await session.commit()
    await session.refresh(company)
    return company


async def list_companies(session: AsyncSession, limit: int = 20, offset: int = 0) -> list[Company]:
    result = await session.execute(select(Company).order_by(Company.created_at.desc()).limit(limit).offset(offset))
    return list(result.scalars().all())


async def get_company(session: AsyncSession, company_id: int) -> Company | None:
    result = await session.execute(
        select(Company)
        .where(Company.id == company_id)
        .options(
            selectinload(Company.decision_makers),
            selectinload(Company.contacts),
            selectinload(Company.interactions),
            selectinload(Company.tasks),
            selectinload(Company.calls),
        )
    )
    return result.scalar_one_or_none()


async def update_company(session: AsyncSession, company_id: int, payload: CompanyUpdate) -> Company | None:
    company = await get_company(session, company_id)
    if not company:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    session.add(company)
    await session.commit()
    await session.refresh(company)
    return company


async def delete_company(session: AsyncSession, company_id: int) -> bool:
    company = await get_company(session, company_id)
    if not company:
        return False
    await session.delete(company)
    await session.commit()
    return True


async def search_companies(session: AsyncSession, query: str, limit: int = 10) -> list[Company]:
    pattern = f"%{query}%"
    result = await session.execute(
        select(Company)
        .outerjoin(DecisionMaker)
        .where(
            or_(
                Company.name.ilike(pattern),
                Company.legal_name.ilike(pattern),
                Company.phone.ilike(pattern),
                Company.inn.ilike(pattern),
                Company.website.ilike(pattern),
                Company.city.ilike(pattern),
                DecisionMaker.full_name.ilike(pattern),
            )
        )
        .order_by(Company.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().unique().all())


async def add_decision_maker(session: AsyncSession, payload: DecisionMakerCreate) -> DecisionMaker:
    dm = DecisionMaker(**payload.model_dump())
    session.add(dm)
    await session.commit()
    await session.refresh(dm)
    return dm


async def list_decision_makers(session: AsyncSession, company_id: int) -> list[DecisionMaker]:
    result = await session.execute(
        select(DecisionMaker).where(DecisionMaker.company_id == company_id).order_by(DecisionMaker.is_primary.desc())
    )
    return list(result.scalars().all())


async def add_contact_point(session: AsyncSession, payload: ContactPointCreate) -> ContactPoint:
    contact = ContactPoint(**payload.model_dump())
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


async def list_contact_points(session: AsyncSession, company_id: int) -> list[ContactPoint]:
    result = await session.execute(
        select(ContactPoint).where(ContactPoint.company_id == company_id).order_by(ContactPoint.is_primary.desc())
    )
    return list(result.scalars().all())


async def add_interaction(session: AsyncSession, payload: InteractionCreate) -> LeadInteraction:
    data = payload.model_dump()
    interaction = LeadInteraction(**data, next_step=data.get("next_action"))
    session.add(interaction)
    await session.commit()
    await session.refresh(interaction)
    return interaction


async def list_interactions(session: AsyncSession, company_id: int) -> list[LeadInteraction]:
    result = await session.execute(
        select(LeadInteraction).where(LeadInteraction.company_id == company_id).order_by(LeadInteraction.created_at.desc())
    )
    return list(result.scalars().all())


async def create_task(session: AsyncSession, payload: FollowUpTaskCreate) -> FollowUpTask:
    data = payload.model_dump()
    task = FollowUpTask(**data, due_date=data.get("due_at"))
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def list_tasks(session: AsyncSession, status: str | None = None) -> list[FollowUpTask]:
    stmt = (
        select(FollowUpTask)
        .options(selectinload(FollowUpTask.company))
        .order_by(FollowUpTask.due_at.asc().nulls_last(), FollowUpTask.created_at.desc())
    )
    if status:
        stmt = stmt.where(FollowUpTask.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_task(session: AsyncSession, task_id: int, payload: FollowUpTaskUpdate) -> FollowUpTask | None:
    result = await session.execute(select(FollowUpTask).where(FollowUpTask.id == task_id))
    task = result.scalar_one_or_none()
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


async def update_call_result(session: AsyncSession, company_id: int, result: str) -> Company | None:
    company = await get_company(session, company_id)
    if not company:
        return None

    normalized = result.strip().lower()
    status_by_result = {
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
    }
    company.status = status_by_result.get(normalized, company.status)
    session.add(company)

    consultation_planned = company.status == CompanyStatus.CONSULTATION_PLANNED.value
    interaction = LeadInteraction(
        company_id=company_id,
        type=InteractionType.CALL.value,
        summary=f"Результат звонка: {result}",
        result=_interaction_result_for_call(normalized),
        next_action="Провести консультацию" if consultation_planned else None,
        next_step="Провести консультацию" if consultation_planned else None,
    )
    session.add(interaction)

    if consultation_planned:
        due_at = datetime.utcnow() + timedelta(days=1)
        session.add(
            FollowUpTask(
                company_id=company_id,
                title="Провести консультацию",
                description="Клиент готов к консультации. Передать в следующий сценарий.",
                due_at=due_at,
                due_date=due_at,
            )
        )

    await session.commit()
    await session.refresh(company)
    return company


def _interaction_result_for_call(value: str) -> str:
    mapping = {
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
    }
    return mapping.get(value, InteractionResult.OTHER.value)


def format_company_card(company: Company) -> str:
    dms = (
        "\n".join(
            f"- {escape(dm.full_name)}, {escape(dm.role or 'роль не указана')} {escape(dm.phone or '')}".rstrip()
            for dm in company.decision_makers
        )
        or "нет"
    )
    contacts = "\n".join(f"- {escape(contact.type)}: {escape(contact.value)}" for contact in company.contacts) or "нет"
    last_interaction = escape(company.interactions[0].summary) if company.interactions and company.interactions[0].summary else "нет"
    next_task = next((task for task in company.tasks if task.status == TaskStatus.OPEN.value), None)
    next_action = escape(next_task.title) if next_task else "нет"

    return (
        f"<b>{escape(company.name)}</b>\n"
        f"Юридическое название: {escape(company.legal_name or 'нет')}\n"
        f"ИНН: {escape(company.inn or 'нет')}\n"
        f"Город: {escape(company.city or 'нет')}\n"
        f"Адрес: {escape(company.address or 'нет')}\n"
        f"Телефон: {escape(company.phone or 'нет')}\n"
        f"Сайт: {escape(company.website or 'нет')}\n"
        f"Статус: {escape(company.status)}\n"
        f"Приоритет: {escape(company.priority)}\n"
        f"ЛПР:\n{dms}\n"
        f"Контакты:\n{contacts}\n"
        f"Последнее касание: {last_interaction}\n"
        f"Следующее действие: {next_action}\n"
        f"Заметки: {escape(company.notes or 'нет')}"
    )
