from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import get_settings
from app.database import async_session_factory
from app.modules.ai.service import prepare_cold_call

router = Router(name="ai")


@router.message(Command("prepare_call"))
async def prepare_call(message: Message) -> None:
    raw_id = (message.text or "").replace("/prepare_call", "", 1).strip()
    if not raw_id.isdigit():
        await message.answer("Формат: /prepare_call 12")
        return
    await message.answer("Готовлю звонок...")
    async with async_session_factory() as session:
        result = await prepare_cold_call(session, int(raw_id))
    await message.answer(result or "Компания не найдена.")


@router.message(F.text == "AI-подготовка к звонку")
async def prepare_call_help(message: Message) -> None:
    await message.answer("Введите /prepare_call и ID компании, например: /prepare_call 12")


@router.message(Command("ai_settings"))
async def ai_settings(message: Message) -> None:
    settings = get_settings()
    await message.answer(
        f"AI_PROVIDER={settings.ai_provider}\n"
        f"OPENROUTER_MODEL={settings.openrouter_model}\n"
        f"OLLAMA_BASE_URL={settings.ollama_base_url}\n"
        f"OLLAMA_MODEL={settings.ollama_model}"
    )
