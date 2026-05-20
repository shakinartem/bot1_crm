from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from app.database import async_session_factory
from app.modules.ai.service import prepare_cold_call
from app.modules.crm.constants import TaskStatus
from app.modules.crm.schemas import CompanyCreate
from app.modules.crm.service import (
    create_company,
    format_company_card,
    get_company,
    list_companies,
    list_tasks,
    search_companies,
    update_call_result,
)

router = Router(name="crm")

SKIP_TEXT = "Пропустить"
CANCEL_TEXT = "Отмена"

CALL_RESULT_LABELS = {
    "no_answer": "Недозвон",
    "interested": "Интересно",
    "callback_requested": "Перезвонить",
    "consultation_booked": "Консультация",
    "rejected": "Отказ",
}

STATUS_LABELS = {
    "new": "Новый",
    "research_needed": "Нужно исследование",
    "prepared": "Подготовлен",
    "call_planned": "Звонок запланирован",
    "called": "Созвонились",
    "no_answer": "Недозвон",
    "interested": "Заинтересован",
    "consultation_planned": "Консультация назначена",
    "proposal_sent": "Отправлено предложение",
    "deal_won": "Сделка выиграна",
    "deal_lost": "Сделка проиграна",
    "do_not_contact": "Не беспокоить",
}


class CompanyCreateStates(StatesGroup):
    name = State()
    phone = State()
    website = State()
    city = State()
    notes = State()


class CompanySearchStates(StatesGroup):
    query = State()


def main_menu() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="Компании"), KeyboardButton(text="Добавить компанию")],
        [KeyboardButton(text="Поиск"), KeyboardButton(text="Импорт CSV")],
        [KeyboardButton(text="Задачи на сегодня"), KeyboardButton(text="AI-подготовка к звонку")],
        [KeyboardButton(text="Статистика"), KeyboardButton(text="Настройки")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def flow_menu(*, allow_skip: bool = False) -> ReplyKeyboardMarkup:
    buttons = [KeyboardButton(text=CANCEL_TEXT)]
    if allow_skip:
        buttons.insert(0, KeyboardButton(text=SKIP_TEXT))
    return ReplyKeyboardMarkup(keyboard=[buttons], resize_keyboard=True)


def company_actions(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Обновить", callback_data=f"company:refresh:{company_id}"),
                InlineKeyboardButton(text="AI-подготовка", callback_data=f"company:prepare:{company_id}"),
            ],
            [
                InlineKeyboardButton(text="Задачи", callback_data=f"company:tasks:{company_id}"),
            ],
            [
                InlineKeyboardButton(text="Недозвон", callback_data=f"company:result:{company_id}:no_answer"),
                InlineKeyboardButton(text="Интересно", callback_data=f"company:result:{company_id}:interested"),
            ],
            [
                InlineKeyboardButton(text="Перезвонить", callback_data=f"company:result:{company_id}:callback_requested"),
                InlineKeyboardButton(text="Консультация", callback_data=f"company:result:{company_id}:consultation_booked"),
            ],
            [
                InlineKeyboardButton(text="Отказ", callback_data=f"company:result:{company_id}:rejected"),
            ],
        ]
    )


def company_list_markup(companies: list) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"#{company.id} {company.name[:28]}",
                callback_data=f"company:open:{company.id}",
            )
        ]
        for company in companies
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_company_preview(company) -> str:
    status = STATUS_LABELS.get(company.status, company.status)
    return f"#{company.id} {company.name} | {status} | {company.phone or 'без телефона'}"


def format_tasks_digest(tasks: list) -> str:
    if not tasks:
        return "На сегодня открытых задач нет."

    lines = ["Задачи на сегодня и просроченные:"]
    for task in tasks:
        due_label = task.due_at.strftime("%d.%m %H:%M") if task.due_at else "без срока"
        company_name = task.company.name if getattr(task, "company", None) else f"Компания #{task.company_id}"
        lines.append(f"- [{due_label}] {task.title} — {company_name}")
    return "\n".join(lines)


def parse_company_id(raw_text: str | None, command: str) -> int | None:
    raw_id = (raw_text or "").replace(command, "", 1).strip()
    return int(raw_id) if raw_id.isdigit() else None


def is_skip(text: str | None) -> bool:
    return (text or "").strip() == SKIP_TEXT


def cleaned_optional(text: str | None) -> str | None:
    value = (text or "").strip()
    return value or None


