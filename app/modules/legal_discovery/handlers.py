from __future__ import annotations

import csv
from io import StringIO

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.config import get_settings
from app.database import async_session_factory
from app.modules.crm.keyboards import CANCEL_TEXT, flow_menu, main_menu
from app.modules.legal_discovery.keyboards import (
    discovery_after_import_markup,
    discovery_limit_markup,
    discovery_niche_markup,
    discovery_preview_markup,
    discovery_provider_markup,
)
from app.modules.legal_discovery.service import get_legal_discovery_preview, import_legal_discovery_preview, run_legal_discovery_preview

router = Router(name="legal_discovery")


class DiscoveryStates(StatesGroup):
    niche_manual = State()
    city = State()


@router.message(F.text == "🔍 Поиск компаний")
@router.message(F.text == "/legal_discovery")
async def discovery_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🔍 Поиск компаний\n\nВыберите источник:", reply_markup=None)
    await message.answer("Доступные источники:", reply_markup=discovery_provider_markup())


@router.callback_query(F.data.startswith("discovery:provider:"))
async def discovery_pick_provider(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    provider = callback.data.rsplit(":", 1)[-1]
    await state.update_data(discovery_provider=provider)
    await _safe_edit_message(callback.message, "Выберите нишу:", reply_markup=discovery_niche_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("discovery:niche:"))
async def discovery_pick_niche(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    niche = callback.data.split(":", 2)[-1]
    if niche == "manual":
        await state.set_state(DiscoveryStates.niche_manual)
        await callback.message.answer("Введите нишу вручную.", reply_markup=flow_menu())
        await callback.answer()
        return
    await state.update_data(discovery_query=niche)
    await state.set_state(DiscoveryStates.city)
    await callback.message.answer("Введите город или регион одним сообщением.", reply_markup=flow_menu())
    await callback.answer()


@router.message(DiscoveryStates.niche_manual)
async def discovery_niche_manual(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip() == CANCEL_TEXT:
        await state.clear()
        await message.answer("Поиск компаний отменён.", reply_markup=main_menu())
        return
    await state.update_data(discovery_query=(message.text or "").strip())
    await state.set_state(DiscoveryStates.city)
    await message.answer("Введите город или регион одним сообщением.", reply_markup=flow_menu())


@router.message(DiscoveryStates.city)
async def discovery_city_input(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip() == CANCEL_TEXT:
        await state.clear()
        await message.answer("Поиск компаний отменён.", reply_markup=main_menu())
        return
    raw = (message.text or "").strip()
    await state.update_data(discovery_city=raw, discovery_region=None)
    await state.set_state(None)
    await message.answer("Выберите лимит выдачи.", reply_markup=None)
    await message.answer("Лимит:", reply_markup=discovery_limit_markup())


@router.callback_query(F.data.startswith("discovery:limit:"))
async def discovery_run_preview(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    limit = int(callback.data.rsplit(":", 1)[-1])
    data = await state.get_data()
    query = data.get("discovery_query") or "стоматология"
    city = data.get("discovery_city")
    provider = data.get("discovery_provider")
    await _safe_edit_message(callback.message, "Ищу юрлица и собираю preview...")
    async with async_session_factory() as session:
        preview = await run_legal_discovery_preview(
            session,
            query=query,
            city=city,
            region=data.get("discovery_region"),
            limit=limit,
            provider_code=provider,
        )
    await state.update_data(last_discovery_preview_id=preview.preview_id)
    await _safe_edit_message(
        callback.message,
        _render_preview(preview),
        reply_markup=discovery_preview_markup(preview.preview_id),
    )
    await callback.answer("Preview готов.")


@router.callback_query(F.data.startswith("discovery:import:"))
async def discovery_import(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    _, _, preview_id, mode = callback.data.split(":", 3)
    async with async_session_factory() as session:
        result = await import_legal_discovery_preview(session, preview_id, mode)
    await state.update_data(last_legal_import_company_ids=result.added_company_ids)
    text = (
        "Импорт завершён\n\n"
        f"Добавлено: {result.added_count}\n"
        f"Дубликаты: {result.skipped_duplicates}\n"
        f"Неактивные: {result.skipped_inactive}\n"
        f"Слабые данные: {result.skipped_weak}\n"
        f"Ошибки: {result.errors_count}"
    )
    await _safe_edit_message(callback.message, text, reply_markup=discovery_after_import_markup())
    await callback.answer("Импорт выполнен.")


@router.callback_query(F.data.startswith("discovery:export:"))
async def discovery_export(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    preview_id = callback.data.rsplit(":", 1)[-1]
    preview = get_legal_discovery_preview(preview_id)
    if not preview:
        await callback.answer("Preview уже недоступен.", show_alert=True)
        return
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["status", "legal_name", "inn", "ogrn", "city", "address", "warnings"])
    for item in preview.items:
        writer.writerow(
            [
                item.status,
                item.company.legal_name,
                item.company.inn,
                item.company.ogrn,
                item.company.city or "",
                item.company.address or "",
                "; ".join(item.warnings),
            ]
        )
    data = buffer.getvalue().encode("utf-8")
    file = BufferedInputFile(data, filename=f"legal_discovery_preview_{preview.preview_id[:8]}.csv")
    await callback.message.answer_document(file, caption="Preview CSV")
    await callback.answer("CSV экспортирован.")


@router.callback_query(F.data == "discovery:cancel")
async def discovery_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено.")
    if callback.message:
        await callback.message.answer("Поиск компаний отменён.", reply_markup=main_menu())


def _render_preview(preview) -> str:
    lines = [
        "🔍 Поиск компаний завершён",
        "",
        f"Найдено юрлиц: {preview.total_found}",
        f"Активных: {preview.active_count}",
        f"Неактивных: {preview.inactive_count}",
        f"Новые для CRM: {preview.new_count}",
        f"Дубли в CRM: {preview.duplicate_count}",
        f"Слабые данные: {preview.weak_count}",
        "",
        "Первые результаты:",
    ]
    for index, item in enumerate(preview.items[:5], start=1):
        lines.append(
            f"{index}. {item.company.legal_name} — ИНН {item.company.inn} — {item.company.status or 'unknown'} — {item.company.city or 'город не указан'}"
        )
    return "\n".join(lines)


async def _safe_edit_message(message: Message, text: str, *, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await message.edit_reply_markup(reply_markup=reply_markup)
