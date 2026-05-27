from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def research_menu_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Проверить сайт", callback_data=f"research:check:{company_id}")],
            [InlineKeyboardButton(text="✍️ Ввести сайт вручную", callback_data=f"research:manual:start:{company_id}")],
            [InlineKeyboardButton(text="📌 Последний research", callback_data=f"research:latest:{company_id}")],
            [InlineKeyboardButton(text="📜 История research", callback_data=f"research:history:{company_id}")],
            [InlineKeyboardButton(text="🤖 AI-резюме", callback_data=f"research:ai:{company_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"company:open:{company_id}")],
        ]
    )


def research_result_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть AI-резюме", callback_data=f"research:ai:{company_id}")],
            [InlineKeyboardButton(text="Добавить в AI-подготовку", callback_data=f"company:ai:{company_id}")],
            [InlineKeyboardButton(text="Сформировать КП", callback_data=f"proposal:open:{company_id}")],
            [InlineKeyboardButton(text="Назад к карточке", callback_data=f"company:open:{company_id}")],
        ]
    )


def research_history_markup(company_id: int, snapshot_ids: list[int]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"Snapshot #{snapshot_id}", callback_data=f"research:snapshot:{company_id}:{snapshot_id}")]
        for snapshot_id in snapshot_ids
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"research:open:{company_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def research_snapshot_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 AI-резюме", callback_data=f"research:ai:{company_id}")],
            [InlineKeyboardButton(text="⬅️ Назад к Research", callback_data=f"research:open:{company_id}")],
        ]
    )
