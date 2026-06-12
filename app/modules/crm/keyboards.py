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
        [KeyboardButton(text="🔍 Поиск компаний")],
        [KeyboardButton(text="🏢 CRM / Компании"), KeyboardButton(text="👤 Мои лиды")],
        [KeyboardButton(text="📞 Продажи"), KeyboardButton(text="🏷 Группы лидов")],
        [KeyboardButton(text="📅 Мои касания"), KeyboardButton(text="📄 КП и документы")],
        [KeyboardButton(text="🧠 AI / Research"), KeyboardButton(text="📊 Аналитика")],
        [KeyboardButton(text="⚙️ Настройки")],
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


def search_import_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Поиск компаний", callback_data="menu:search_import:companies")],
            [InlineKeyboardButton(text="📥 Импорт CSV", callback_data="menu:search_import:import_csv")],
            [InlineKeyboardButton(text="🔎 Поиск по CRM", callback_data="menu:search_import:crm_search")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def crm_section_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список компаний", callback_data="menu:crm:list")],
            [InlineKeyboardButton(text="🏷 Группы лидов", callback_data="menu:crm:lead_groups")],
            [InlineKeyboardButton(text="📅 Мои касания", callback_data="menu:crm:my_touches")],
            [InlineKeyboardButton(text="🗺 Города и регионы", callback_data="menu:crm:regions")],
            [InlineKeyboardButton(text="🏙 Компании по городу", callback_data="menu:crm:cities")],
            [InlineKeyboardButton(text="➕ Добавить компанию", callback_data="menu:crm:add")],
            [InlineKeyboardButton(text="🔎 Поиск по CRM", callback_data="menu:crm:search")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def leads_section_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Мои задачи на сегодня", callback_data="menu:leads:today")],
            [InlineKeyboardButton(text="📅 Мои касания", callback_data="menu:crm:my_touches")],
            [InlineKeyboardButton(text="📋 Последние компании", callback_data="menu:leads:companies")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def sales_section_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📞 Как открыть план звонка", callback_data="menu:sales:call_plan_help")],
            [InlineKeyboardButton(text="🧠 Где смотреть SOPRANO", callback_data="menu:sales:soprano_help")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def proposals_section_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Открыть КП / договор в карточке", callback_data="menu:docs:proposal_help")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def ai_research_section_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 Research и legal discovery", callback_data="menu:ai:research")],
            [InlineKeyboardButton(text="🧾 INN / Intelligence", callback_data="menu:ai:intelligence")],
            [InlineKeyboardButton(text="🤖 Bot2 context", callback_data="menu:ai:bot2")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def settings_section_menu_markup(include_admin_reset: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="ℹ️ Состояние системы", callback_data="menu:settings:system")],
        [InlineKeyboardButton(text="🔎 Настройки поиска", callback_data="menu:settings:search")],
    ]
    if include_admin_reset:
        rows.append([InlineKeyboardButton(text="🧹 Очистить CRM-данные", callback_data="admin:reset:crm:start")])
        rows.append([InlineKeyboardButton(text="🧨 Очистить все данные", callback_data="admin:reset:all:start")])
    rows.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lead_groups_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔥 Горячие", callback_data="leadfit:group:A_hot_priority:0")],
            [InlineKeyboardButton(text="🟡 Перспективные", callback_data="leadfit:group:B_warm_potential:0")],
            [InlineKeyboardButton(text="⚪ Нейтральные", callback_data="leadfit:group:C_neutral_database:0")],
            [InlineKeyboardButton(text="🔻 Низкий приоритет", callback_data="leadfit:group:D_low_priority:0")],
            [InlineKeyboardButton(text="🚫 Исключённые", callback_data="leadfit:group:excluded_do_not_contact:0")],
            [InlineKeyboardButton(text="🔄 Пересчитать группы", callback_data="leadfit:recalculate_all")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:crm:list")],
        ]
    )


