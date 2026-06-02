from __future__ import annotations

from pathlib import Path
from typing import Any

from aiogram.types import CallbackQuery, FSInputFile, Message

from app.config import get_settings
from app.modules.crm.models import CRMUser
from app.modules.users.service import get_or_create_user_from_telegram


def chunk_text(text: str, limit: int = 3500) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    return chunks


async def send_long_message_or_file(
    message: Message,
    text: str,
    *,
    file_name: str,
    caption: str | None = None,
    parse_mode: str | None = None,
    limit: int = 3500,
) -> Path | None:
    if len(text) <= limit:
        for chunk in chunk_text(text, limit=limit):
            await message.answer(chunk, parse_mode=parse_mode)
        return None

    settings = get_settings()
    exports_dir = settings.storage_path / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    file_path = exports_dir / file_name
    file_path.write_text(text, encoding="utf-8")
    await message.answer_document(FSInputFile(file_path), caption=caption)
    return file_path


async def get_current_crm_user(session: Any, message_or_callback: Message | CallbackQuery) -> CRMUser:
    return await get_or_create_user_from_telegram(session, message_or_callback)
