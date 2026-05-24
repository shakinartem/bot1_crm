from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def daily_digest_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔴 Просроченные", callback_data="digest:overdue")],
            [InlineKeyboardButton(text="🟡 Сегодня", callback_data="digest:today")],
            [InlineKeyboardButton(text="🔥 Горячие", callback_data="digest:hot")],
            [InlineKeyboardButton(text="🧊 Без касаний", callback_data="digest:stale")],
            [InlineKeyboardButton(text="📊 Неделя", callback_data="digest:weekly")],
            [InlineKeyboardButton(text="⚙️ Настройки дайджеста", callback_data="digest:settings")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="digest:menu")],
        ]
    )


def digest_task_list_markup(tasks: list, *, section: str) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    for task in tasks:
        rows.append(
            [
                InlineKeyboardButton(text=f"Открыть #{task.company_id}", callback_data=f"digest:open_company:{task.company_id}"),
                InlineKeyboardButton(text="✅ Выполнено", callback_data=f"digest:task_done:{task.task_id}:{section}"),
                InlineKeyboardButton(text="🔁 Перенести", callback_data=f"digest:task_snooze:{task.task_id}:{section}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ К плану дня", callback_data="digest:daily")])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def digest_lead_list_markup(leads: list, *, prefix: str) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    for lead in leads:
        rows.append(
            [
                InlineKeyboardButton(text=f"Открыть #{lead.company_id}", callback_data=f"digest:open_company:{lead.company_id}"),
                InlineKeyboardButton(text="📞 Звонок", callback_data=f"company:call:{lead.company_id}"),
                InlineKeyboardButton(text="✅ Задача", callback_data=f"company:task:{lead.company_id}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ К плану дня", callback_data="digest:daily")])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def digest_settings_markup(enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = "Выключить авто-дайджест" if enabled else "Включить авто-дайджест"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data="digest:settings:toggle")],
            [InlineKeyboardButton(text="Изменить время", callback_data="digest:settings:time")],
            [InlineKeyboardButton(text="Изменить период без касаний", callback_data="digest:settings:stale")],
            [InlineKeyboardButton(text="Назад", callback_data="digest:daily")],
        ]
    )