async def show_company_card(target, company_id: int) -> bool:
    async with async_session_factory() as session:
        company = await get_company(session, company_id)
    if not company:
        return False
    await target.answer(format_company_card(company), parse_mode="HTML", reply_markup=company_actions(company_id))
    return True


async def edit_company_card(message: Message, company_id: int) -> bool:
    async with async_session_factory() as session:
        company = await get_company(session, company_id)
    if not company:
        return False

    try:
        await message.edit_text(
            format_company_card(company),
            parse_mode="HTML",
            reply_markup=company_actions(company_id),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await message.edit_reply_markup(reply_markup=company_actions(company_id))
    return True


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("ШАРиК Sales Intelligence готов. Выберите действие.", reply_markup=main_menu())


@router.message(Command("menu"))
async def menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Главное меню CRM.", reply_markup=main_menu())


@router.message(Command("cancel"))
@router.message(F.text == CANCEL_TEXT)
async def cancel_flow(message: Message, state: FSMContext) -> None:
    if await state.get_state():
        await state.clear()
        await message.answer("Текущее действие отменено.", reply_markup=main_menu())
        return
    await message.answer("Вы уже в главном меню.", reply_markup=main_menu())


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
        await message.answer("Укажите минимум название: /new_company Клиника Улыбка; +79990000000; https://site.ru")
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
    await show_company_card(message, company.id)


@router.message(CompanyCreateStates.name)
async def company_creation_name(message: Message, state: FSMContext) -> None:
    name = cleaned_optional(message.text)
    if not name or is_skip(name):
        await message.answer("Название обязательно. Введите название компании.", reply_markup=flow_menu())
        return

    await state.update_data(name=name)
    await state.set_state(CompanyCreateStates.phone)
    await message.answer("Введите телефон или нажмите «Пропустить».", reply_markup=flow_menu(allow_skip=True))


@router.message(CompanyCreateStates.phone)
async def company_creation_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=None if is_skip(message.text) else cleaned_optional(message.text))
    await state.set_state(CompanyCreateStates.website)
    await message.answer("Введите сайт компании или нажмите «Пропустить».", reply_markup=flow_menu(allow_skip=True))


@router.message(CompanyCreateStates.website)
async def company_creation_website(message: Message, state: FSMContext) -> None:
    await state.update_data(website=None if is_skip(message.text) else cleaned_optional(message.text))
    await state.set_state(CompanyCreateStates.city)
    await message.answer("Введите город или нажмите «Пропустить».", reply_markup=flow_menu(allow_skip=True))


@router.message(CompanyCreateStates.city)
async def company_creation_city(message: Message, state: FSMContext) -> None:
    await state.update_data(city=None if is_skip(message.text) else cleaned_optional(message.text))
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
        notes=None if is_skip(message.text) else cleaned_optional(message.text),
    )

    async with async_session_factory() as session:
        company = await create_company(session, payload)

    await state.clear()
    await message.answer(
        f"Компания создана: #{company.id} {company.name}",
        reply_markup=main_menu(),
    )
    await show_company_card(message, company.id)


@router.message(Command("leads"))
@router.message(F.text == "Компании")
async def leads(message: Message) -> None:
    async with async_session_factory() as session:
        companies = await list_companies(session, limit=15)
    if not companies:
        await message.answer("Лидов пока нет.")
        return

    lines = ["Последние компании:", *[format_company_preview(company) for company in companies]]
    await message.answer("\n".join(lines), reply_markup=company_list_markup(companies))


@router.message(Command("search"))
async def search(message: Message, state: FSMContext) -> None:
    query = (message.text or "").replace("/search", "", 1).strip()
    if not query:
        await state.set_state(CompanySearchStates.query)
        await message.answer(
            "Введите название, телефон, ИНН, город, сайт или ФИО ЛПР.",
            reply_markup=flow_menu(),
        )
        return

    async with async_session_factory() as session:
        companies = await search_companies(session, query)
    await message.answer(
        "\n".join(format_company_preview(company) for company in companies) or "Ничего не найдено.",
        reply_markup=company_list_markup(companies) if companies else None,
    )


@router.message(F.text == "Поиск")
async def search_help(message: Message, state: FSMContext) -> None:
    await state.set_state(CompanySearchStates.query)
    await message.answer(
        "Введите название, телефон, ИНН, город, сайт или ФИО ЛПР.",
        reply_markup=flow_menu(),
    )


