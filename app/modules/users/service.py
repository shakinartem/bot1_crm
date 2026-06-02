from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.modules.crm.constants import CRMUserRole, TaskStatus
from app.modules.crm.models import CRMUser, Company, FollowUpTask, LeadInteraction
from app.modules.users.schemas import AssignmentResult


@dataclass(slots=True)
class TelegramIdentity:
    id: int
    username: str | None = None
    full_name: str | None = None


def build_display_name(user: CRMUser | None) -> str | None:
    if not user:
        return None
    if user.full_name:
        return user.full_name
    if user.username:
        return f"@{user.username}"
    if user.telegram_user_id:
        return f"tg:{user.telegram_user_id}"
    return f"user #{user.id}"


def extract_telegram_identity(message_or_callback: Any) -> TelegramIdentity | None:
    from_user = getattr(message_or_callback, "from_user", None)
    if from_user is None and getattr(message_or_callback, "message", None) is not None:
        from_user = getattr(message_or_callback.message, "from_user", None)
    if from_user is None:
        return None

    full_name = " ".join(part for part in [getattr(from_user, "first_name", None), getattr(from_user, "last_name", None)] if part).strip() or None
    return TelegramIdentity(
        id=from_user.id,
        username=getattr(from_user, "username", None),
        full_name=full_name,
    )


async def get_user_by_telegram_id(session: AsyncSession, telegram_user_id: int) -> CRMUser | None:
    result = await session.execute(
        select(CRMUser).where(CRMUser.telegram_user_id == telegram_user_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> CRMUser | None:
    result = await session.execute(select(CRMUser).where(CRMUser.id == user_id))
    return result.scalar_one_or_none()


async def list_users(session: AsyncSession, active_only: bool = True) -> list[CRMUser]:
    stmt = select(CRMUser).order_by(CRMUser.created_at.asc(), CRMUser.id.asc())
    if active_only:
        stmt = stmt.where(CRMUser.is_active.is_(True))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_user_role(session: AsyncSession, user_id: int, role: CRMUserRole | str) -> CRMUser | None:
    user = await get_user_by_id(session, user_id)
    if not user:
        return None
    user.role = role.value if isinstance(role, CRMUserRole) else role
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def deactivate_user(session: AsyncSession, user_id: int) -> CRMUser | None:
    user = await get_user_by_id(session, user_id)
    if not user:
        return None
    user.is_active = False
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def touch_user_last_seen(session: AsyncSession, user_id: int) -> CRMUser | None:
    user = await get_user_by_id(session, user_id)
    if not user:
        return None
    user.last_seen_at = datetime.utcnow()
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_or_create_user_from_telegram(session: AsyncSession, telegram_user: Any) -> CRMUser:
    identity = telegram_user if isinstance(telegram_user, TelegramIdentity) else extract_telegram_identity(telegram_user)
    if identity is None:
        raise ValueError("Telegram user identity is required")

    existing = await get_user_by_telegram_id(session, identity.id)
    if existing:
        existing.username = identity.username
        existing.full_name = identity.full_name
        existing.last_seen_at = datetime.utcnow()
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing

    settings = get_settings()
    if not settings.crm_auto_create_users:
        raise ValueError("CRM auto-create users is disabled")

    total_users = await session.scalar(select(func.count(CRMUser.id)))
    role = _resolve_new_user_role(identity.id, total_users or 0)
    user = CRMUser(
        telegram_user_id=identity.id,
        username=identity.username,
        full_name=identity.full_name,
        role=role,
        is_active=True,
        last_seen_at=datetime.utcnow(),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _resolve_new_user_role(telegram_user_id: int, total_users: int) -> str:
    settings = get_settings()
    if total_users == 0:
        return CRMUserRole.OWNER.value
    if telegram_user_id in settings.crm_owner_telegram_id_list:
        return CRMUserRole.OWNER.value
    try:
        return CRMUserRole(settings.default_new_user_role).value
    except ValueError:
        return CRMUserRole.MANAGER.value


async def assign_company_to_user(
    session: AsyncSession,
    company_id: int,
    user_id: int | None,
    actor_user_id: int | None = None,
) -> AssignmentResult:
    company = await session.get(Company, company_id)
    if not company:
        raise ValueError("Company not found")

    assigned_user = await get_user_by_id(session, user_id) if user_id is not None else None
    actor_user = await get_user_by_id(session, actor_user_id) if actor_user_id is not None else None
    if user_id is not None and assigned_user is None:
        raise ValueError("Assigned user not found")

    company.assigned_user_id = user_id
    company.updated_by_user_id = actor_user_id or company.updated_by_user_id
    session.add(company)

    assigned_name = build_display_name(assigned_user)
    actor_name = build_display_name(actor_user) or "system"
    note_summary = (
        f"Компания назначена на {assigned_name or 'не назначен'} пользователем {actor_name}"
    )
    session.add(
        LeadInteraction(
            company_id=company_id,
            type="note",
            summary=note_summary,
            created_by="assignment_service",
            created_by_user_id=actor_user_id,
        )
    )
    await session.commit()
    return AssignmentResult(
        company_id=company_id,
        assigned_user_id=user_id,
        assigned_user_name=assigned_name,
        status="assigned" if user_id is not None else "unassigned",
    )


async def assign_task_to_user(
    session: AsyncSession,
    task_id: int,
    user_id: int | None,
    actor_user_id: int | None = None,
) -> FollowUpTask:
    task = await session.get(FollowUpTask, task_id)
    if not task:
        raise ValueError("Task not found")
    if user_id is not None and await get_user_by_id(session, user_id) is None:
        raise ValueError("Assigned user not found")
    task.assigned_user_id = user_id
    if actor_user_id is not None and task.created_by_user_id is None:
        task.created_by_user_id = actor_user_id
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def get_user_companies(
    session: AsyncSession,
    user_id: int,
    limit: int = 50,
    status: str | None = None,
) -> list[Company]:
    stmt = (
        select(Company)
        .options(selectinload(Company.assigned_user))
        .where(Company.assigned_user_id == user_id)
        .order_by(Company.created_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(Company.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_user_tasks(
    session: AsyncSession,
    user_id: int,
    limit: int = 50,
    only_open: bool = True,
) -> list[FollowUpTask]:
    stmt = (
        select(FollowUpTask)
        .options(selectinload(FollowUpTask.company), selectinload(FollowUpTask.assigned_user))
        .where(FollowUpTask.assigned_user_id == user_id)
        .order_by(FollowUpTask.due_at.asc().nulls_last(), FollowUpTask.created_at.desc())
        .limit(limit)
    )
    if only_open:
        stmt = stmt.where(FollowUpTask.status == TaskStatus.OPEN.value)
    result = await session.execute(stmt)
    return list(result.scalars().all())
