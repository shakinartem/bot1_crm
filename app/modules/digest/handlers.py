from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_factory
from app.modules.crm.keyboards import CANCEL_TEXT, company_actions, flow_menu, main_menu
from app.modules.crm.service import (
    complete_task,
    format_company_card,
    format_datetime,
    get_company,
    humanize_company_status,
    parse_due_at_input,
    snooze_task,
)
from app.modules.digest.keyboards import (
    daily_digest_markup,
    digest_lead_list_markup,
    digest_settings_markup,
    digest_task_list_markup,
)
from app.modules.digest.models import DigestSettings
from app.modules.digest.service import (
    build_daily_digest,
    build_weekly_summary,
    get_hot_leads,
    get_overdue_tasks,
    get_stale_leads,
    get_today_tasks,
)
from app.modules.digest.settings import get_or_create_digest_settings, update_digest_settings
from app.modules.digest.states import DigestStates

router = Router(name="digest")


@router.message(Command("daily"))
@router.message(F.text == "🗓 План дня")
async def daily_digest_command(message: Message) -> None:
    await _show_daily_digest(message)


@router.message(Command("week"))
async def weekly_digest_command(message: Message) -> None:
    await _show_weekly_summary(message)


@router.message(Command("overdue"))
async def overdue_digest_command(message: Message) -> None:
    await _show_overdue_tasks(message)


@router.message(Command("hot"))
async def hot_digest_command(message: Message) -> None:
    await _show_hot_leads(message)


@router.message(Command("stale"))
async def stale_digest_command(message: Message) -> None:
    await _show_stale_leads(message)


@router.callback_query(F.data == "digest:daily")
async def digest_daily_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not callback.message:
        await callback.answer("Не удалось открыть план дня.", show_alert=True)
        return
    await _show_daily_digest(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "digest:weekly")
async def digest_weekly_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть сводку.", show_alert=True)
        return
    await _show_weekly_summary(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "digest:overdue")
async def digest_overdue_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть просроченные задачи.", show_alert=True)
        return
    await _show_overdue_tasks(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "digest:today")
async def digest_today_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть задачи на сегодня.", show_alert=True)
        return
    await _show_today_tasks(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "digest:hot")
async def digest_hot_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть горячие лиды.", show_alert=True)
        return
    await _show_hot_leads(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "digest:stale")
async def digest_stale_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть лиды без касаний.", show_alert=True)
        return
    await _show_stale_leads(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "digest:settings")
async def digest_settings_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not callback.message or not callback.from_user:
        await callback.answer("Не удалось открыть настройки дайджеста.", show_alert=True)
        return

    async with async_session_factory() as session:
        settings = await _resolve_digest_settings(session, callback.from_user.id)

    await _safe_edit_message(
        callback.message,
        _render_digest_settings_text(settings),
        reply_markup=digest_settings_markup(settings.enabled),
    )
    await callback.answer()


