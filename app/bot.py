import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import get_settings
from app.database import create_db_schema
from app.modules.analytics.handlers import router as analytics_router
from app.modules.ai.handlers import router as ai_router
from app.modules.calls.handlers import router as calls_router
from app.modules.crm.handlers import router as crm_router
from app.modules.digest.handlers import router as digest_router
from app.modules.digest.scheduler import DigestScheduler
from app.modules.enrichment.handlers import router as enrichment_router
from app.modules.exports.handlers import router as exports_router
from app.modules.imports.handlers import router as imports_router
from app.modules.intelligence.handlers import router as intelligence_router
from app.modules.legal_discovery.handlers import router as legal_discovery_router
from app.modules.proposals.handlers import router as proposals_router
from app.modules.research_queue.handlers import router as research_queue_router


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required to start Telegram bot")

    settings.storage_path.mkdir(parents=True, exist_ok=True)
    for child in ("calls", "imports", "companies", "exports", "proposals"):
        (settings.storage_path / child).mkdir(parents=True, exist_ok=True)
    await create_db_schema()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(crm_router)
    dp.include_router(legal_discovery_router)
    dp.include_router(enrichment_router)
    dp.include_router(intelligence_router)
    dp.include_router(research_queue_router)
    dp.include_router(analytics_router)
    dp.include_router(proposals_router)
    dp.include_router(digest_router)
    dp.include_router(exports_router)
    dp.include_router(imports_router)
    dp.include_router(ai_router)
    dp.include_router(calls_router)

    scheduler = DigestScheduler()
    scheduler_task = asyncio.create_task(scheduler.run(bot))
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.stop()
        scheduler_task.cancel()
        await asyncio.gather(scheduler_task, return_exceptions=True)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
