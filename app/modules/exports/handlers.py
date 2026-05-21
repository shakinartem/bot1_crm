from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.database import async_session_factory
from app.modules.ai.service import generate_mini_audit
from app.modules.crm.handoff import build_consultation_handoff_payload
from app.modules.crm.keyboards import CANCEL_TEXT, flow_menu, main_menu
from app.modules.crm.service import (
    build_company_consultation_package,
    get_company_full_context,
    get_latest_proposal_draft,
    save_proposal_draft,
)
from app.modules.exports.keyboards import (
    consultation_package_markup,
    export_menu_markup,
    export_priority_markup,
    handoff_preview_markup,
    mini_audit_markup,
)
from app.modules.exports.service import (
    ExportFilters,
    export_companies_to_csv,
    export_company_markdown,
    export_handoff_payload_json,
    export_text_artifact,
)
from app.modules.exports.states import ExportStates
from app.utils.telegram import send_long_message_or_file

router = Router(name="exports")


@router.message(F.text == "📤 Экспорт")
@router.message(F.text == "Экспорт")
async def export_root(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Выберите вариант экспорта компаний.", reply_markup=export_menu_markup())


@router.callback_query(F.data == "export:root")
async def export_root_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not callback.message:
        await callback.answer("Не удалось открыть экспорт.", show_alert=True)
        return
    await _safe_edit_message(callback.message, "Выберите вариант экспорта компаний.", reply_markup=export_menu_markup())
    await callback.answer()


@router.callback_query(F.data == "export:menu")
async def export_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Главное меню CRM.", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "export:prompt:city")
async def export_prompt_city(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ExportStates.waiting_for_city)
    if callback.message:
        await callback.message.answer("Введите город для экспорта.", reply_markup=flow_menu())
    await callback.answer()


@router.callback_query(F.data == "export:prompt:source")
async def export_prompt_source(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ExportStates.waiting_for_source)
    if callback.message:
        await callback.message.answer("Введите источник для экспорта.", reply_markup=flow_menu())
    await callback.answer()


@router.callback_query(F.data == "export:prompt:priority")
async def export_prompt_priority(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось выбрать приоритет.", show_alert=True)
        return
    await _safe_edit_message(callback.message, "Выберите приоритет для экспорта.", reply_markup=export_priority_markup())
    await callback.answer()


@router.message(ExportStates.waiting_for_city)
async def export_city_value(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip() == CANCEL_TEXT:
        await state.clear()
        await message.answer("Экспорт отменён.", reply_markup=main_menu())
        return

    filters = ExportFilters(city=(message.text or "").strip())
    await state.clear()
    await _send_export(message, filters, "город")


@router.message(ExportStates.waiting_for_source)
async def export_source_value(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip() == CANCEL_TEXT:
        await state.clear()
        await message.answer("Экспорт отменён.", reply_markup=main_menu())
        return

    filters = ExportFilters(source=(message.text or "").strip())
    await state.clear()
    await _send_export(message, filters, "источник")


@router.callback_query(F.data.startswith("export:run:"))
async def export_run_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось запустить экспорт.", show_alert=True)
        return

    parts = callback.data.split(":")
    filters = ExportFilters()
    filter_label = "все компании"
    if parts[2] == "all":
        filter_label = "все компании"
    elif parts[2] == "status":
        filters.status = parts[3]
        filter_label = f"status={parts[3]}"
    elif parts[2] == "priority":
        filters.priority = parts[3]
        filter_label = f"priority={parts[3]}"

    await callback.answer()
    await _send_export(callback.message, filters, filter_label)


@router.callback_query(F.data.startswith("consult:package:"))
async def consultation_package_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось собрать пакет.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        package = await build_company_consultation_package(session, company_id)

    if not package:
        await callback.answer("Компания не найдена.", show_alert=True)
        return

    await callback.answer("Пакет консультации готов.")
    file_path = await send_long_message_or_file(
        callback.message,
        package["text"],
        file_name=f"company_{company_id}_consultation_preview.txt",
        caption=package["title"],
    )
    if file_path:
        await callback.message.answer(package["title"], reply_markup=consultation_package_markup(company_id))
    else:
        await callback.message.answer("Доступные действия:", reply_markup=consultation_package_markup(company_id))


@router.callback_query(F.data.startswith("consult:mini_audit:"))
async def consultation_mini_audit_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось подготовить мини-аудит.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        audit = await generate_mini_audit(session, company_id)
        if audit:
            await save_proposal_draft(session, company_id, audit, created_by="mini_audit")

    if not audit:
        await callback.answer("Компания не найдена.", show_alert=True)
        return

    await callback.answer("Мини-аудит сгенерирован.")
    await send_long_message_or_file(
        callback.message,
        audit,
        file_name=f"mini_audit_company_{company_id}.txt",
        caption="Черновик мини-аудита готов",
    )
    await callback.message.answer("Что сделать с черновиком дальше?", reply_markup=mini_audit_markup(company_id))


@router.callback_query(F.data.startswith("audit:copy:"))
async def audit_copy_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть текст.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        proposal = await get_latest_proposal_draft(session, company_id)

    if not proposal:
        await callback.answer("Сначала сгенерируйте мини-аудит.", show_alert=True)
        return

    await callback.answer("Отправляю текст для копирования.")
    await send_long_message_or_file(
        callback.message,
        proposal.summary or "",
        file_name=f"mini_audit_copy_company_{company_id}.txt",
        caption="Текст мини-аудита",
    )


@router.callback_query(F.data.startswith("audit:save:"))
async def audit_save_callback(callback: CallbackQuery) -> None:
    await callback.answer("Черновик уже сохранён в историю компании.", show_alert=True)


@router.callback_query(F.data.startswith("audit:export:"))
async def audit_export_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось экспортировать мини-аудит.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        proposal = await get_latest_proposal_draft(session, company_id)

    if not proposal or not proposal.summary:
        await callback.answer("Сначала сгенерируйте мини-аудит.", show_alert=True)
        return

    result = export_text_artifact(
        company_id=company_id,
        prefix="mini_audit",
        content=proposal.summary,
        extension=".txt",
    )
    await callback.message.answer_document(
        FSInputFile(result.file_path),
        caption=f"Файл сохранён: {result.filename}",
    )
    await callback.answer("TXT-экспорт готов.")


@router.callback_query(F.data.startswith("consult:export_company:"))
async def consultation_export_company_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось экспортировать компанию.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        result = await export_company_markdown(session, company_id)

    if not result:
        await callback.answer("Компания не найдена.", show_alert=True)
        return

    await callback.message.answer_document(
        FSInputFile(result.file_path),
        caption=f"📤 Экспортировано: {result.filename}",
    )
    await callback.answer("Markdown-пакет отправлен.")


@router.callback_query(F.data.startswith("consult:handoff:"))
async def consultation_handoff_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось подготовить handoff.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        payload = await build_consultation_handoff_payload(session, company_id)
        company = await get_company_full_context(session, company_id)

    if not payload or not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return

    preview = _render_handoff_preview(company.name, payload)
    await callback.answer("Передача подготовлена.")
    await callback.message.answer(preview, reply_markup=handoff_preview_markup(company_id))


@router.callback_query(F.data.startswith("handoff:export:"))
async def handoff_export_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось экспортировать payload.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        result = await export_handoff_payload_json(session, company_id)

    if not result:
        await callback.answer("Компания не найдена.", show_alert=True)
        return

    await callback.message.answer_document(
        FSInputFile(result.file_path),
        caption=f"JSON сохранён: {result.filename}",
    )
    await callback.answer("Payload JSON отправлен.")


async def _send_export(message: Message, filters: ExportFilters, filter_label: str) -> None:
    async with async_session_factory() as session:
        result = await export_companies_to_csv(session, filters)

    await message.answer_document(
        FSInputFile(result.file_path),
        caption=(
            "📤 Экспорт готов\n"
            f"Компаний выгружено: {result.total_exported}\n"
            f"Фильтр: {filter_label}\n"
            f"Путь: {result.file_path}"
        ),
    )


def _render_handoff_preview(company_name: str, payload: dict) -> str:
    decision_makers = payload.get("decision_makers", [])
    contacts = payload.get("contacts", [])
    interactions = payload.get("recent_interactions", [])
    tasks = payload.get("open_tasks", [])
    sales_context = payload.get("sales_context", {})

    lines = [
        "🚀 Передача в БОТ 2 подготовлена",
        "",
        f"Клиника: {company_name}",
        f"Статус: {sales_context.get('status_label') or payload['company'].get('status_label')}",
        f"ЛПР: {len(decision_makers)}",
        f"Контакты: {len(contacts)}",
        f"Последние касания: {len(interactions)}",
        f"Открытые задачи: {len(tasks)}",
        f"Рекомендованный следующий шаг: {sales_context.get('recommended_next_step') or 'нет'}",
        "",
        "Интеграция пока в режиме draft_only.",
        "На следующем этапе подключим реальный API БОТ 2.",
    ]
    return "\n".join(lines)


async def _safe_edit_message(message: Message, text: str, *, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await message.edit_reply_markup(reply_markup=reply_markup)
