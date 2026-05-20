from aiogram import F, Router
from aiogram.types import Message

from app.database import async_session_factory
from app.modules.calls.service import save_call_record

router = Router(name="calls")


@router.message(F.text == "Загрузить звонок")
async def upload_call_help(message: Message) -> None:
    await message.answer("Отправьте аудио/voice с подписью: call:ID, например call:12")


@router.message(F.voice | F.audio | F.document)
async def upload_call(message: Message) -> None:
    caption = (message.caption or "").strip().lower()
    if not caption.startswith("call:") or not caption.replace("call:", "", 1).strip().isdigit():
        return
    company_id = int(caption.replace("call:", "", 1).strip())
    file = message.voice or message.audio or message.document
    bot_file = await message.bot.get_file(file.file_id)
    content = await message.bot.download_file(bot_file.file_path)
    filename = getattr(file, "file_name", None) or f"{file.file_id}.ogg"
    async with async_session_factory() as session:
        record = await save_call_record(session, company_id, filename, content.read())
    await message.answer(f"Запись сохранена: #{record.id}\n{record.transcript}")
