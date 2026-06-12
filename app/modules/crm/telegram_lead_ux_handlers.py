from __future__ import annotations

from datetime import datetime, timedelta
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message

from app.config import get_settings
from app.database import async_session_factory
from app.modules.admin_reset.service import reset_database
from app.modules.analytics.service import format_company_card_with_score
from app.modules.crm.keyboards import (
    company_actions,
    company_delete_confirm_markup,
    flow_menu,
    lead_group_companies_markup,
    lead_groups_markup,
    main_menu,
    settings_section_menu_markup,
    simple_menu_markup,
    today_tasks_markup,
    touch_plan_markup,
)
from app.modules.crm.service import (
    complete_task,
    delete_company,
    format_datetime,
    get_company,
    get_company_open_tasks,
    get_task,
    get_task_dashboard,
    snooze_task,
)
from app.modules.crm.states import AdminResetStates, CompanyNoteStates
from app.modules.crm.telegram_ux import (
    LIST_PREVIEW_LIMIT,
    TELEGRAM_TEXT_LIMIT,
    build_system_status_snapshot,
    clamp_text,
    is_admin_telegram_id,
    render_admin_reset_disabled,
    render_admin_reset_prompt,
    render_admin_reset_result,
    render_delete_confirmation,
    render_lead_group_companies,
    render_lead_groups_menu,
    render_my_touches_today,
    render_open_tasks,
    render_search_settings_text,
    render_system_status_text,
    render_touch_plan_block,
    render_website_research_result,
)
from app.modules.crm.touch_service import create_touch_plan_for_company, get_touch_plan_for_company
from app.modules.lead_fit.service import (
    get_company_lead_fit,
    list_companies_by_lead_fit_group,
    recalculate_all_companies_lead_fit,
    recalculate_company_lead_fit,
    summarize_lead_fit_groups,
)
from app.modules.research.website_resolver import run_website_search_for_company
from app.modules.users.service import build_display_name, get_user_tasks
from app.utils.telegram import get_current_crm_user

router = Router(name="crm_telegram_lead_ux")