def company_actions(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Рассчитать приоритет", callback_data=f"leadfit:recalculate:{company_id}"),
                InlineKeyboardButton(text="🧠 Website research", callback_data=f"leadfit:website:{company_id}"),
            ],
            [
                InlineKeyboardButton(text="📅 План 7 касаний", callback_data=f"touch:open:{company_id}"),
                InlineKeyboardButton(text="🗑 Удалить компанию", callback_data=f"company:delete:{company_id}"),
            ],
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
            [InlineKeyboardButton(text="👤 Назначить на себя", callback_data=f"company:assignme:{company_id}")],
            [
                InlineKeyboardButton(text="📝 История", callback_data=f"company:history:{company_id}:0"),
                InlineKeyboardButton(text="🤖 AI-подготовка", callback_data=f"company:ai:{company_id}"),
            ],
            [
                InlineKeyboardButton(text="🔎 Research", callback_data=f"research:open:{company_id}"),
                InlineKeyboardButton(text="🧾 INN / Intelligence", callback_data=f"intelligence:open:{company_id}"),
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
        [InlineKeyboardButton(text=f"#{company.id} {company.name[:28]}", callback_data=f"company:open:{company.id}")]
        for company in companies
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lead_group_companies_markup(companies: list[Any], group: str, page: int, has_next_page: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"#{company.id} {company.name[:28]}", callback_data=f"company:open:{company.id}")]
        for company in companies
    ]
    if has_next_page:
        rows.append([InlineKeyboardButton(text="➡️ Следующая страница", callback_data=f"leadfit:group:{group}:{page + 1}")])
    rows.append([InlineKeyboardButton(text="⬅️ К группам", callback_data="menu:crm:lead_groups")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def simple_menu_markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def stats_company_list_markup(companies: list[Any]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"#{company.id} {company.name[:28]}", callback_data=f"company:open:{company.id}")]
        for company in companies
    ]
    rows.append([InlineKeyboardButton(text="⬅️ К статистике", callback_data="stats:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def call_results_markup(company_id: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"call:pick:{company_id}:{code}")] for label, code in CALL_RESULT_OPTIONS]
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
        rows.append([InlineKeyboardButton(text="Показать ещё", callback_data=f"company:history:{company_id}:{next_offset}")])
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


def today_tasks_markup(tasks: list[Any], *, back_callback: str = "menu:leads:today") -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    for task in tasks:
        rows.append(
            [
                InlineKeyboardButton(text=f"Открыть #{task.company_id}", callback_data=f"task:open:{task.id}"),
                InlineKeyboardButton(text="Выполнено", callback_data=f"task:done:{task.id}"),
                InlineKeyboardButton(text="Перенести", callback_data=f"task:shift:{task.id}"),
            ]
        )
    if rows:
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)])
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


def touch_plan_markup(company_id: int, *, has_plan: bool, current_task_id: int | None = None) -> InlineKeyboardMarkup:
    if not has_plan:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Создать план 7 касаний", callback_data=f"touch:create:{company_id}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"company:open:{company_id}")],
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отметить касание выполненным", callback_data=f"touch:done:{current_task_id or 0}")],
            [InlineKeyboardButton(text="➕ Записать касание", callback_data=f"touch:note:{company_id}")],
            [InlineKeyboardButton(text="▶️ Следующее касание", callback_data=f"touch:open:{company_id}")],
            [InlineKeyboardButton(text="📅 Открытые задачи", callback_data=f"touch:tasks:{company_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"company:open:{company_id}")],
        ]
    )


def company_delete_confirm_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, удалить", callback_data=f"company:delete:confirm:{company_id}")],
            [InlineKeyboardButton(text="Отмена", callback_data=f"company:open:{company_id}")],
        ]
    )


def stats_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Новые лиды", callback_data="stats:companies:new")],
            [InlineKeyboardButton(text="Просроченные задачи", callback_data="stats:tasks:overdue")],
            [InlineKeyboardButton(text="Интересные", callback_data="stats:companies:interested")],
            [InlineKeyboardButton(text="Назад", callback_data="stats:menu")],
        ]
    )
