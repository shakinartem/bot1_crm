from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.constants import LeadPriority, TaskStatus, TouchStage
from app.modules.crm.models import Company, FollowUpTask
from app.modules.crm.schemas import FollowUpTaskRead


TOUCH_PLAN = [
    (TouchStage.TOUCH_1_FIRST_CONTACT, 0, "Первый звонок / первое сообщение"),
    (TouchStage.TOUCH_2_VALUE_MESSAGE, 1, "Сообщение с ценностью"),
    (TouchStage.TOUCH_3_CASE_OR_PROBLEM, 3, "Кейс / разбор ошибки"),
    (TouchStage.TOUCH_4_DIAGNOSTIC_OFFER, 5, "Предложение бесплатной диагностики"),
    (TouchStage.TOUCH_5_FOLLOW_UP, 7, "Follow-up"),
    (TouchStage.TOUCH_6_OBJECTION_HANDLING, 10, "Обработка возражения / альтернативный заход"),
    (TouchStage.TOUCH_7_FINAL_ATTEMPT, 14, "Финальное касание"),
]


async def create_touch_plan_for_company(
    session: AsyncSession,
    company_id: int,
    assigned_user_id: int | None = None,
) -> list[FollowUpTask]:
    company = await session.get(Company, company_id)
    if not company or company.deleted_at is not None:
        raise ValueError("Company not found")
    existing = await get_touch_plan_for_company(session, company_id)
    if existing:
        return existing
    base_date = datetime.utcnow()
    tasks: list[FollowUpTask] = []
    for stage, day_offset, title in TOUCH_PLAN:
        task = FollowUpTask(
            company_id=company_id,
            title=title,
            description=f"7-touch workflow: {stage.value}",
            due_at=base_date + timedelta(days=day_offset),
            due_date=base_date + timedelta(days=day_offset),
            status=TaskStatus.OPEN.value,
            priority=LeadPriority.HIGH.value if day_offset == 0 else LeadPriority.MEDIUM.value,
            interaction_stage=stage.value,
            assigned_user_id=assigned_user_id,
        )
        session.add(task)
        tasks.append(task)
    await session.commit()
    return await get_touch_plan_for_company(session, company_id)


async def get_touch_plan_for_company(session: AsyncSession, company_id: int) -> list[FollowUpTask]:
    result = await session.execute(
        select(FollowUpTask)
        .where(
            FollowUpTask.company_id == company_id,
            FollowUpTask.interaction_stage.is_not(None),
        )
        .order_by(FollowUpTask.due_at.asc().nullslast(), FollowUpTask.id.asc())
    )
    return list(result.scalars().all())