@router.message(CompanySearchStates.query)
async def search_from_state(message: Message, state: FSMContext) -> None:
    query = cleaned_optional(message.text)
    if not query or is_skip(query):
        await message.answer("Поисковый запрос не должен быть пустым.", reply_markup=flow_menu())
        return

    async with async_session_factory() as session:
        companies = await search_companies(session, query)

    await state.clear()
    await message.answer(
        "\n".join(format_company_preview(company) for company in companies) or "Ничего не найдено.",
        reply_markup=company_list_markup(companies) if companies else main_menu(),
    )
    if companies:
        await message.answer("Откройте карточку кнопкой ниже или начните новый поиск.", reply_markup=main_menu())


@router.message(Command("company"))
async def company_card(message: Message) -> None:
    company_id = parse_company_id(message.text, "/company")
    if company_id is None:
        await message.answer("Формат: /company 12")
        return
    if not await show_company_card(message, company_id):
        await message.answer("Компания не найдена.")


@router.message(Command("call_result"))
async def call_result(message: Message) -> None:
    raw = (message.text or "").replace("/call_result", "", 1).strip()
    parts = [part.strip().lower() for part in raw.split(";")]
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer("Формат: /call_result ID; недозвон|отказ|интересно|перезвонить|назначена консультация")
        return
    async with async_session_factory() as session:
        company = await update_call_result(session, int(parts[0]), parts[1])
    await message.answer(f"Результат сохранен. Статус: {company.status}") if company else await message.answer("Компания не найдена.")


@router.message(F.text == "Задачи на сегодня")
async def today_tasks(message: Message) -> None:
    async with async_session_factory() as session:
        tasks = await list_tasks(session, status=TaskStatus.OPEN.value)
        today = datetime.now().date()
        due_tasks = [task for task in tasks if task.due_at and task.due_at.date() <= today]

    await message.answer(format_tasks_digest(due_tasks[:10]))
    if due_tasks:
        companies = []
        seen_company_ids = set()
        for task in due_tasks[:10]:
            company = getattr(task, "company", None)
            if not company or company.id in seen_company_ids:
                continue
            seen_company_ids.add(company.id)
            companies.append(company)
        await message.answer(
            "Карточки компаний по задачам:",
            reply_markup=company_list_markup(companies),
        )


@router.callback_query(F.data.startswith("company:open:"))
@router.callback_query(F.data.startswith("company:refresh:"))
async def company_card_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть карточку.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    if not await edit_company_card(callback.message, company_id):
        await callback.answer("Компания не найдена.", show_alert=True)
        return
    await callback.answer("Карточка обновлена.")


@router.callback_query(F.data.startswith("company:prepare:"))
async def company_prepare_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось показать подготовку.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        result = await prepare_cold_call(session, company_id)
    await callback.answer("Подготовка готова.")
    await callback.message.answer(result or "Компания не найдена.")


@router.callback_query(F.data.startswith("company:tasks:"))
async def company_tasks_callback(callback: CallbackQuery) -> None:
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        company = await get_company(session, company_id)
    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return

    open_tasks = [task for task in company.tasks if task.status == TaskStatus.OPEN.value]
    if not open_tasks:
        await callback.answer("Открытых задач нет.")
        return

    lines = [f"Открытые задачи по #{company.id} {company.name}:"]
    for task in open_tasks[:10]:
        due_label = task.due_at.strftime("%d.%m %H:%M") if task.due_at else "без срока"
        lines.append(f"- [{due_label}] {task.title}")
    await callback.answer()
    await callback.message.answer("\n".join(lines))


@router.callback_query(F.data.startswith("company:result:"))
async def company_result_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось обновить статус.", show_alert=True)
        return

    _, _, company_id_raw, result_code = callback.data.split(":", 3)
    company_id = int(company_id_raw)

    async with async_session_factory() as session:
        company = await update_call_result(session, company_id, result_code)

    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return

    await edit_company_card(callback.message, company_id)
    await callback.answer(f"Статус обновлен: {CALL_RESULT_LABELS.get(result_code, result_code)}")


@router.message(F.text == "Статистика")
async def stats_placeholder(message: Message) -> None:
    await message.answer("Статистика будет добавлена на следующем этапе.")


@router.message(F.text == "Настройки")
async def settings_placeholder(message: Message) -> None:
    await message.answer("Настройки CRM будут добавлены на следующем этапе. AI-настройки доступны отдельной командой.")