@router.callback_query(F.data == "digest:settings:toggle")
async def digest_settings_toggle_callback(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        await callback.answer("Не удалось обновить настройки дайджеста.", show_alert=True)
        return

    async with async_session_factory() as session:
        current = await _resolve_digest_settings(session, callback.from_user.id)
        settings = await update_digest_settings(
            session,
            callback.from_user.id,
            enabled=not current.enabled,
            default_enabled=_default_auto_enabled(callback.from_user.id),
        )

    await _safe_edit_message(
        callback.message,
        _render_digest_settings_text(settings),
        reply_markup=digest_settings_markup(settings.enabled),
    )
    await callback.answer("Настройки обновлены.")


@router.callback_query(F.data == "digest:settings:time")
async def digest_settings_time_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось изменить время дайджеста.", show_alert=True)
        return
    await state.set_state(DigestStates.settings_time)
    await callback.message.answer(
        "Введите время в формате HH:MM, например 09:00.",
        reply_markup=flow_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "digest:settings:stale")
async def digest_settings_stale_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось изменить период без касаний.", show_alert=True)
        return
    await state.set_state(DigestStates.settings_stale_days)
    await callback.message.answer(
        "Введите период без касаний в днях, например 7.",
        reply_markup=flow_menu(),
    )
    await callback.answer()


@router.message(DigestStates.settings_time)
async def digest_settings_time_input(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip() == CANCEL_TEXT:
        await state.clear()
        await message.answer("Изменение времени отменено.", reply_markup=main_menu())
        return

    raw = (message.text or "").strip()
    if len(raw) != 5 or raw[2] != ":" or not raw.replace(":", "").isdigit():
        await message.answer("Введите время в формате HH:MM.", reply_markup=flow_menu())
        return

    if not message.from_user:
        await state.clear()
        return

    async with async_session_factory() as session:
        settings = await update_digest_settings(
            session,
            message.from_user.id,
            send_time=raw,
            default_enabled=_default_auto_enabled(message.from_user.id),
        )

    await state.clear()
    await message.answer(_render_digest_settings_text(settings), reply_markup=main_menu())


@router.message(DigestStates.settings_stale_days)
async def digest_settings_stale_input(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip() == CANCEL_TEXT:
        await state.clear()
        await message.answer("Изменение периода отменено.", reply_markup=main_menu())
        return

    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) < 1 or int(raw) > 90:
        await message.answer("Введите число дней от 1 до 90.", reply_markup=flow_menu())
        return

    if not message.from_user:
        await state.clear()
        return

    async with async_session_factory() as session:
        settings = await update_digest_settings(
            session,
            message.from_user.id,
            stale_days=int(raw),
            default_enabled=_default_auto_enabled(message.from_user.id),
        )

    await state.clear()
    await message.answer(_render_digest_settings_text(settings), reply_markup=main_menu())


@router.callback_query(F.data.startswith("digest:task_done:"))
async def digest_task_done_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось завершить задачу.", show_alert=True)
        return

    _, _, task_id_raw, section = callback.data.split(":", 3)
    async with async_session_factory() as session:
        task = await complete_task(session, int(task_id_raw))

    if not task:
        await callback.answer("Задача не найдена.", show_alert=True)
        return

    await callback.answer("Задача выполнена.")
    await _refresh_section(callback.message, section, edit=True)


@router.callback_query(F.data.startswith("digest:task_snooze:"))
async def digest_task_snooze_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось перенести задачу.", show_alert=True)
        return

    _, _, task_id_raw, section = callback.data.split(":", 3)
    await state.set_state(DigestStates.task_snooze_due_at)
    await state.update_data(task_id=int(task_id_raw), return_section=section)
    await callback.message.answer(
        "Введите новый срок: завтра, через 2 часа или DD.MM.YYYY HH:MM.",
        reply_markup=flow_menu(),
    )
    await callback.answer()


@router.message(DigestStates.task_snooze_due_at)
async def digest_task_snooze_input(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip() == CANCEL_TEXT:
        await state.clear()
        await message.answer("Перенос задачи отменён.", reply_markup=main_menu())
        return

    try:
        due_at = parse_due_at_input(message.text or "")
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=flow_menu())
        return

    data = await state.get_data()
    async with async_session_factory() as session:
        task = await snooze_task(session, data["task_id"], due_at, created_by="digest")

    section = data.get("return_section", "daily")
    await state.clear()
    if not task:
        await message.answer("Задача не найдена.", reply_markup=main_menu())
        return

    await message.answer(f"Задача перенесена на {format_datetime(due_at)}.", reply_markup=main_menu())
    await _refresh_section(message, section, edit=False)


@router.callback_query(F.data.startswith("digest:open_company:"))
async def digest_open_company_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть компанию.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        company = await get_company(session, company_id)

    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return

    await callback.message.answer(
        format_company_card(company),
        parse_mode="HTML",
        reply_markup=company_actions(company.id),
    )
    await callback.answer()


@router.callback_query(F.data == "digest:menu")
async def digest_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Главное меню CRM.", reply_markup=main_menu())
    await callback.answer()


async def _show_daily_digest(message: Message, *, edit: bool = False) -> None:
    async with async_session_factory() as session:
        digest = await build_daily_digest(session, manager_id=getattr(message.from_user, "id", None))

    text = _render_daily_digest_text(digest)
    if edit:
        await _safe_edit_message(message, text, reply_markup=daily_digest_markup())
        return
    await message.answer(text, reply_markup=daily_digest_markup())


async def _show_weekly_summary(message: Message, *, edit: bool = False) -> None:
    async with async_session_factory() as session:
        summary = await build_weekly_summary(session, manager_id=getattr(message.from_user, "id", None))

    text = _render_weekly_summary_text(summary)
    if edit:
        await _safe_edit_message(message, text, reply_markup=daily_digest_markup())
        return
    await message.answer(text, reply_markup=daily_digest_markup())


async def _show_overdue_tasks(message: Message, *, edit: bool = False) -> None:
    async with async_session_factory() as session:
        tasks = await get_overdue_tasks(session)

    text = _render_task_digest_text("🔴 Просроченные задачи", tasks)
    markup = digest_task_list_markup(tasks, section="overdue")
    if edit:
        await _safe_edit_message(message, text, reply_markup=markup or daily_digest_markup())
        return
    await message.answer(text, reply_markup=markup or daily_digest_markup())


async def _show_today_tasks(message: Message, *, edit: bool = False) -> None:
    async with async_session_factory() as session:
        tasks = await get_today_tasks(session)

    text = _render_task_digest_text("🟡 Задачи на сегодня", tasks)
    markup = digest_task_list_markup(tasks, section="today")
    if edit:
        await _safe_edit_message(message, text, reply_markup=markup or daily_digest_markup())
        return
    await message.answer(text, reply_markup=markup or daily_digest_markup())


async def _show_hot_leads(message: Message, *, edit: bool = False) -> None:
    async with async_session_factory() as session:
        leads = await get_hot_leads(session)

    text = _render_lead_digest_text("🔥 Горячие лиды", leads)
    markup = digest_lead_list_markup(leads, prefix="hot")
    if edit:
        await _safe_edit_message(message, text, reply_markup=markup or daily_digest_markup())
        return
    await message.answer(text, reply_markup=markup or daily_digest_markup())


async def _show_stale_leads(message: Message, *, edit: bool = False) -> None:
    async with async_session_factory() as session:
        stale_days = 7
        if message.from_user:
            settings = await _resolve_digest_settings(session, message.from_user.id)
            stale_days = settings.stale_days
        leads = await get_stale_leads(session, days_without_interaction=stale_days)

    text = _render_lead_digest_text("🧊 Давно без касаний", leads)
    markup = digest_lead_list_markup(leads, prefix="stale")
    if edit:
        await _safe_edit_message(message, text, reply_markup=markup or daily_digest_markup())
        return
    await message.answer(text, reply_markup=markup or daily_digest_markup())


async def _refresh_section(message: Message, section: str, *, edit: bool) -> None:
    if section == "overdue":
        await _show_overdue_tasks(message, edit=edit)
        return
    if section == "today":
        await _show_today_tasks(message, edit=edit)
        return
    await _show_daily_digest(message, edit=edit)


def _render_daily_digest_text(digest) -> str:
    lines = [
        f"🗓 План дня — {digest.date}",
        "",
        f"🔴 Просроченные задачи: {len(digest.overdue_tasks)}",
    ]
    lines.extend(_preview_tasks(digest.overdue_tasks))
    lines.extend(["", f"🟡 Задачи на сегодня: {len(digest.today_tasks)}"])
    lines.extend(_preview_tasks(digest.today_tasks))
    lines.extend(["", f"🔥 Горячие лиды: {len(digest.hot_leads)}"])
    lines.extend(_preview_leads(digest.hot_leads))
    lines.extend(["", f"🧊 Давно без касаний: {len(digest.stale_leads)}"])
    lines.extend(_preview_stale(digest.stale_leads))
    lines.extend(
        [
            "",
            "📊 Вчера:",
            f"• Касаний: {digest.yesterday_activity.interactions_total}",
            f"• Интерес: {digest.yesterday_activity.interested_count}",
            f"• КП: {digest.yesterday_activity.proposals_count}",
            f"• Консультации: {digest.yesterday_activity.consultations_count}",
            f"• Отказы: {digest.yesterday_activity.deals_lost_count}",
            "",
            "🎯 Рекомендация:",
            digest.recommendation,
        ]
    )
    return "\n".join(lines)


def _render_weekly_summary_text(summary) -> str:
    activity = summary.activity
    return "\n".join(
        [
            "📊 Сводка за 7 дней",
            "",
            f"📞 Касания: {activity.interactions_total}",
            f"☎️ Звонки: {activity.calls_total}",
            f"💬 Сообщения: {activity.messages_total}",
            f"📧 Email: {activity.emails_total}",
            "",
            f"🔥 Интерес: {activity.interested_count}",
            f"📅 Консультации назначены: {activity.consultations_count}",
            f"📄 КП запрошено/отправлено: {activity.proposals_count}",
            f"✅ Сделки: {activity.deals_won_count}",
            f"❌ Отказы: {activity.deals_lost_count}",
            "",
            f"🏥 Новых компаний: {activity.new_companies_count}",
            f"📌 Выполненных задач: {activity.tasks_done_count}",
            f"🔴 Осталось просроченных: {activity.overdue_tasks_count}",
            "",
            "Лучшие следующие действия:",
            summary.recommendation,
        ]
    )


def _render_task_digest_text(title: str, tasks: list) -> str:
    lines = [title, ""]
    if not tasks:
        lines.append("Список пуст.")
        return "\n".join(lines)

    for index, task in enumerate(tasks, start=1):
        lines.append(f"{index}. {task.company_name}")
        lines.append(f"Задача: {task.title}")
        lines.append(f"Срок: {task.due_at or 'без срока'}")
        lines.append(f"Статус компании: {humanize_company_status(task.company_status)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _render_lead_digest_text(title: str, leads: list) -> str:
    lines = [title, ""]
    if not leads:
        lines.append("Список пуст.")
        return "\n".join(lines)

    for index, lead in enumerate(leads, start=1):
        lines.append(f"{index}. {lead.company_name} — {humanize_company_status(lead.status)} — {lead.reason}")
        if lead.city:
            lines.append(f"Город: {lead.city}")
        if lead.last_interaction_at:
            lines.append(f"Последнее касание: {lead.last_interaction_at}")
        if lead.next_task_title:
            due_suffix = f" ({lead.next_task_due_at})" if lead.next_task_due_at else ""
            lines.append(f"Последняя задача: {lead.next_task_title}{due_suffix}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _preview_tasks(tasks: list) -> list[str]:
    if not tasks:
        return ["— нет"]
    return [f"{index}. {task.company_name} — {task.title}" for index, task in enumerate(tasks[:3], start=1)]


def _preview_leads(leads: list) -> list[str]:
    if not leads:
        return ["— нет"]
    return [
        f"{index}. {lead.company_name} — {humanize_company_status(lead.status)} — последнее касание {lead.last_interaction_at or 'нет'}"
        for index, lead in enumerate(leads[:3], start=1)
    ]


def _preview_stale(leads: list) -> list[str]:
    if not leads:
        return ["— нет"]
    return [
        f"{index}. {lead.company_name} — {lead.days_without_interaction or 0} дней без касаний"
        for index, lead in enumerate(leads[:3], start=1)
    ]


def _render_digest_settings_text(settings: DigestSettings) -> str:
    status = "включен" if settings.enabled else "выключен"
    return "\n".join(
        [
            "⚙️ Настройки дайджеста",
            "",
            f"Авто-дайджест: {status}",
            f"Время: {settings.send_time}",
            f"Дни: {settings.weekdays_label}",
            "Просрочка: показывать",
            "Горячие лиды: показывать",
            f"Давно без касаний: {settings.stale_days} дней",
        ]
    )


async def _resolve_digest_settings(session: AsyncSession, user_id: int) -> DigestSettings:
    return await get_or_create_digest_settings(
        session,
        user_id,
        default_enabled=_default_auto_enabled(user_id),
    )


def _default_auto_enabled(user_id: int) -> bool:
    return user_id in set(get_settings().admin_id_list)


async def _safe_edit_message(
    message: Message,
    text: str,
    *,
    reply_markup=None,
) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await message.edit_reply_markup(reply_markup=reply_markup)
