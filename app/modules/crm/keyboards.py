from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app.modules.crm.constants import COMPANY_STATUS_LABELS, CONTACT_TYPE_LABELS


SKIP_TEXT = "Пропустить"
CANCEL_TEXT = "Отмена"
YES_TEXT = "Да"
NO_TEXT = "Нет"

CALL_RESULT_OPTIONS = [
    ("Не дозвонился", "no_answer"),
    ("Интересно", "interested"),
    ("Перезвонить позже", "callback_requested"),
    ("Отказ", "rejected"),
    ("Запросили КП", "proposal_requested"),
    ("Назначена консультация", "consultation_booked"),
    ("Сделка", "deal_won"),
    ("Другое", "other"),
]


def main_menu() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="Компании"), KeyboardButton(text="Добавить компанию")],
        [KeyboardButton(text="Поиск"), KeyboardButton(text="Импорт CSV")],
        [KeyboardButton(text="Задачи на сегодня"), KeyboardButton(text="AI-подготовка к звонку")],
        [KeyboardButton(text="Статистика"), KeyboardButton(text="📈 Аналитика")],
        [KeyboardButton(text="📤 Экспорт"), KeyboardButton(text="🗓 План дня")],
        [KeyboardButton(text="Настройки")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def flow_menu(*, allow_skip: bool = False) -> ReplyKeyboardMarkup:
    buttons = [KeyboardButton(text=CANCEL_TEXT)]
    if allow_skip:
        buttons.insert(0, KeyboardButton(text=SKIP_TEXT))
    return ReplyKeyboardMarkup(keyboard=[buttons], resize_keyboard=True)


def yes_no_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=YES_TEXT), KeyboardButton(text=NO_TEXT)], [KeyboardButton(text=CANCEL_TEXT)]],
        resize_keyboard=True,
    )


def contact_type_menu() -> ReplyKeyboardMarkup:
    buttons = [[KeyboardButton(text=label)] for label in CONTACT_TYPE_LABELS.values()]
    buttons.append([KeyboardButton(text=CANCEL_TEXT)])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def company_actions(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📞 Добавить звонок", callback_data=f"company:call:{company_id}"),
                InlineKeyboardButton(text="🧾 Добавить заметку", callback_data=f"company:note:{company_id}"),
            ],
            [
                InlineKeyboardButton(text="👤 Добавить ЛПР", callback_data=f"company:dm:{company_id}"),
                InlineKeyboardButton(text="☎️ Добавить контакт", callback_data=f"company:contact:{company_id}"),
            ],
            [
                InlineKeyboardButton(text="🔄 Сменить статус", callback_data=f"company:status:{company_id}"),
                InlineKeyboardButton(text="✅ Добавить задачу", callback_data=f"company:task:{company_id}"),
            ],
            [
                InlineKeyboardButton(text="📜 История", callback_data=f"company:history:{company_id}:0"),
                InlineKeyboardButton(text="🤖 AI-подготовка", callback_data=f"company:ai:{company_id}"),
            ],
            [
                InlineKeyboardButton(text="📦 Пакет консультации", callback_data=f"consult:package:{company_id}"),
                InlineKeyboardButton(text="📄 КП / Договор", callback_data=f"proposal:open:{company_id}"),
            ],
            [InlineKeyboardButton(text="📤 Экспортировать компанию", callback_data=f"consult:export_company:{company_id}")],
            [InlineKeyboardButton(text="🚀 Подготовить передачу в БОТ 2", callback_data=f"consult:handoff:{company_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="company:list")],
        ]
    )


def company_list_markup(companies: list[Any]) -> InlineKeyboardMarkup:
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


def stats_company_list_markup(companies: list[Any]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"#{company.id} {company.name[:28]}",
                callback_data=f"company:open:{company.id}",
            )
        ]
        for company in companies
    ]
    rows.append([InlineKeyboardButton(text="⬅️ К статистике", callback_data="stats:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def call_results_markup(company_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"call:pick:{company_id}:{code}")]
        for label, code in CALL_RESULT_OPTIONS
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"company:open:{company_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def status_options_markup(company_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"status:set:{company_id}:{value}")]
        for value, label in COMPANY_STATUS_LABELS.items()
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"company:open:{company_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def decision_maker_confirm_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сохранить", callback_data=f"dm:save:{company_id}"),
                InlineKeyboardButton(text="Отмена", callback_data=f"company:open:{company_id}"),
            ]
        ]
    )


def history_markup(company_id: int, next_offset: int | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if next_offset is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Показать ещё",
                    callback_data=f"company:history:{company_id}:{next_offset}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Назад к карточке", callback_data=f"company:open:{company_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def follow_up_task_prompt_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Добавить задачу", callback_data=f"company:task:{company_id}"),
                InlineKeyboardButton(text="⬅️ К карточке", callback_data=f"company:open:{company_id}"),
            ]
        ]
    )


def today_tasks_markup(tasks: list[Any]) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    for task in tasks:
        rows.append(
            [
                InlineKeyboardButton(text=f"Открыть #{task.company_id}", callback_data=f"task:open:{task.id}"),
                InlineKeyboardButton(text="Выполнено", callback_data=f"task:done:{task.id}"),
                InlineKeyboardButton(text="Перенести", callback_data=f"task:shift:{task.id}"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def stats_tasks_markup(tasks: list[Any]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for task in tasks:
        rows.append(
            [
                InlineKeyboardButton(text=f"Открыть #{task.company_id}", callback_data=f"task:open:{task.id}"),
                InlineKeyboardButton(text="Выполнено", callback_data=f"task:done:{task.id}"),
                InlineKeyboardButton(text="Перенести", callback_data=f"task:shift:{task.id}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ К статистике", callback_data="stats:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def stats_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Новые лиды", callback_data="stats:companies:new")],
            [InlineKeyboardButton(text="Просроченные задачи", callback_data="stats:tasks:overdue")],
            [InlineKeyboardButton(text="Интересные", callback_data="stats:companies:interested")],
            [InlineKeyboardButton(text="Назад", callback_data="stats:menu")],
        ]
    )
