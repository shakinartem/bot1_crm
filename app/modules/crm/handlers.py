from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from app.database import async_session_factory
from app.modules.crm.schemas import CompanyCreate
from app.modules.crm.service import create_company, format_company_card, get_company, list_companies, search_companies, update_call_result

router = Router(name="crm")


def main_menu() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="Добавить компанию"), KeyboardButton(text="Список лидов")],
        [KeyboardButton(text="Импорт CSV"), KeyboardButton(text="Поиск компании")],
        [KeyboardButton(text="Карточка компании"), KeyboardButton(text="Подготовить звонок")],
        [KeyboardButton(text="Загрузить звонок"), KeyboardButton(text="Указать результат звонка")],
        [KeyboardButton(text="Передать на консультацию"), KeyboardButton(text="Настройки AI")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer("ШАРиК Sales Intelligence готов. Выберите действие.", reply_markup=main_menu())


@router.message(Command("add_company"))
@router.message(F.text == "Добавить компанию")
async def add_company_help(message: Message) -> None:
    await message.answer("Формат: /new_company Название; телефон; сайт; город; заметки")


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
    await message.answer(f"Компания добавлена: #{company.id} {company.name}")


@router.message(Command("leads"))
@router.message(F.text == "Список лидов")
async def leads(message: Message) -> None:
    async with async_session_factory() as session:
        companies = await list_companies(session, limit=15)
    if not companies:
        await message.answer("Лидов пока нет.")
        return
    await message.answer("\n".join(f"#{c.id} {c.name} | {c.status} | {c.phone or 'без телефона'}" for c in companies))


@router.message(Command("search"))
async def search(message: Message) -> None:
    query = (message.text or "").replace("/search", "", 1).strip()
    if not query:
        await message.answer("Формат: /search название, телефон, ИНН или сайт")
        return
    async with async_session_factory() as session:
        companies = await search_companies(session, query)
    await message.answer("\n".join(f"#{c.id} {c.name} | {c.phone or '-'} | {c.website or '-'}" for c in companies) or "Ничего не найдено.")


@router.message(F.text == "Поиск компании")
async def search_help(message: Message) -> None:
    await message.answer("Введите /search и название, телефон, ИНН или сайт.")


@router.message(Command("company"))
async def company_card(message: Message) -> None:
    raw_id = (message.text or "").replace("/company", "", 1).strip()
    if not raw_id.isdigit():
        await message.answer("Формат: /company 12")
        return
    async with async_session_factory() as session:
        company = await get_company(session, int(raw_id))
    await message.answer(format_company_card(company), parse_mode="HTML") if company else await message.answer("Компания не найдена.")


@router.message(F.text == "Карточка компании")
async def company_card_help(message: Message) -> None:
    await message.answer("Введите /company и ID компании, например: /company 12")


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


@router.message(F.text == "Указать результат звонка")
async def call_result_help(message: Message) -> None:
    await message.answer("Формат: /call_result ID; недозвон|отказ|интересно|перезвонить|назначена консультация")


@router.message(F.text == "Передать на консультацию")
async def consultation_help(message: Message) -> None:
    await message.answer("Используйте: /call_result ID; назначена консультация")
