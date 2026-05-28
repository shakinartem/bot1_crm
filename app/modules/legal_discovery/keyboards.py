from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def discovery_provider_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Mock / Dev", callback_data="discovery:provider:mock")],
            [InlineKeyboardButton(text="ФНС / API-ФНС", callback_data="discovery:provider:api_fns")],
            [InlineKeyboardButton(text="DaData", callback_data="discovery:provider:dadata")],
        ]
    )


def discovery_niche_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="стоматология", callback_data="discovery:niche:стоматология")],
            [InlineKeyboardButton(text="стоматологическая клиника", callback_data="discovery:niche:стоматологическая клиника")],
            [InlineKeyboardButton(text="медицинская организация", callback_data="discovery:niche:медицинская организация")],
            [InlineKeyboardButton(text="ручной ввод", callback_data="discovery:niche:manual")],
        ]
    )


def discovery_limit_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="25", callback_data="discovery:limit:25")],
            [InlineKeyboardButton(text="50", callback_data="discovery:limit:50")],
            [InlineKeyboardButton(text="100", callback_data="discovery:limit:100")],
            [InlineKeyboardButton(text="500", callback_data="discovery:limit:500")],
        ]
    )


def discovery_preview_markup(preview_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Импортировать активные новые", callback_data=f"discovery:import:{preview_id}:active_new")],
            [InlineKeyboardButton(text="✅ Импортировать все новые", callback_data=f"discovery:import:{preview_id}:all_new")],
            [InlineKeyboardButton(text="📤 Экспорт preview CSV", callback_data=f"discovery:export:{preview_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="discovery:cancel")],
        ]
    )


def discovery_after_import_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧠 Запустить research", callback_data="research_queue:from_last_import")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="company:list")],
        ]
    )
