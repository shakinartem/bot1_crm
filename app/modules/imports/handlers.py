from __future__ import annotations

from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database import async_session_factory
from app.modules.crm.keyboards import main_menu
from app.modules.crm.telegram_ux import (
    TELEGRAM_TEXT_LIMIT,
    clamp_text,
    format_lead_group_count_lines,
    render_lead_fit_block,
)
from app.modules.imports.csv_company_import import (
    import_companies_from_csv,
    preview_csv,
)
from app.modules.imports.keyboards import import_preview_markup, import_report_markup
from app.modules.imports.states import ImportCsvStates
from app.modules.lead_fit.service import summarize_lead_fit_groups

router = Router(name="imports")


MODE_LABELS = {
    "create_only": "Только новые",
    "update_existing": "Обновить существующие",
    "upsert": "Создать/обновить",
}


@router.message(Command("import_csv"))
@router.message(F.text == "📥 Импорт CSV")
async def import_csv_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ImportCsvStates.awaiting_file)
    await message.answer(
        "📥 <b>Импорт компаний из CSV</b>\n\n"
        "Отправьте CSV-файл документом.\n\n"
        "Поддерживаются разделители: comma (,), semicolon (;), tab.\n"
        "Кодировки: UTF-8, UTF-8 BOM, Windows-1251.\n\n"
        "Обязательна колонка с названием компании:\n"
        "name / company / название / организация\n\n"
        "Дополнительные колонки:\n"
        "• ИНН, ОГРН — для дедупликации\n"
        "• телефон, email, website\n"
        "• адрес, город, регион\n"
        "• checko_profile_url, yandex_maps_url\n"
        "• статус, приоритет, заметки, источник\n\n"
        "Бот сначала покажет предпросмотр, потом предложит выбрать режим импорта.",
        reply_markup=main_menu(),
        parse_mode="HTML",
    )


@router.message(ImportCsvStates.awaiting_file, F.document)
async def import_csv_file(message: Message, state: FSMContext) -> None:
    """Receive CSV file, show preview, ask for import mode."""
    document = message.document
    bot_file = await message.bot.get_file(document.file_id)
    content = await message.bot.download_file(bot_file.file_path)
    file_bytes = content.read()

    # Generate preview
    preview = preview_csv(file_bytes)

    file_name = document.file_name or "import.csv"

    await state.clear()
    await state.set_state(ImportCsvStates.awaiting_commit)
    await state.update_data(
        csv_file_bytes=file_bytes,
        csv_file_name=file_name,
        import_mode="upsert",
        import_preview=preview,
    )

    text = _render_preview_text(preview, import_mode="upsert", file_name=file_name)
    await message.answer(
        text,
        reply_markup=import_preview_markup("upsert"),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("import:mode:"))
async def import_mode_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось обновить режим импорта.", show_alert=True)
        return

    data = await state.get_data()
    preview = data.get("import_preview")
    file_name = data.get("csv_file_name", "import.csv")
    if not preview:
        await callback.answer("Предпросмотр уже недоступен. Загрузите файл заново.", show_alert=True)
        return

    import_mode = callback.data.rsplit(":", 1)[-1]
    if import_mode not in MODE_LABELS:
        await callback.answer("Неизвестный режим импорта.", show_alert=True)
        return

    await state.update_data(import_mode=import_mode)
    text = _render_preview_text(preview, import_mode=import_mode, file_name=file_name)
    await _safe_edit_message(
        callback.message,
        text,
        reply_markup=import_preview_markup(import_mode),
    )
    await callback.answer("Режим обновлён.")


@router.callback_query(F.data == "import:cancel")
async def import_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("❌ Импорт CSV отменён.", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "import:commit")
async def import_commit_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось продолжить импорт.", show_alert=True)
        return

    data = await state.get_data()
    file_bytes = data.get("csv_file_bytes")
    file_name = data.get("csv_file_name", "import.csv")
    import_mode = data.get("import_mode", "upsert")
    preview = data.get("import_preview")

    if not file_bytes:
        await callback.answer("Файл импорта не найден. Загрузите CSV заново.", show_alert=True)
        return

    await callback.message.edit_text("⏳ Импортирую компании...")

    async with async_session_factory() as session:
        result = await import_companies_from_csv(
            session,
            file_bytes,
            mode=import_mode,
            source="telegram_csv_upload",
        )
        # Get lead groups summary
        lead_groups = await summarize_lead_fit_groups(session)

    await state.clear()

    text = _render_report_text(result, file_name, import_mode)
    if lead_groups:
        text += "\n\n" + "\n".join(["🏷 Группы лидов после импорта:"] + format_lead_group_count_lines(lead_groups))

    text = clamp_text(text)

    await _safe_edit_message(
        callback.message,
        text,
        reply_markup=import_report_markup(),
    )
    await callback.answer("✅ Импорт завершён.")


