from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.config import get_settings
from app.database import async_session_factory
from app.modules.crm.keyboards import main_menu
from app.modules.crm.models import Company
from app.modules.research_queue.keyboards import research_queue_created_markup, research_queue_scope_markup
from app.modules.research_queue.service import create_research_jobs_for_companies, get_queue_status, run_research_batch

router = Router(name="research_queue")


@router.callback_query(F.data == "research_queue:from_last_import")
async def research_from_last_import(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    await _safe_edit_message(
        callback.message,
        "🧠 Запустить research\n\nВыберите объём запуска:",
        reply_markup=research_queue_scope_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("research_queue:scope:"))
async def research_pick_scope(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    scope = callback.data.rsplit(":", 1)[-1]
    data = await state.get_data()
    company_ids = list(data.get("last_legal_import_company_ids") or [])
    async with async_session_factory() as session:
        if scope == "without_website":
            result = await session.execute(
                select(Company.id).where(Company.website.is_(None)).order_by(Company.created_at.desc()).limit(100)
            )
            company_ids = [item[0] for item in result.all()]
        elif scope == "top50":
            result = await session.execute(select(Company.id).order_by(Company.created_at.desc()).limit(50))
            company_ids = [item[0] for item in result.all()]
        elif scope == "last_import_all":
            company_ids = list(data.get("last_legal_import_company_ids") or [])
        jobs = await create_research_jobs_for_companies(session, company_ids)
    await state.update_data(last_research_job_company_ids=company_ids)
    text = (
        "🧠 Очередь research создана\n\n"
        f"Компаний: {len(company_ids)}\n"
        f"Задач создано: {len(jobs)}\n"
        f"Параллельность: {get_settings().research_concurrency}"
    )
    await _safe_edit_message(callback.message, text, reply_markup=research_queue_created_markup())
    await callback.answer("Очередь создана.")


@router.callback_query(F.data == "research_queue:run_batch")
async def research_run_batch(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    await _safe_edit_message(callback.message, "Запускаю batch research, это может занять некоторое время...")
    await run_research_batch(
        async_session_factory,
        concurrency=get_settings().research_concurrency,
        limit=100,
    )
    async with async_session_factory() as session:
        status = await get_queue_status(session)
    text = (
        "🧠 Research завершён\n\n"
        f"Обработано: {status.total}\n"
        f"Success: {status.success}\n"
        f"Blocked/manual: {status.blocked + status.needs_manual_review}\n"
        f"Ошибок: {status.failed}"
    )
    await _safe_edit_message(callback.message, text, reply_markup=research_queue_created_markup())
    await callback.answer("Batch завершён.")


@router.callback_query(F.data == "research_queue:status")
async def research_queue_status(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    async with async_session_factory() as session:
        status = await get_queue_status(session)
    text = (
        "📊 Статус очереди\n\n"
        f"Всего: {status.total}\n"
        f"Pending: {status.pending}\n"
        f"Running: {status.running}\n"
        f"Success: {status.success}\n"
        f"Blocked: {status.blocked}\n"
        f"Manual review: {status.needs_manual_review}\n"
        f"Failed: {status.failed}\n"
        f"Cancelled: {status.cancelled}"
    )
    await _safe_edit_message(callback.message, text, reply_markup=research_queue_created_markup())
    await callback.answer()


@router.callback_query(F.data == "research_queue:cancel")
async def research_queue_cancel(callback: CallbackQuery) -> None:
    await callback.answer("Ок.")
    if callback.message:
        await callback.message.answer("Работа с очередью завершена.", reply_markup=main_menu())


async def _safe_edit_message(message: Message, text: str, *, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await message.edit_reply_markup(reply_markup=reply_markup)
