import re
from datetime import datetime, timedelta
from html import escape

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.crm.constants import (
    COMPANY_STATUS_LABELS,
    CONTACT_TYPE_LABELS,
    INTERACTION_RESULT_LABELS,
    INTERACTION_TYPE_LABELS,
    PRIORITY_LABELS,
    CompanyStatus,
    InteractionResult,
    InteractionType,
    LeadPriority,
    TaskStatus,
)
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
    await session.refresh(company)
    return company


async def list_companies(session: AsyncSession, limit: int = 20, offset: int = 0) -> list[Company]:
    result = await session.execute(
        select(Company)
        .order_by(Company.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
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
    await session.refresh(interaction)
    return interaction


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


async def create_note_interaction(
    session: AsyncSession,
    company_id: int,
    summary: str,
    *,
    created_by: str | None = "telegram",
    next_action: str | None = None,
) -> LeadInteraction:
    payload = InteractionCreate(
        company_id=company_id,
        type=InteractionType.NOTE,
        summary=summary,
        next_action=next_action,
        created_by=created_by,
    )
    return await add_interaction(session, payload)


async def change_company_status(
    session: AsyncSession,
    company_id: int,
    new_status: str,
    *,
    created_by: str | None = "telegram",
) -> Company | None:
    company = await get_company(session, company_id)
    if not company:
        return None

    old_status = company.status
    company.status = new_status
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
        )
    )
    await session.commit()
    await session.refresh(company)
    return company


async def create_task(session: AsyncSession, payload: FollowUpTaskCreate) -> FollowUpTask:
    data = payload.model_dump()
    task = FollowUpTask(**data, due_date=data.get("due_at"))
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def create_company_task(
    session: AsyncSession,
    company_id: int,
    title: str,
    description: str | None,
    due_at: datetime | None,
    *,
    priority: str = LeadPriority.MEDIUM.value,
) -> FollowUpTask:
    payload = FollowUpTaskCreate(
        company_id=company_id,
        title=title,
        description=description,
        due_at=due_at,
        priority=LeadPriority(priority),
    )
    return await create_task(session, payload)


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


async def get_task(session: AsyncSession, task_id: int) -> FollowUpTask | None:
    result = await session.execute(
        select(FollowUpTask)
        .where(FollowUpTask.id == task_id)
        .options(selectinload(FollowUpTask.company))
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


async def complete_task(session: AsyncSession, task_id: int) -> FollowUpTask | None:
    return await update_task(
        session,
        task_id,
        FollowUpTaskUpdate(status=TaskStatus.DONE, completed_at=datetime.utcnow()),
    )


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


def normalize_call_result(value: str) -> str:
    return value.strip().lower()


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
        f"Сайт: {escape(company.website or 'нет')}\n\n"
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
