from __future__ import annotations

from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database import async_session_factory
from app.modules.crm.keyboards import main_menu, today_tasks_markup
from app.modules.crm.service import format_datetime, get_task_dashboard, list_companies
from app.modules.imports.keyboards import import_preview_markup, import_report_markup
from app.modules.imports.service import import_companies_from_csv, preview_companies_from_csv, save_import_file
from app.modules.imports.states import ImportCsvStates

router = Router(name="imports")


@router.message(Command("import_csv"))
@router.message(F.text == "Импорт CSV")
async def import_csv_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ImportCsvStates.awaiting_file)
    await message.answer(
        "Отправьте CSV-файл документом.\n\n"
        "Поддерживаются разделители: comma (,), semicolon (;), tab.\n"
        "Кодировки: UTF-8 и Windows-1251.\n"
        "Обязательна колонка с названием клиники: name/company/clinic/название/клиника.\n\n"
        "Бот сначала покажет предпросмотр и только потом попросит подтверждение импорта.",
        reply_markup=main_menu(),
    )


@router.message(ImportCsvStates.awaiting_file, F.document)
@router.message(F.document, F.caption == "import_csv")
async def import_csv_file(message: Message, state: FSMContext) -> None:
    document = message.document
    bot_file = await message.bot.get_file(document.file_id)
    content = await message.bot.download_file(bot_file.file_path)
    file_bytes = content.read()

    file_path = save_import_file(file_bytes, document.file_name)

    async with async_session_factory() as session:
        preview = await preview_companies_from_csv(
            session,
            file_bytes,
            file_name=document.file_name,
            file_path=str(file_path),
        )

    await state.clear()
    await state.set_state(ImportCsvStates.awaiting_confirm)
    await state.update_data(
        import_file_name=document.file_name or Path(file_path).name,
        import_file_path=str(file_path),
        import_mode="skip",
        import_preview=preview,
    )

    await message.answer(
        _render_preview(preview, import_mode="skip"),
        reply_markup=import_preview_markup("skip"),
    )


@router.callback_query(F.data.startswith("import:mode:"))
async def import_mode_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось обновить режим импорта.", show_alert=True)
        return

    data = await state.get_data()
    preview = data.get("import_preview")
    if not preview:
        await callback.answer("Предпросмотр уже недоступен. Загрузите файл заново.", show_alert=True)
        return

    import_mode = callback.data.rsplit(":", 1)[-1]
    await state.update_data(import_mode=import_mode)
    await _safe_edit_message(
        callback.message,
        _render_preview(preview, import_mode=import_mode),
        reply_markup=import_preview_markup(import_mode),
    )
    await callback.answer("Режим обновлён.")


@router.callback_query(F.data == "import:cancel")
async def import_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Импорт CSV отменён.", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "import:commit")
async def import_commit_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось продолжить импорт.", show_alert=True)
        return

    data = await state.get_data()
    file_path = data.get("import_file_path")
    file_name = data.get("import_file_name")
    import_mode = data.get("import_mode", "skip")
    if not file_path:
        await callback.answer("Файл импорта не найден. Загрузите CSV заново.", show_alert=True)
        return

    file_bytes = Path(file_path).read_bytes()
    async with async_session_factory() as session:
        report = await import_companies_from_csv(
            session,
            file_bytes,
            file_name=file_name,
            file_path=file_path,
            import_mode=import_mode,
        )

    await state.clear()
    await state.update_data(last_import_added_ids=report.get("added_company_ids", [])[:10])

    await _safe_edit_message(
        callback.message,
        _render_report(report),
        reply_markup=import_report_markup(),
    )
    await callback.answer("Импорт завершён.")


@router.callback_query(F.data == "import:report:added")
async def import_report_added_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть компании.", show_alert=True)
        return

    data = await state.get_data()
    added_ids: list[int] = data.get("last_import_added_ids", [])
    if not added_ids:
        await callback.answer("В последнем импорте не было новых компаний.", show_alert=True)
        return

    async with async_session_factory() as session:
        companies = await list_companies(session, limit=50)
    companies = [company for company in companies if company.id in set(added_ids)]

    if not companies:
        await callback.answer("Компании уже недоступны в списке.", show_alert=True)
        return

    lines = ["Добавленные компании:", ""]
    for company in companies[:10]:
        lines.append(f"#{company.id} {company.name}")
    await callback.message.answer("\n".join(lines), reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "import:report:tasks")