async def _safe_edit_message(message: Message, text: str, *, reply_markup=None, parse_mode: str | None = None) -> None:
    try:
        await message.edit_text(clamp_text(text, TELEGRAM_TEXT_LIMIT), reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await message.edit_reply_markup(reply_markup=reply_markup)


async def _show_company_card(message: Message, company_id: int, *, edit: bool = False) -> bool:
    async with async_session_factory() as session:
        company = await get_company(session, company_id)
    if not company:
        return False

    assigned_user_text = build_display_name(getattr(company, "assigned_user", None)) or "не назначен"
    text = f"👤 <b>Менеджер:</b> {escape(assigned_user_text)}\n\n{format_company_card_with_score(company)}"
    markup = company_actions(company_id)
    markup.inline_keyboard.insert(6, [InlineKeyboardButton(text="📞 План звонка", callback_data=f"sales:open:{company_id}")])
    if edit:
        await _safe_edit_message(message, text, reply_markup=markup, parse_mode="HTML")
        return True
    await message.answer(clamp_text(text, TELEGRAM_TEXT_LIMIT), parse_mode="HTML", reply_markup=markup)
    return True


async def _show_lead_groups(message: Message, *, edit: bool = False) -> None:
    async with async_session_factory() as session:
        summary = await summarize_lead_fit_groups(session)
    text = render_lead_groups_menu(summary)
    if edit:
        await _safe_edit_message(message, text, reply_markup=lead_groups_markup())
        return
    await message.answer(text, reply_markup=lead_groups_markup())


async def _show_lead_group_list(message: Message, group: str, page: int, *, edit: bool = False) -> None:
    async with async_session_factory() as session:
        companies = await list_companies_by_lead_fit_group(session, group)
        visible = companies[page * LIST_PREVIEW_LIMIT : (page + 1) * LIST_PREVIEW_LIMIT]
        lead_fit_scores = {company.id: await get_company_lead_fit(session, company.id) for company in visible}
    text = render_lead_group_companies(group, companies, lead_fit_scores, page=page)
    markup = lead_group_companies_markup(
        visible,
        group,
        page,
        has_next_page=(page + 1) * LIST_PREVIEW_LIMIT < len(companies),
    )
    if edit:
        await _safe_edit_message(message, text, reply_markup=markup)
        return
    await message.answer(text, reply_markup=markup)


async def _show_my_touches(message: Message, telegram_actor: Message | CallbackQuery, *, edit: bool = False) -> None:
    async with async_session_factory() as session:
        current_user = await get_current_crm_user(session, telegram_actor)
        tasks = await get_user_tasks(session, current_user.id, limit=50, only_open=True)
    today = datetime.now().date()
    visible = [
        task
        for task in tasks
        if task.interaction_stage and task.due_at and task.due_at.date() <= today
    ][:LIST_PREVIEW_LIMIT]
    text = render_my_touches_today(visible)
    markup = today_tasks_markup(visible, back_callback="menu:crm:my_touches")
    if edit:
        await _safe_edit_message(message, text, reply_markup=markup)
        return
    await message.answer(text, reply_markup=markup)


async def _show_today_tasks(message: Message, *, edit: bool = False) -> None:
    async with async_session_factory() as session:
        dashboard = await get_task_dashboard(session)
    visible_tasks = [*dashboard["overdue"], *dashboard["today"], *dashboard["upcoming"]]
    lines = ["📊 Задачи на сегодня", ""]
    for title, tasks in (("Просрочено", dashboard["overdue"]), ("Сегодня", dashboard["today"]), ("Ближайшие", dashboard["upcoming"])):
        lines.append(f"{title}:")
        if not tasks:
            lines.append("— нет")
        else:
            for index, task in enumerate(tasks[:LIST_PREVIEW_LIMIT], start=1):
                company_name = task.company.name if task.company else f"Компания #{task.company_id}"
                lines.append(f"{index}. {company_name} — {task.title} ({format_datetime(task.due_at)})")
        lines.append("")
    text = "\n".join(lines).rstrip()
    markup = today_tasks_markup(visible_tasks, back_callback="menu:crm:list")
    if edit:
        await _safe_edit_message(message, text, reply_markup=markup)
        return
    await message.answer(text, reply_markup=markup)


async def _show_touch_plan(message: Message, company_id: int, *, edit: bool = False) -> bool:
    async with async_session_factory() as session:
        company = await get_company(session, company_id)
        if not company:
            return False
        tasks = await get_touch_plan_for_company(session, company_id)
    current_task = next((task for task in tasks if task.status == "open"), None)
    text = clamp_text(f"{company.name}\n\n{render_touch_plan_block(tasks)}", TELEGRAM_TEXT_LIMIT)
    markup = touch_plan_markup(company_id, has_plan=bool(tasks), current_task_id=current_task.id if current_task else None)
    if edit:
        await _safe_edit_message(message, text, reply_markup=markup)
        return True
    await message.answer(text, reply_markup=markup)
    return True


async def _show_settings(message: Message, telegram_user_id: int | None, *, edit: bool = False) -> None:
    settings = get_settings()
    can_reset = is_admin_telegram_id(telegram_user_id) and settings.allow_db_reset
    text = "⚙️ Настройки\n\nЗдесь доступны состояние системы и read-only параметры поиска."
    markup = settings_section_menu_markup(include_admin_reset=can_reset)
    if edit:
        await _safe_edit_message(message, text, reply_markup=markup)
        return
    await message.answer(text, reply_markup=markup)


async def _show_system_status(message: Message, *, edit: bool = False) -> None:
    async with async_session_factory() as session:
        snapshot = await build_system_status_snapshot(session)
    text = render_system_status_text(snapshot)
    markup = settings_section_menu_markup(include_admin_reset=is_admin_telegram_id(message.from_user.id if message.from_user else None) and get_settings().allow_db_reset)
    if edit:
        await _safe_edit_message(message, text, reply_markup=markup)
        return
    await message.answer(text, reply_markup=markup)


async def _show_search_settings(message: Message, *, edit: bool = False) -> None:
    text = render_search_settings_text()
    markup = settings_section_menu_markup(include_admin_reset=is_admin_telegram_id(message.from_user.id if message.from_user else None) and get_settings().allow_db_reset)
    if edit:
        await _safe_edit_message(message, text, reply_markup=markup)
        return
    await message.answer(text, reply_markup=markup)


def _is_touches_message(message: Message) -> bool:
    return "Мои касания сегодня" in (message.text or "")


def _is_touch_plan_message(message: Message) -> bool:
    return "План 7 касаний" in (message.text or "")


@router.message(F.text == "🏷 Группы лидов")
async def lead_groups_message(message: Message) -> None:
    await _show_lead_groups(message)


@router.message(F.text == "📅 Мои касания")
async def my_touches_message(message: Message) -> None:
    await _show_my_touches(message, message)


@router.message(F.text.in_({"⚙️ Настройки", "⚙️ Настройки / Admin"}))
async def settings_message(message: Message) -> None:
    await _show_settings(message, message.from_user.id if message.from_user else None)


@router.callback_query(F.data == "menu:crm:lead_groups")
async def lead_groups_callback(callback: CallbackQuery) -> None:
    if callback.message:
        await _show_lead_groups(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "menu:crm:my_touches")
async def my_touches_callback(callback: CallbackQuery) -> None:
    if callback.message:
        await _show_my_touches(callback.message, callback, edit=True)
    await callback.answer()


@router.callback_query(F.data.in_({"menu:settings:about", "menu:settings:system"}))
async def settings_about_callback(callback: CallbackQuery) -> None:
    if callback.message:
        await _show_system_status(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "menu:settings:search")
async def settings_search_callback(callback: CallbackQuery) -> None:
    if callback.message:
        await _show_search_settings(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("leadfit:group:"))
async def lead_group_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть группу.", show_alert=True)
        return
    _, _, group, page_raw = callback.data.split(":", 3)
    await _show_lead_group_list(callback.message, group, int(page_raw), edit=True)
    await callback.answer()


@router.callback_query(F.data == "leadfit:recalculate_all")
async def lead_groups_recalculate_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось пересчитать группы.", show_alert=True)
        return
    async with async_session_factory() as session:
        scores = await recalculate_all_companies_lead_fit(session)
    await _show_lead_groups(callback.message, edit=True)
    await callback.answer(f"Пересчитано компаний: {len(scores)}")


@router.callback_query(F.data.startswith("leadfit:recalculate:"))
async def lead_fit_recalculate_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось пересчитать приоритет.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        await recalculate_company_lead_fit(session, company_id)
    await _show_company_card(callback.message, company_id, edit=True)
    await callback.answer("Приоритет обновлён.")


@router.callback_query(F.data.startswith("leadfit:website:"))
async def website_research_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось запустить research.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    try:
        async with async_session_factory() as session:
            outcome = await run_website_search_for_company(session, company_id, force=True)
            company = await get_company(session, company_id)
    except Exception:
        await callback.answer("Website research завершился с ошибкой.", show_alert=True)
        return
    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return
    await callback.message.answer(render_website_research_result(outcome, company))
    await callback.answer("Website research выполнен.")


@router.callback_query(F.data.startswith("touch:open:"))
async def touch_plan_open_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть план.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    if not await _show_touch_plan(callback.message, company_id, edit=True):
        await callback.answer("Компания не найдена.", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("touch:create:"))
async def touch_plan_create_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось создать план.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        current_user = await get_current_crm_user(session, callback)
        await create_touch_plan_for_company(session, company_id, assigned_user_id=current_user.id)
    await _show_touch_plan(callback.message, company_id, edit=True)
    await callback.answer("План 7 касаний создан.")


@router.callback_query(F.data.startswith("touch:done:"))
async def touch_plan_done_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось завершить касание.", show_alert=True)
        return
    task_id = int(callback.data.rsplit(":", 1)[-1])
    if task_id <= 0:
        await callback.answer("Нет открытого касания.", show_alert=True)
        return
    async with async_session_factory() as session:
        task = await complete_task(session, task_id)
    if not task:
        await callback.answer("Задача не найдена.", show_alert=True)
        return
    await _show_touch_plan(callback.message, task.company_id, edit=True)
    await callback.answer("Касание отмечено выполненным.")


@router.callback_query(F.data.startswith("touch:note:"))
async def touch_note_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть заметку.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(company_id=company_id)
    await state.set_state(CompanyNoteStates.text)
    await callback.message.answer("Введите короткую заметку по касанию.", reply_markup=flow_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("touch:tasks:"))
async def touch_tasks_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть задачи.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        company = await get_company(session, company_id)
        tasks = await get_company_open_tasks(session, company_id)
    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return
    text = render_open_tasks(company, tasks)
    markup = today_tasks_markup(tasks[:LIST_PREVIEW_LIMIT], back_callback=f"touch:open:{company_id}")
    if markup is None:
        markup = simple_menu_markup([[InlineKeyboardButton(text="⬅️ Назад", callback_data=f"touch:open:{company_id}")]])
    await _safe_edit_message(callback.message, text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("company:delete:confirm:"))
async def company_delete_confirm_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось удалить компанию.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        current_user = await get_current_crm_user(session, callback)
        deleted = await delete_company(session, company_id, deleted_by_user_id=current_user.id)
    if not deleted:
        await callback.answer("Компания не найдена.", show_alert=True)
        return
    markup = simple_menu_markup([[InlineKeyboardButton(text="⬅️ К CRM", callback_data="menu:crm:list")]])
    await _safe_edit_message(callback.message, "Компания скрыта из CRM.", reply_markup=markup)
    await callback.answer("Компания удалена.")


@router.callback_query(F.data.startswith("company:delete:"))
async def company_delete_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть удаление.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        company = await get_company(session, company_id)
    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return
    await _safe_edit_message(
        callback.message,
        render_delete_confirmation(company),
        reply_markup=company_delete_confirm_markup(company_id),
    )
    await callback.answer()


@router.callback_query(F.data.in_({"admin:reset:crm:start", "admin:reset:all:start"}))
async def admin_reset_start_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть reset.", show_alert=True)
        return
    telegram_user_id = callback.from_user.id if callback.from_user else None
    if not is_admin_telegram_id(telegram_user_id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return
    if not get_settings().allow_db_reset:
        await callback.message.answer(render_admin_reset_disabled())
        await callback.answer()
        return
    mode = "all_data" if callback.data.endswith("all:start") else "crm_only"
    await state.clear()
    await state.update_data(admin_reset_mode=mode)
    await state.set_state(AdminResetStates.confirmation)
    await callback.message.answer(render_admin_reset_prompt(mode), reply_markup=flow_menu())
    await callback.answer()


@router.message(AdminResetStates.confirmation)
async def admin_reset_confirmation_message(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    mode = data.get("admin_reset_mode", "crm_only")
    expected_confirmation = "RESET ALL DATA" if mode == "all_data" else "RESET CRM"
    if (message.text or "").strip() != expected_confirmation:
        await message.answer(f"Нужен точный текст {expected_confirmation}.", reply_markup=flow_menu())
        return
    if not is_admin_telegram_id(message.from_user.id if message.from_user else None):
        await state.clear()
        await message.answer("Недостаточно прав.", reply_markup=main_menu())
        return
    if not get_settings().allow_db_reset:
        await state.clear()
        await message.answer(render_admin_reset_disabled(), reply_markup=main_menu())
        return
    async with async_session_factory() as session:
        result = await reset_database(session, mode=mode, keep_users=True, clear_debug_files=mode == "all_data")
    await state.clear()
    await message.answer(render_admin_reset_result(result), reply_markup=main_menu())


@router.callback_query(F.data.startswith("task:done:"))
async def task_done_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось завершить задачу.", show_alert=True)
        return
    task_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        task = await complete_task(session, task_id)
    if not task:
        await callback.answer("Задача не найдена.", show_alert=True)
        return
    if _is_touch_plan_message(callback.message):
        await _show_touch_plan(callback.message, task.company_id, edit=True)
    elif _is_touches_message(callback.message):
        await _show_my_touches(callback.message, callback, edit=True)
    else:
        await _show_today_tasks(callback.message, edit=True)
    await callback.answer("Задача отмечена выполненной.")


@router.callback_query(F.data.startswith("task:shift:"))
async def task_shift_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось перенести задачу.", show_alert=True)
        return
    task_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        task = await get_task(session, task_id)
        if not task:
            await callback.answer("Задача не найдена.", show_alert=True)
            return
        new_due_at = (task.due_at or datetime.now()) + timedelta(days=1)
        updated = await snooze_task(session, task_id, new_due_at)
    if not updated:
        await callback.answer("Не удалось перенести задачу.", show_alert=True)
        return
    if _is_touch_plan_message(callback.message):
        await _show_touch_plan(callback.message, updated.company_id, edit=True)
    elif _is_touches_message(callback.message):
        await _show_my_touches(callback.message, callback, edit=True)
    else:
        await _show_today_tasks(callback.message, edit=True)
    await callback.answer("Задача перенесена на +1 день.")
