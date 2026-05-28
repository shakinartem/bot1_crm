from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def intelligence_menu_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 Найти ИНН по названию", callback_data=f"intelligence:find_legal:{company_id}")],
            [InlineKeyboardButton(text="🧾 Проверить по ИНН", callback_data=f"intelligence:check_inn:{company_id}")],
            [InlineKeyboardButton(text="🌐 Найти сайт по ИНН", callback_data=f"intelligence:resolve_website:{company_id}")],
            [InlineKeyboardButton(text="🌐 Найти сайт по юр. названию", callback_data=f"intelligence:resolve_legal:{company_id}")],
            [InlineKeyboardButton(text="🧠 Полное обогащение", callback_data=f"intelligence:enrich:{company_id}")],
            [InlineKeyboardButton(text="📌 Последний результат", callback_data=f"intelligence:latest:{company_id}")],
            [InlineKeyboardButton(text="📜 История", callback_data=f"intelligence:history:{company_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"company:open:{company_id}")],
        ]
    )


def intelligence_result_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Добавить в карточку", callback_data=f"company:open:{company_id}"),
                InlineKeyboardButton(text="AI-подготовка к звонку", callback_data=f"company:ai:{company_id}"),
            ],
            [
                InlineKeyboardButton(text="Сформировать КП", callback_data=f"proposal:open:{company_id}"),
                InlineKeyboardButton(text="⬅️ Назад", callback_data=f"intelligence:open:{company_id}"),
            ],
        ]
    )


def intelligence_history_markup(company_id: int, snapshot_ids: list[int]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"Открыть #{snapshot_id}", callback_data=f"intelligence:snapshot:{company_id}:{snapshot_id}")]
        for snapshot_id in snapshot_ids[:10]
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"intelligence:open:{company_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def intelligence_legal_candidates_markup(company_id: int, count: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"Выбрать {index}", callback_data=f"intelligence:pick_legal:{company_id}:{index}")]
        for index in range(1, count + 1)
    ]
    rows.append([InlineKeyboardButton(text="Отмена", callback_data=f"intelligence:open:{company_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
