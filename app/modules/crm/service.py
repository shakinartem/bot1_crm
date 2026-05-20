from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.crm.constants import CompanyStatus, InteractionType
from app.modules.crm.models import Company, DecisionMaker, LeadInteraction, Task
from app.modules.crm.schemas import CompanyCreate, DecisionMakerCreate


async def create_company(session: AsyncSession, payload: CompanyCreate) -> Company:
    company = Company(**payload.model_dump(mode="json"))
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
            selectinload(Company.interactions),
            selectinload(Company.tasks),
            selectinload(Company.calls),
        )
    )
    return result.scalar_one_or_none()


async def search_companies(session: AsyncSession, query: str, limit: int = 10) -> list[Company]:
    pattern = f"%{query}%"
    result = await session.execute(
        select(Company)
        .where(or_(Company.name.ilike(pattern), Company.phone.ilike(pattern), Company.inn.ilike(pattern), Company.website.ilike(pattern)))
        .order_by(Company.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def add_decision_maker(session: AsyncSession, payload: DecisionMakerCreate) -> DecisionMaker:
    dm = DecisionMaker(**payload.model_dump())
    session.add(dm)
    await session.commit()
    await session.refresh(dm)
    return dm


async def add_interaction(
    session: AsyncSession,
    company_id: int,
    interaction_type: str,
    summary: str | None = None,
    result: str | None = None,
    next_step: str | None = None,
) -> LeadInteraction:
    interaction = LeadInteraction(company_id=company_id, type=interaction_type, summary=summary, result=result, next_step=next_step)
    session.add(interaction)
    await session.commit()
    await session.refresh(interaction)
    return interaction


async def update_call_result(session: AsyncSession, company_id: int, result: str) -> Company | None:
    company = await get_company(session, company_id)
    if not company:
        return None

    status_by_result = {
        "недозвон": CompanyStatus.NO_ANSWER.value,
        "отказ": CompanyStatus.REFUSED.value,
        "интересно": CompanyStatus.INTERESTED.value,
        "перезвонить": CompanyStatus.CALL_PLANNED.value,
        "назначена консультация": CompanyStatus.CONSULTATION_SCHEDULED.value,
    }
    company.status = status_by_result.get(result, company.status)
    session.add(company)

    interaction = LeadInteraction(
        company_id=company_id,
        type=InteractionType.CALL.value,
        summary=f"Результат звонка: {result}",
        result=result,
        next_step="Провести консультацию" if result == "назначена консультация" else None,
    )
    session.add(interaction)

    if result == "назначена консультация":
        session.add(
            Task(
                company_id=company_id,
                title="Провести консультацию",
                description="Клиент передан в сценарий консультации.",
                due_date=datetime.utcnow() + timedelta(days=1),
            )
        )

    await session.commit()
    await session.refresh(company)
    return company


def format_company_card(company: Company) -> str:
    socials = "\n".join(
        item
        for item in [
            f"VK: {company.vk_url}" if company.vk_url else "",
            f"Instagram: {company.instagram_url}" if company.instagram_url else "",
            f"Telegram: {company.telegram_url}" if company.telegram_url else "",
            f"Другое: {company.other_socials}" if company.other_socials else "",
        ]
        if item
    )
    dms = "\n".join(f"- {dm.full_name}, {dm.role or 'роль не указана'} {dm.phone or ''}" for dm in company.decision_makers) or "нет"
    calls = "\n".join(f"- {call.created_at:%Y-%m-%d}: {call.manager_result or 'без результата'}" for call in company.calls) or "нет"
    interactions = "\n".join(f"- {i.created_at:%Y-%m-%d}: {i.summary or i.type}" for i in company.interactions) or "нет"
    tasks = "\n".join(f"- {task.title}: {task.status}" for task in company.tasks) or "нет"

    return (
        f"<b>{company.name}</b>\n"
        f"Статус: {company.status}\n"
        f"Телефон: {company.phone or 'нет'}\n"
        f"Сайт: {company.website or 'нет'}\n"
        f"Адрес: {company.address or 'нет'}\n"
        f"Рейтинг: {company.rating or 'нет'} | Отзывы: {company.reviews_count or 0}\n"
        f"Соцсети:\n{socials or 'нет'}\n\n"
        f"ЛПР:\n{dms}\n\n"
        f"Заметки: {company.notes or 'нет'}\n\n"
        f"Звонки:\n{calls}\n\n"
        f"Взаимодействия:\n{interactions}\n\n"
        f"Задачи:\n{tasks}"
    )
