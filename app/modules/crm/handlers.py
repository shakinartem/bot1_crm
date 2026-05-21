from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database import async_session_factory
from app.modules.ai.service import prepare_cold_call
from app.modules.crm.constants import CONTACT_TYPE_LABELS, ContactType
from app.modules.crm.keyboards import (
    CANCEL_TEXT,
    NO_TEXT,
    SKIP_TEXT,
    YES_TEXT,
    call_results_markup,
    company_actions,
    company_list_markup,
    contact_type_menu,
    decision_maker_confirm_markup,
    flow_menu,
    follow_up_task_prompt_markup,
    history_markup,
    main_menu,
    status_options_markup,
    today_tasks_markup,
    yes_no_menu,
)
from app.modules.crm.schemas import CompanyCreate, ContactPointCreate, DecisionMakerCreate
from app.modules.crm.service import (
    add_contact_point,
    add_decision_maker,
    change_company_status,
    complete_task,
    create_company,
    create_company_task,
    create_note_interaction,
    format_company_card,
    format_datetime,
    get_company,
    get_task,
    get_task_dashboard,
    humanize_company_status,
    humanize_interaction_result,
    humanize_interaction_type,
    list_companies,
    list_interactions,
    parse_due_at_input,
    record_call_result,
    search_companies,
    suggest_next_task_title,
)
from app.modules.crm.states import (
    CompanyCallStates,
    CompanyCreateStates,
    CompanyNoteStates,
    CompanySearchStates,
    ContactPointStates,
    DecisionMakerStates,
    TaskStates,
)

router = Router(name="crm")

CONTACT_TYPE_BY_LABEL = {label: value for value, label in CONTACT_TYPE_LABELS.items()}


def _is_skip(text: str | None) -> bool:
    return (text or "").strip() == SKIP_TEXT


def _clean_optional(text: str | None) -> str | None:
    value = (text or "").strip()
    return value or None


def _search_results_text(companies: list) -> str:
    if not companies:
        return "🔎 Ничего не найдено."

    lines = [f"🔎 Найдено: {len(companies)}", ""]
    for index, company in enumerate(companies, start=1):
        lines.append(
            f"{index}. {company.name} — {company.city or 'город не указан'} — "
            f"{humanize_company_status(company.status)}"
        )
    return "\n".join(lines)


def _format_interaction_entry(index: int, interaction) -> str:
    lines = [f"{index}. {format_datetime(interaction.created_at)}"]
    lines.append(f"Тип: {humanize_interaction_type(interaction.type)}")
    if interaction.result:
        lines.append(f"Результат: {humanize_interaction_result(interaction.result)}")
    if interaction.summary:
        lines.append(f"Комментарий: {interaction.summary}")
    if interaction.next_action:
        lines.append(f"Следующее действие: {interaction.next_action}")
    return "\n".join(lines)


def _render_history(company_name: str, interactions: list, offset: int) -> str:
    lines = [f"📜 История касаний: {company_name}", ""]
    if not interactions:
        lines.append("Пока нет сохранённых касаний.")
        return "\n".join(lines)

    for index, interaction in enumerate(interactions, start=offset + 1):
        lines.append(_format_interaction_entry(index, interaction))
        lines.append("")
    return "\n".join(lines).rstrip()


def _task_line(task) -> str:
    due_part = format_datetime(task.due_at) if task.due_at else "без срока"
    company_name = task.company.name if getattr(task, "company", None) else f"Компания #{task.company_id}"
    return f"{company_name} — {task.title} ({due_part})"


def _render_task_section(title: str, icon: str, tasks: list) -> list[str]:
    lines = [f"{icon} {title}:"]
    if not tasks:
        lines.append("— нет")
        return lines

    for index, task in enumerate(tasks, start=1):
        lines.append(f"{index}. {_task_line(task)}")
    return lines


async def _show_recent_companies(message: Message, *, edit: bool = False) -> None:
    async with async_session_factory() as session:
        companies = await list_companies(session, limit=15)

    text = "Компаний пока нет." if not companies else "Последние компании:"
    if companies:
        text = f"{text}\n\n" + "\n".join(
            f"#{company.id} {company.name} — {humanize_company_status(company.status)}"
            for company in companies
        )

    if edit:
        await _safe_edit_message(
            message,
            text,
            reply_markup=company_list_markup(companies) if companies else None,
        )
        return

    await message.answer(
        text,
        reply_markup=company_list_markup(companies) if companies else None,
    )


