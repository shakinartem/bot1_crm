from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.modules.crm.constants import CompanyStatus


def analytics_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Воронка продаж", callback_data="analytics:funnel")],
            [InlineKeyboardButton(text="🧲 Источники лидов", callback_data="analytics:sources")],
            [InlineKeyboardButton(text="🏙 Города / регионы", callback_data="analytics:cities")],
            [InlineKeyboardButton(text="🔥 Скоринг лидов", callback_data="analytics:scores:all")],
            [InlineKeyboardButton(text="🧊 Холодная база", callback_data="analytics:cold")],
            [InlineKeyboardButton(text="📤 Экспорт аналитики", callback_data="analytics:export")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="analytics:back")],
        ]
    )


def analytics_funnel_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Показать лидов в статусе", callback_data="analytics:funnel:statuses")],
            [InlineKeyboardButton(text="Экспорт", callback_data="analytics:export:funnel")],
            [InlineKeyboardButton(text="Назад", callback_data="analytics:menu")],
        ]
    )


def analytics_funnel_status_markup() -> InlineKeyboardMarkup:
    statuses = [
        CompanyStatus.NEW.value,
        CompanyStatus.RESEARCH_NEEDED.value,
        CompanyStatus.PREPARED.value,
        CompanyStatus.CALL_PLANNED.value,
        CompanyStatus.CALLED.value,
        CompanyStatus.INTERESTED.value,
        CompanyStatus.CONSULTATION_PLANNED.value,
        CompanyStatus.PROPOSAL_SENT.value,
        CompanyStatus.DEAL_WON.value,
        CompanyStatus.DEAL_LOST.value,
    ]
    rows = [
        [InlineKeyboardButton(text=status, callback_data=f"analytics:funnel:status:{status}")]
        for status in statuses
    ]
    rows.append([InlineKeyboardButton(text="Назад", callback_data="analytics:funnel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def analytics_sources_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Лучшие источники", callback_data="analytics:sources:best")],
            [InlineKeyboardButton(text="Слабые источники", callback_data="analytics:sources:weak")],
            [InlineKeyboardButton(text="Экспорт CSV", callback_data="analytics:export:sources")],
            [InlineKeyboardButton(text="Назад", callback_data="analytics:menu")],
        ]
    )


def analytics_cities_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Лучшие города", callback_data="analytics:cities:best")],
            [InlineKeyboardButton(text="Города с просрочкой", callback_data="analytics:cities:overdue")],
            [InlineKeyboardButton(text="Экспорт CSV", callback_data="analytics:export:cities")],
            [InlineKeyboardButton(text="Назад", callback_data="analytics:menu")],
        ]
    )


def analytics_scores_filter_markup(current_filter: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=_filter_label("all", current_filter), callback_data="analytics:scores:all"),
            InlineKeyboardButton(text=_filter_label("hot", current_filter), callback_data="analytics:scores:hot"),
            InlineKeyboardButton(text=_filter_label("priority", current_filter), callback_data="analytics:scores:priority"),
        ],
        [
            InlineKeyboardButton(text=_filter_label("no_task", current_filter), callback_data="analytics:scores:no_task"),
            InlineKeyboardButton(text=_filter_label("overdue", current_filter), callback_data="analytics:scores:overdue"),
        ],
        [InlineKeyboardButton(text="Экспорт CSV", callback_data="analytics:export:scores")],
        [InlineKeyboardButton(text="Назад", callback_data="analytics:menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def analytics_score_actions_markup(items: list, current_filter: str) -> InlineKeyboardMarkup | None:
    if not items:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        rows.append(
            [
                InlineKeyboardButton(text=f"Открыть #{item.company_id}", callback_data=f"company:open:{item.company_id}"),
                InlineKeyboardButton(text="AI-подготовка", callback_data=f"company:ai:{item.company_id}"),
                InlineKeyboardButton(text="Поставить задачу", callback_data=f"company:task:{item.company_id}"),
            ]
        )
        if item.can_prepare_proposal:
            rows.append([InlineKeyboardButton(text="📄 КП / Договор", callback_data=f"proposal:open:{item.company_id}")])
    rows.extend(analytics_scores_filter_markup(current_filter).inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def analytics_cold_base_markup(items: list) -> InlineKeyboardMarkup | None:
    if not items:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        rows.append(
            [
                InlineKeyboardButton(text=f"Открыть #{item.company_id}", callback_data=f"company:open:{item.company_id}"),
                InlineKeyboardButton(text="AI-подготовка", callback_data=f"company:ai:{item.company_id}"),
                InlineKeyboardButton(text="Поставить задачу", callback_data=f"company:task:{item.company_id}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="Экспорт", callback_data="analytics:export:cold_base")])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="analytics:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def analytics_export_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Funnel CSV", callback_data="analytics:export:funnel")],
            [InlineKeyboardButton(text="Sources CSV", callback_data="analytics:export:sources")],
            [InlineKeyboardButton(text="Cities CSV", callback_data="analytics:export:cities")],
            [InlineKeyboardButton(text="Scores CSV", callback_data="analytics:export:scores")],
            [InlineKeyboardButton(text="Cold Base CSV", callback_data="analytics:export:cold_base")],
            [InlineKeyboardButton(text="Назад", callback_data="analytics:menu")],
        ]
    )


def _filter_label(code: str, current_filter: str) -> str:
    labels = {
        "all": "Все",
        "hot": "Hot",
        "priority": "Priority",
        "no_task": "Без задачи",
        "overdue": "Просроченные",
    }
    prefix = "✅ " if code == current_filter else ""
    return f"{prefix}{labels[code]}"