@router.callback_query(F.data == "import:report:lead_groups")
async def import_report_lead_groups_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть группы лидов.", show_alert=True)
        return

    async with async_session_factory() as session:
        lead_groups = await summarize_lead_fit_groups(session)

    text = "🏷 Группы лидов\n\n" + "\n".join(format_lead_group_count_lines(lead_groups))
    await callback.message.answer(text, reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "import:report:menu")
async def import_report_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("⬅️ Главное меню CRM.", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "import:report:added")
async def import_report_added_callback(callback: CallbackQuery) -> None:
    # Note: this is legacy, we keep the button for compatibility
    await callback.answer("После импорта можно проверить группы лидов.", show_alert=True)


@router.callback_query(F.data == "import:report:tasks")
async def import_report_tasks_callback(callback: CallbackQuery) -> None:
    await callback.answer("Задачи можно настроить в разделе CRM.", show_alert=True)


# ============================================================
# Rendering helpers
# ============================================================


def _render_preview_text(preview, *, import_mode: str, file_name: str) -> str:
    """Render CSV preview text for Telegram (<=3500 chars)."""
    mode_label = MODE_LABELS.get(import_mode, "Создать/обновить")

    lines = [
        f"📄 <b>Предпросмотр CSV: {file_name}</b>",
        "",
        f"📊 Всего строк: <b>{preview.total_rows}</b>",
        f"📋 С ИНН: <b>{preview.inn_count}</b>",
        f"📞 С телефоном: <b>{preview.phone_count}</b>",
        f"🌐 С сайтом: <b>{preview.website_count}</b>",
        "",
        "Распознанные колонки:",
    ]

    if preview.detected_columns:
        for col in preview.detected_columns:
            lines.append(f"  • {col}")
    else:
        lines.append("  — колонки не найдены")

    lines.append("")
    lines.append(f"Первые {len(preview.sample_rows)} строк:")
    for sample in preview.sample_rows:
        parts = [
            f"#{sample['row_number']}",
            sample.get("display_name", "—") or "—",
        ]
        inn = sample.get("inn", "—") or "—"
        phone = sample.get("phone", "—") or "—"
        if inn != "—":
            parts.append(f"ИНН: {inn}")
        if phone != "—":
            parts.append(f"Тел: {phone}")
        lines.append("  " + " | ".join(parts))

    if not preview.sample_rows:
        lines.append("  — нет строк для предпросмотра")

    for warning in preview.warnings:
        lines.append(f"\n⚠️ {warning}")

    if not preview.can_import:
        lines.append("\n❌ Импорт невозможен — не найдено название компании")

    lines.extend(
        [
            "",
            f"Режим: <b>{mode_label}</b>",
            "",
            "Подтвердить импорт?",
        ]
    )

    return clamp_text("\n".join(lines))


def _render_report_text(result, file_name: str, import_mode: str) -> str:
    """Render CSV import report text for Telegram (<=3500 chars)."""
    mode_label = MODE_LABELS.get(import_mode, "Создать/обновить")

    lines = [
        "✅ <b>Импорт CSV завершён</b>",
        "",
        f"Файл: {file_name}",
        f"Режим: {mode_label}",
        "",
        f"📊 Всего строк: <b>{result.total_rows}</b>",
        f"✅ Импортировано: <b>{result.imported_count}</b>",
        f"♻️ Обновлено: <b>{result.updated_count}</b>",
        f"📋 Дублей: <b>{result.duplicate_count}</b>",
        f"⏭ Пропущено: <b>{result.skipped_count}</b>",
        f"❌ Ошибок: <b>{result.error_count}</b>",
    ]

    # Show first N errors
    errors = [r for r in result.row_results if r.status == "error"]
    if errors:
        lines.append(f"\nПервые ошибки ({min(5, len(errors))} из {len(errors)}):")
        for row_err in errors[:5]:
            lines.append(f"  • Строка {row_err.row_number}: {row_err.message[:100]}")

    # Show first N warnings
    if result.warnings:
        lines.append(f"\n⚠️ Предупреждения:")
        for w in result.warnings[:5]:
            lines.append(f"  • {w[:100]}")

    return clamp_text("\n".join(lines))


async def _safe_edit_message(message: Message, text: str, *, reply_markup=None, parse_mode: str | None = None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await message.edit_reply_markup(reply_markup=reply_markup)