async def import_report_tasks_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть задачи.", show_alert=True)
        return

    async with async_session_factory() as session:
        dashboard = await get_task_dashboard(session)

    visible_tasks = [*dashboard["overdue"], *dashboard["today"], *dashboard["upcoming"]]
    lines = ["📌 Задачи по новым лидам", ""]
    lines.extend(_render_task_group("Просрочено", dashboard["overdue"]))
    lines.append("")
    lines.extend(_render_task_group("Сегодня", dashboard["today"]))
    lines.append("")
    lines.extend(_render_task_group("Ближайшие", dashboard["upcoming"]))
    await callback.message.answer(
        "\n".join(lines),
        reply_markup=today_tasks_markup(visible_tasks) or main_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "import:report:menu")
async def import_report_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Главное меню CRM.", reply_markup=main_menu())
    await callback.answer()


def _render_preview(preview: dict, *, import_mode: str) -> str:
    lines = [
        "📄 Предпросмотр импорта CSV",
        "",
        f"Файл: {preview['file_name']}",
        f"Кодировка: {preview['encoding']}",
        f"Разделитель: {preview['delimiter']}",
        "",
        "Найденные колонки:",
    ]
    lines.extend(f"• {column}" for column in preview.get("detected_columns", []))
    lines.append("")
    lines.append("Column mapping:")
    mapped_columns = preview.get("mapped_columns", {})
    if mapped_columns:
        lines.extend(f"• {canonical} ← {header}" for canonical, header in mapped_columns.items())
    else:
        lines.append("• Совпадений не найдено")

    lines.extend(
        [
            "",
            "Оценка перед импортом:",
            f"• Всего строк: {preview['total_rows']}",
            f"• Похоже на валидные компании: {preview['valid_rows']}",
            f"• Пустое название: {preview['empty_name_rows']}",
            f"• Потенциальные дубли: {preview['potential_duplicates']}",
            "",
            "Первые 5 строк:",
        ]
    )

    for row in preview.get("preview_rows", []):
        data = row["data"]
        line = (
            f"{row['line_number']}. {data['name']} | ИНН: {data['inn']} | "
            f"Телефон: {data['phone']} | Сайт: {data['website']} | Город: {data['city']}"
        )
        if row.get("duplicate_reasons"):
            line += f" | Дубль: {', '.join(row['duplicate_reasons'])}"
        lines.append(line)

    if not preview.get("preview_rows"):
        lines.append("— Нет строк для предпросмотра")

    for warning in preview.get("warnings", []):
        lines.extend(["", f"⚠️ {warning}"])

    for error in preview.get("errors", []):
        lines.extend(["", f"❌ {error}"])

    mode_label = "Пропускать дубли" if import_mode == "skip" else "Обновлять существующие карточки"
    lines.extend(["", f"Режим импорта: {mode_label}", "Подтвердить импорт?"])
    return "\n".join(lines)


def _render_report(report: dict) -> str:
    lines = [
        "📥 Импорт завершён",
        "",
        f"Файл: {report['file_name']}",
        f"Путь: {report['file_path']}",
        "",
        f"Всего строк: {report['total_rows']}",
        f"Валидных строк: {report['valid_rows']}",
        "",
        f"✅ Добавлено: {report['added']}",
        f"♻️ Обновлено: {report['updated']}",
        f"⏭ Пропущено дублей: {report['skipped_duplicates']}",
        f"⚠️ Ошибок: {report['error_rows']}",
    ]

    added_ids = report.get("added_company_ids", [])
    if added_ids:
        lines.extend(["", "Первые добавленные компании:"])
        for company_id in added_ids[:10]:
            lines.append(f"• Компания #{company_id}")

    errors = report.get("errors", [])
    if errors:
        lines.extend(["", "Первые ошибки:"])
        for index, error in enumerate(errors[:5], start=1):
            lines.append(f"{index}. {error}")

    return "\n".join(lines)


def _render_task_group(title: str, tasks: list) -> list[str]:
    lines = [f"{title}:"]
    if not tasks:
        lines.append("— нет")
        return lines

    for task in tasks[:5]:
        due_part = format_datetime(task.due_at) if task.due_at else "без срока"
        company_name = task.company.name if getattr(task, "company", None) else f"Компания #{task.company_id}"
        lines.append(f"• {company_name} — {task.title} ({due_part})")
    return lines


async def _safe_edit_message(message: Message, text: str, *, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await message.edit_reply_markup(reply_markup=reply_markup)
