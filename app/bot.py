import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import get_settings
from app.database import create_db_schema
from app.modules.ai.handlers import router as ai_router
from app.modules.calls.handlers import router as calls_router
from app.modules.crm.handlers import router as crm_router
from app.modules.exports.handlers import router as exports_router
from app.modules.imports.handlers import router as imports_router


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required to start Telegram bot")

    settings.storage_path.mkdir(parents=True, exist_ok=True)
    for child in ("calls", "imports", "companies", "exports"):
        (settings.storage_path / child).mkdir(parents=True, exist_ok=True)
    await create_db_schema()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(crm_router)
    dp.include_router(exports_router)
    dp.include_router(imports_router)
    dp.include_router(ai_router)
    dp.include_router(calls_router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