async def _show_company_card(message: Message, company_id: int, *, edit: bool = False) -> bool:
    async with async_session_factory() as session:
        company = await get_company(session, company_id)
    if not company:
        return False

    text = format_company_card(company)
    markup = company_actions(company_id)
    if edit:
        await _safe_edit_message(message, text, reply_markup=markup, parse_mode="HTML")
        return True

    await message.answer(text, parse_mode="HTML", reply_markup=markup)
    return True


async def _show_today_tasks(message: Message, *, edit: bool = False) -> None:
    async with async_session_factory() as session:
        dashboard = await get_task_dashboard(session)

    visible_tasks = [*dashboard["overdue"], *dashboard["today"], *dashboard["upcoming"]]
    lines = ["📌 Задачи на сегодня", ""]
    lines.extend(_render_task_section("Просрочено", "🔴", dashboard["overdue"]))
    lines.append("")
    lines.extend(_render_task_section("Сегодня", "🟡", dashboard["today"]))
    lines.append("")
    lines.extend(_render_task_section("Ближайшие", "🟢", dashboard["upcoming"]))
    lines.append("")
    lines.append("Перенос задачи будет добавлен на следующем этапе.")
    text = "\n".join(lines)
    markup = today_tasks_markup(visible_tasks)

    if edit:
        await _safe_edit_message(message, text, reply_markup=markup)
        return

    await message.answer(text, reply_markup=markup)


async def _safe_edit_message(
    message: Message,
    text: str,
    *,
    reply_markup=None,
    parse_mode: str | None = None,
) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await message.edit_reply_markup(reply_markup=reply_markup)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "ШАРиК Sales Intelligence готов.\n"
        "Выберите действие.",
        reply_markup=main_menu(),
    )


@router.message(Command("menu"))
async def menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Главное меню CRM.", reply_markup=main_menu())


@router.message(Command("cancel"))
@router.message(F.text == CANCEL_TEXT)
async def cancel_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Текущее действие отменено.", reply_markup=main_menu())


@router.message(Command("add_company"))
@router.message(F.text == "Добавить компанию")
async def start_company_creation(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(CompanyCreateStates.name)
    await message.answer("Введите название компании.", reply_markup=flow_menu())


@router.message(Command("new_company"))
async def new_company(message: Message) -> None:
    raw = (message.text or "").replace("/new_company", "", 1).strip()
    parts = [part.strip() for part in raw.split(";")]
    if not parts or not parts[0]:
        await message.answer(
            "Укажите минимум название: "
            "/new_company Клиника Улыбка; +79990000000; https://site.ru"
        )
        return

    payload = CompanyCreate(
        name=parts[0],
        phone=parts[1] if len(parts) > 1 else None,
        website=parts[2] if len(parts) > 2 else None,
        city=parts[3] if len(parts) > 3 else None,
        notes=parts[4] if len(parts) > 4 else None,
    )
    async with async_session_factory() as session:
        company = await create_company(session, payload)

    await message.answer(
        f"Компания добавлена: #{company.id} {company.name}",
        reply_markup=main_menu(),
    )
    await _show_company_card(message, company.id)


@router.message(CompanyCreateStates.name)
async def company_creation_name(message: Message, state: FSMContext) -> None:
    name = _clean_optional(message.text)
    if not name or _is_skip(name):
        await message.answer("Название обязательно. Введите название компании.", reply_markup=flow_menu())
        return

    await state.update_data(name=name)
    await state.set_state(CompanyCreateStates.phone)
    await message.answer("Введите телефон или нажмите «Пропустить».", reply_markup=flow_menu(allow_skip=True))


@router.message(CompanyCreateStates.phone)
async def company_creation_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=None if _is_skip(message.text) else _clean_optional(message.text))
    await state.set_state(CompanyCreateStates.website)
    await message.answer("Введите сайт компании или нажмите «Пропустить».", reply_markup=flow_menu(allow_skip=True))


@router.message(CompanyCreateStates.website)
async def company_creation_website(message: Message, state: FSMContext) -> None:
    await state.update_data(website=None if _is_skip(message.text) else _clean_optional(message.text))
    await state.set_state(CompanyCreateStates.city)
    await message.answer("Введите город или нажмите «Пропустить».", reply_markup=flow_menu(allow_skip=True))


