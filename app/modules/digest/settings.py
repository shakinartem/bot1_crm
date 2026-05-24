from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.digest.models import DigestSettings


DEFAULT_SEND_TIME = "09:00"
DEFAULT_WEEKDAYS = (0, 1, 2, 3, 4)
DEFAULT_STALE_DAYS = 7


def normalize_send_time(send_time: str) -> str:
    raw = send_time.strip()
    if len(raw) != 5 or raw[2] != ":" or not raw.replace(":", "").isdigit():
        raise ValueError("Time must be in HH:MM format.")

    hours = int(raw[:2])
    minutes = int(raw[3:])
    if hours > 23 or minutes > 59:
        raise ValueError("Time must be in the 00:00-23:59 range.")
    return f"{hours:02d}:{minutes:02d}"


def serialize_weekdays(weekdays: tuple[int, ...] | list[int]) -> str:
    cleaned = sorted({int(day) for day in weekdays if 0 <= int(day) <= 6})
    return ",".join(str(day) for day in cleaned) or ",".join(str(day) for day in DEFAULT_WEEKDAYS)


async def get_or_create_digest_settings(
    session: AsyncSession,
    telegram_user_id: int,
    *,
    default_enabled: bool = False,
) -> DigestSettings:
    result = await session.execute(
        select(DigestSettings).where(DigestSettings.telegram_user_id == telegram_user_id)
    )
    settings = result.scalar_one_or_none()
    if settings:
        return settings

    settings = DigestSettings(
        telegram_user_id=telegram_user_id,
        enabled=default_enabled,
        send_time=DEFAULT_SEND_TIME,
        weekdays=serialize_weekdays(DEFAULT_WEEKDAYS),
        stale_days=DEFAULT_STALE_DAYS,
    )
    session.add(settings)
    await session.commit()
    await session.refresh(settings)
    return settings


async def update_digest_settings(
    session: AsyncSession,
    telegram_user_id: int,
    *,
    enabled: bool | None = None,
    send_time: str | None = None,
    stale_days: int | None = None,
    weekdays: tuple[int, ...] | list[int] | None = None,
    default_enabled: bool = False,
) -> DigestSettings:
    settings = await get_or_create_digest_settings(
        session,
        telegram_user_id,
        default_enabled=default_enabled,
    )

    if enabled is not None:
        settings.enabled = enabled
    if send_time is not None:
        settings.send_time = normalize_send_time(send_time)
    if stale_days is not None:
        settings.stale_days = stale_days
    if weekdays is not None:
        settings.weekdays = serialize_weekdays(weekdays)

    session.add(settings)
    await session.commit()
    await session.refresh(settings)
    return settings


async def ensure_digest_recipients(
    session: AsyncSession,
    telegram_user_ids: list[int],
    *,
    default_enabled: bool = True,
) -> list[DigestSettings]:
    ensured: list[DigestSettings] = []
    for user_id in telegram_user_ids:
        ensured.append(
            await get_or_create_digest_settings(
                session,
                user_id,
                default_enabled=default_enabled,
            )
        )
    return ensured


async def get_due_digest_settings(
    session: AsyncSession,
    *,
    now: datetime,
    admin_user_ids: list[int] | None = None,
) -> list[DigestSettings]:
    if admin_user_ids:
        await ensure_digest_recipients(session, admin_user_ids, default_enabled=True)

    result = await session.execute(
        select(DigestSettings).where(
            DigestSettings.enabled.is_(True),
            DigestSettings.send_time == now.strftime("%H:%M"),
        )
    )
    items = list(result.scalars().all())
    due: list[DigestSettings] = []
    for item in items:
        if now.weekday() not in item.weekdays_tuple:
            continue
        if item.last_sent_at and item.last_sent_at.date() == now.date():
            continue
        due.append(item)
    return due


async def mark_digest_sent(
    session: AsyncSession,
    settings: DigestSettings,
    *,
    sent_at: datetime,
) -> DigestSettings:
    settings.last_sent_at = sent_at
    session.add(settings)
    await session.commit()
    await session.refresh(settings)
    return settings
