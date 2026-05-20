from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import get_settings
from app.database import async_session_factory
from app.modules.imports.service import import_companies_from_csv

router = Router(name="imports")


@router.message(Command("import_csv"))
@router.message(F.text == "Импорт CSV")
async def import_csv_help(message: Message) -> None:
    await message.answer("Прикрепите CSV-файл документом с подписью: import_csv")


@router.message(F.document, F.caption == "import_csv")
async def import_csv_file(message: Message) -> None:
    document = message.document
    bot_file = await message.bot.get_file(document.file_id)
    content = await message.bot.download_file(bot_file.file_path)
    text = content.read().decode("utf-8-sig")

    settings = get_settings()
    imports_dir = settings.storage_path / "imports"
    imports_dir.mkdir(parents=True, exist_ok=True)
    if document.file_name:
        (imports_dir / document.file_name).write_text(text, encoding="utf-8")

    async with async_session_factory() as session:
        report = await import_companies_from_csv(session, text)
    await message.answer(f"Импорт завершен.\nДобавлено: {report['added']}\nПропущено: {report['skipped']}\nОшибки: {len(report['errors'])}")