@router.message(CompanyCreateStates.city)
async def company_creation_city(message: Message, state: FSMContext) -> None:
    await state.update_data(city=None if _is_skip(message.text) else _clean_optional(message.text))
    await state.set_state(CompanyCreateStates.notes)
    await message.answer("Добавьте заметку или нажмите «Пропустить».", reply_markup=flow_menu(allow_skip=True))


@router.message(CompanyCreateStates.notes)
async def company_creation_notes(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    payload = CompanyCreate(
        name=data["name"],
        phone=data.get("phone"),
        website=data.get("website"),
        city=data.get("city"),
        notes=None if _is_skip(message.text) else _clean_optional(message.text),
    )

    async with async_session_factory() as session:
        company = await create_company(session, payload)

    await state.clear()
    await message.answer(f"Компания создана: #{company.id} {company.name}", reply_markup=main_menu())
    await _show_company_card(message, company.id)


@router.message(Command("leads"))
@router.message(F.text == "Компании")
async def leads(message: Message) -> None:
    await _show_recent_companies(message)


@router.message(Command("search"))
async def search(message: Message, state: FSMContext) -> None:
    query = (message.text or "").replace("/search", "", 1).strip()
    if not query:
        await state.set_state(CompanySearchStates.query)
        await message.answer(
            "Введите название, ИНН, телефон, сайт, город, ФИО ЛПР или контакт.",
            reply_markup=flow_menu(),
        )
        return

    async with async_session_factory() as session:
        companies = await search_companies(session, query)
    await message.answer(
        _search_results_text(companies),
        reply_markup=company_list_markup(companies) if companies else None,
    )


@router.message(F.text == "Поиск")
async def search_help(message: Message, state: FSMContext) -> None:
    await state.set_state(CompanySearchStates.query)
    await message.answer(
        "Введите название, ИНН, телефон, сайт, город, ФИО ЛПР или контакт.",
        reply_markup=flow_menu(),
    )


@router.message(CompanySearchStates.query)
async def search_from_state(message: Message, state: FSMContext) -> None:
    query = _clean_optional(message.text)
    if not query or _is_skip(query):
        await message.answer("Поисковый запрос не должен быть пустым.", reply_markup=flow_menu())
        return

    async with async_session_factory() as session:
        companies = await search_companies(session, query)

    await state.clear()
    await message.answer(
        _search_results_text(companies),
        reply_markup=company_list_markup(companies) if companies else None,
    )


@router.message(Command("company"))
async def company_card(message: Message) -> None:
    raw_id = (message.text or "").replace("/company", "", 1).strip()
    if not raw_id.isdigit():
        await message.answer("Формат: /company 12")
        return

    if not await _show_company_card(message, int(raw_id)):
        await message.answer("Компания не найдена.")


@router.message(Command("call_result"))
async def call_result(message: Message) -> None:
    raw = (message.text or "").replace("/call_result", "", 1).strip()
    parts = [part.strip() for part in raw.split(";")]
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer(
            "Формат: /call_result ID; недозвон|отказ|интересно|перезвонить|"
            "назначена консультация|запросили КП|сделка; комментарий"
        )
        return

    comment = parts[2] if len(parts) > 2 and parts[2] else None
    async with async_session_factory() as session:
        company, _ = await record_call_result(session, int(parts[0]), parts[1], comment=comment)

    if not company:
        await message.answer("Компания не найдена.")
        return

    await message.answer(f"Результат звонка сохранен. Статус: {humanize_company_status(company.status)}")


@router.message(F.text == "Задачи на сегодня")
async def today_tasks(message: Message) -> None:
    await _show_today_tasks(message)


@router.callback_query(F.data == "company:list")
async def company_list_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть список.")
        return

    await state.clear()
    await _show_recent_companies(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("company:open:"))
async def company_card_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть карточку.", show_alert=True)
        return

    await state.clear()
    company_id = int(callback.data.rsplit(":", 1)[-1])
    if not await _show_company_card(callback.message, company_id, edit=True):
        await callback.answer("Компания не найдена.", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("company:call:"))
async def company_call_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть сценарий звонка.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    await _safe_edit_message(
        callback.message,
        "Выберите результат звонка:",
        reply_markup=call_results_markup(company_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("call:pick:"))
async def call_result_pick_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось продолжить сценарий.", show_alert=True)
        return

    _, _, company_id_raw, result_code = callback.data.split(":", 3)
    await state.clear()
    await state.update_data(company_id=int(company_id_raw), result_code=result_code)
    await state.set_state(CompanyCallStates.comment)
    await callback.answer()
    await callback.message.answer(
        "Добавьте короткий комментарий к звонку или нажмите «Пропустить».",
        reply_markup=flow_menu(allow_skip=True),
    )


@router.message(CompanyCallStates.comment)
async def call_comment_step(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    comment = None if _is_skip(message.text) else _clean_optional(message.text)

    async with async_session_factory() as session:
        company, _ = await record_call_result(
            session,
            data["company_id"],
            data["result_code"],
            comment=comment,
        )

    await state.clear()
    await message.answer("Результат звонка сохранен.", reply_markup=main_menu())
    if company:
        await _show_company_card(message, company.id)
        await message.answer(
            f"Создать следующую задачу?\n"
            f"Рекомендуемый заголовок: {suggest_next_task_title(data['result_code'])}",
            reply_markup=follow_up_task_prompt_markup(company.id),
        )


@router.callback_query(F.data.startswith("company:note:"))
async def company_note_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть заметку.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(company_id=company_id)
    await state.set_state(CompanyNoteStates.text)
    await callback.answer()
    await callback.message.answer("Введите текст заметки.", reply_markup=flow_menu())


@router.message(CompanyNoteStates.text)
async def note_text_step(message: Message, state: FSMContext) -> None:
    note = _clean_optional(message.text)
    if not note or _is_skip(note):
        await message.answer("Заметка не должна быть пустой.", reply_markup=flow_menu())
        return

    data = await state.get_data()
    async with async_session_factory() as session:
        await create_note_interaction(session, data["company_id"], note)

    await state.clear()
    await message.answer("Заметка сохранена.", reply_markup=main_menu())
    await _show_company_card(message, data["company_id"])


@router.callback_query(F.data.startswith("company:dm:"))
async def company_dm_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть сценарий ЛПР.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(company_id=company_id)
    await state.set_state(DecisionMakerStates.full_name)
    await callback.answer()
    await callback.message.answer("Введите ФИО ЛПР.", reply_markup=flow_menu())


@router.message(DecisionMakerStates.full_name)
async def dm_full_name_step(message: Message, state: FSMContext) -> None:
    full_name = _clean_optional(message.text)
    if not full_name or _is_skip(full_name):
        await message.answer("ФИО обязательно. Введите ФИО ЛПР.", reply_markup=flow_menu())
        return

    await state.update_data(full_name=full_name)
    await state.set_state(DecisionMakerStates.role)
    await message.answer("Введите должность или нажмите «Пропустить».", reply_markup=flow_menu(allow_skip=True))


@router.message(DecisionMakerStates.role)
async def dm_role_step(message: Message, state: FSMContext) -> None:
    await state.update_data(role=None if _is_skip(message.text) else _clean_optional(message.text))
    await state.set_state(DecisionMakerStates.phone)
    await message.answer("Введите телефон или нажмите «Пропустить».", reply_markup=flow_menu(allow_skip=True))


@router.message(DecisionMakerStates.phone)
async def dm_phone_step(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=None if _is_skip(message.text) else _clean_optional(message.text))
    await state.set_state(DecisionMakerStates.email)
    await message.answer("Введите email или нажмите «Пропустить».", reply_markup=flow_menu(allow_skip=True))


@router.message(DecisionMakerStates.email)
async def dm_email_step(message: Message, state: FSMContext) -> None:
    await state.update_data(email=None if _is_skip(message.text) else _clean_optional(message.text))
    await state.set_state(DecisionMakerStates.telegram)
    await message.answer("Введите Telegram или нажмите «Пропустить».", reply_markup=flow_menu(allow_skip=True))


@router.message(DecisionMakerStates.telegram)
async def dm_telegram_step(message: Message, state: FSMContext) -> None:
    await state.update_data(telegram=None if _is_skip(message.text) else _clean_optional(message.text))
    await state.set_state(DecisionMakerStates.notes)
    await message.answer("Введите комментарий или нажмите «Пропустить».", reply_markup=flow_menu(allow_skip=True))


@router.message(DecisionMakerStates.notes)
async def dm_notes_step(message: Message, state: FSMContext) -> None:
    notes = None if _is_skip(message.text) else _clean_optional(message.text)
    await state.update_data(notes=notes)
    data = await state.get_data()
    await state.set_state(DecisionMakerStates.confirm)

    preview = (
        "Проверьте ЛПР перед сохранением:\n\n"
        f"ФИО: {data['full_name']}\n"
        f"Должность: {data.get('role') or 'не указана'}\n"
        f"Телефон: {data.get('phone') or 'не указан'}\n"
        f"Email: {data.get('email') or 'не указан'}\n"
        f"Telegram: {data.get('telegram') or 'не указан'}\n"
        f"Комментарий: {notes or 'нет'}"
    )
    await message.answer(
        preview,
        reply_markup=decision_maker_confirm_markup(data["company_id"]),
    )


@router.callback_query(F.data.startswith("dm:save:"))
async def dm_save_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось сохранить ЛПР.", show_alert=True)
        return

    data = await state.get_data()
    if not data:
        await callback.answer("Сценарий ЛПР уже завершен.", show_alert=True)
        return

    payload = DecisionMakerCreate(
        company_id=data["company_id"],
        full_name=data["full_name"],
        role=data.get("role"),
        phone=data.get("phone"),
        email=data.get("email"),
        telegram=data.get("telegram"),
        notes=data.get("notes"),
    )
    async with async_session_factory() as session:
        await add_decision_maker(session, payload)
        await create_note_interaction(
            session,
            data["company_id"],
            f"Добавлен ЛПР: {data['full_name']}",
        )

    await state.clear()
    await callback.answer("ЛПР сохранен.")
    await _show_company_card(callback.message, data["company_id"], edit=True)


@router.callback_query(F.data.startswith("company:contact:"))
async def company_contact_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть контакт.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(company_id=company_id)
    await state.set_state(ContactPointStates.contact_type)
    await callback.answer()
    await callback.message.answer("Выберите тип контакта.", reply_markup=contact_type_menu())


@router.message(ContactPointStates.contact_type)
async def contact_type_step(message: Message, state: FSMContext) -> None:
    raw_value = (message.text or "").strip()
    if raw_value == CANCEL_TEXT:
        await state.clear()
        await message.answer("Добавление контакта отменено.", reply_markup=main_menu())
        return

    contact_type = CONTACT_TYPE_BY_LABEL.get(raw_value)
    if not contact_type:
        await message.answer("Выберите тип контакта из списка.", reply_markup=contact_type_menu())
        return

    await state.update_data(contact_type=contact_type)
    await state.set_state(ContactPointStates.value)
    await message.answer("Введите значение контакта.", reply_markup=flow_menu())


@router.message(ContactPointStates.value)
async def contact_value_step(message: Message, state: FSMContext) -> None:
    value = _clean_optional(message.text)
    if not value or _is_skip(value):
        await message.answer("Значение контакта обязательно.", reply_markup=flow_menu())
        return

    await state.update_data(value=value)
    await state.set_state(ContactPointStates.label)
    await message.answer("Введите метку/комментарий или нажмите «Пропустить».", reply_markup=flow_menu(allow_skip=True))


@router.message(ContactPointStates.label)
async def contact_label_step(message: Message, state: FSMContext) -> None:
    await state.update_data(label=None if _is_skip(message.text) else _clean_optional(message.text))
    await state.set_state(ContactPointStates.is_primary)
    await message.answer("Сделать контакт основным?", reply_markup=yes_no_menu())


@router.message(ContactPointStates.is_primary)
async def contact_primary_step(message: Message, state: FSMContext) -> None:
    answer = (message.text or "").strip()
    if answer not in {YES_TEXT, NO_TEXT}:
        await message.answer("Ответьте «Да» или «Нет».", reply_markup=yes_no_menu())
        return

    data = await state.get_data()
    payload = ContactPointCreate(
        company_id=data["company_id"],
        type=ContactType(data["contact_type"]),
        value=data["value"],
        label=data.get("label"),
        is_primary=answer == YES_TEXT,
    )
    async with async_session_factory() as session:
        await add_contact_point(session, payload)

    await state.clear()
    await message.answer("Контакт сохранен.", reply_markup=main_menu())
    await _show_company_card(message, data["company_id"])


@router.callback_query(F.data.startswith("company:status:"))
async def company_status_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть статусы.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    await _safe_edit_message(
        callback.message,
        "Выберите новый статус компании:",
        reply_markup=status_options_markup(company_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("status:set:"))
async def company_status_set_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось сменить статус.", show_alert=True)
        return

    _, _, company_id_raw, status_value = callback.data.split(":", 3)
    async with async_session_factory() as session:
        company = await change_company_status(session, int(company_id_raw), status_value)

    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return

    await callback.answer("Статус обновлен.")
    await _show_company_card(callback.message, company.id, edit=True)


@router.callback_query(F.data.startswith("company:task:"))
async def company_task_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть задачу.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(company_id=company_id)
    await state.set_state(TaskStates.title)
    await callback.answer()
    await callback.message.answer("Введите название задачи.", reply_markup=flow_menu())


@router.message(TaskStates.title)
async def task_title_step(message: Message, state: FSMContext) -> None:
    title = _clean_optional(message.text)
    if not title or _is_skip(title):
        await message.answer("Название задачи обязательно.", reply_markup=flow_menu())
        return

    await state.update_data(title=title)
    await state.set_state(TaskStates.description)
    await message.answer("Введите описание или нажмите «Пропустить».", reply_markup=flow_menu(allow_skip=True))


@router.message(TaskStates.description)
async def task_description_step(message: Message, state: FSMContext) -> None:
    await state.update_data(description=None if _is_skip(message.text) else _clean_optional(message.text))
    await state.set_state(TaskStates.due_at)
    await message.answer(
        "Введите срок: сегодня, завтра, завтра 12:00, через 2 часа "
        "или 21.05.2026 15:30",
        reply_markup=flow_menu(),
    )


@router.message(TaskStates.due_at)
async def task_due_at_step(message: Message, state: FSMContext) -> None:
    if _is_skip(message.text):
        await message.answer("Для задачи нужен срок.", reply_markup=flow_menu())
        return

    try:
        due_at = parse_due_at_input(message.text or "")
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=flow_menu())
        return

    data = await state.get_data()
    async with async_session_factory() as session:
        await create_company_task(
            session,
            data["company_id"],
            data["title"],
            data.get("description"),
            due_at,
        )

    await state.clear()
    await message.answer("Задача сохранена.", reply_markup=main_menu())
    await _show_company_card(message, data["company_id"])


@router.callback_query(F.data.startswith("company:history:"))
async def company_history_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть историю.", show_alert=True)
        return

    _, _, company_id_raw, offset_raw = callback.data.split(":", 3)
    company_id = int(company_id_raw)
    offset = int(offset_raw)

    async with async_session_factory() as session:
        company = await get_company(session, company_id)
        interactions = await list_interactions(session, company_id, limit=11, offset=offset)

    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return

    visible = interactions[:10]
    next_offset = offset + 10 if len(interactions) > 10 else None
    await _safe_edit_message(
        callback.message,
        _render_history(company.name, visible, offset),
        reply_markup=history_markup(company_id, next_offset),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("company:ai:"))
async def company_ai_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось подготовить AI-ответ.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        result = await prepare_cold_call(session, company_id)

    await callback.answer("AI-подготовка готова.")
    await callback.message.answer(result or "Компания не найдена.")


@router.callback_query(F.data.startswith("task:open:"))
async def task_open_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть компанию.", show_alert=True)
        return

    task_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        task = await get_task(session, task_id)

    if not task:
        await callback.answer("Задача не найдена.", show_alert=True)
        return

    await _show_company_card(callback.message, task.company_id, edit=True)
    await callback.answer()


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

    await callback.answer("Задача отмечена выполненной.")
    await _show_today_tasks(callback.message, edit=True)


@router.callback_query(F.data.startswith("task:shift:"))
async def task_shift_callback(callback: CallbackQuery) -> None:
    await callback.answer("TODO: перенос задачи добавим следующим этапом.", show_alert=True)


@router.message(F.text == "Статистика")
async def stats_placeholder(message: Message) -> None:
    await message.answer("Статистика будет добавлена на следующем этапе.")


@router.message(F.text == "Настройки")
async def settings_placeholder(message: Message) -> None:
    await message.answer("Настройки CRM будут добавлены на следующем этапе. AI-настройки доступны отдельной командой.")
