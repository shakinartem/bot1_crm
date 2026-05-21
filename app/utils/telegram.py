from __future__ import annotations

from pathlib import Path

from aiogram.types import FSInputFile, Message

from app.config import get_settings


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
