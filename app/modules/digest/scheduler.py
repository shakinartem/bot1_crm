from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Bot

from app.config import get_settings
from app.database import async_session_factory
from app.modules.digest.service import build_daily_digest
from app.modules.digest.settings import get_due_digest_settings, mark_digest_sent

logger = logging.getLogger(__name__)


class DigestScheduler:
    def __init__(self) -> None:
        self._stopped = False

    async def run(self, bot: Bot) -> None:
        while not self._stopped:
            try:
                await self._tick(bot)
            except Exception:
                logger.exception("Digest scheduler tick failed")
            await asyncio.sleep(60)

    def stop(self) -> None:
        self._stopped = True

    async def _tick(self, bot: Bot) -> None:
        now = datetime.now()
        async with async_session_factory() as session:
            due_settings = await get_due_digest_settings(
                session,
                now=now,
                admin_user_ids=get_settings().admin_id_list,
            )

            for item in due_settings:
                digest = await build_daily_digest(session, manager_id=item.telegram_user_id)
                try:
                    await bot.send_message(item.telegram_user_id, _render_scheduler_digest(digest))
                except Exception:
                    logger.exception("Failed to send digest to user %s", item.telegram_user_id)
                    continue
                await mark_digest_sent(session, item, sent_at=now)


def _render_scheduler_digest(digest) -> str:
    return (
        f"🗓 План дня — {digest.date}\n\n"
        f"🔴 Просроченные задачи: {len(digest.overdue_tasks)}\n"
        f"🟡 Задачи на сегодня: {len(digest.today_tasks)}\n"
        f"🔥 Горячие лиды: {len(digest.hot_leads)}\n"
        f"🧊 Давно без касаний: {len(digest.stale_leads)}\n\n"
        f"🎯 Рекомендация:\n{digest.recommendation}"
    )
