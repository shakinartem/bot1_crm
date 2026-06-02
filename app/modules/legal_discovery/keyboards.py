from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def discovery_provider_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Checko HTML", callback_data="discovery:provider:checko_html")],
            [InlineKeyboardButton(text="Mock / Dev", callback_data="discovery:provider:mock")],
        ]
    )


def discovery_niche_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="86.23 Стоматология", callback_data="discovery:niche:86.23")],
            [InlineKeyboardButton(text="56.10 Рестораны", callback_data="discovery:niche:56.10")],
            [InlineKeyboardButton(text="69.10 Юридические услуги", callback_data="discovery:niche:69.10")],
            [InlineKeyboardButton(text="Ручной ОКВЭД", callback_data="discovery:niche:manual")],
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
            [InlineKeyboardButton(text="Импортировать active new", callback_data=f"discovery:import:{preview_id}:active_new")],
            [InlineKeyboardButton(text="Импортировать все new", callback_data=f"discovery:import:{preview_id}:all_new")],
            [InlineKeyboardButton(text="Импортировать с сайтами", callback_data=f"discovery:import:{preview_id}:new_with_websites")],
            [InlineKeyboardButton(text="Импортировать phone/site", callback_data=f"discovery:import:{preview_id}:new_with_phone_or_website")],
            [InlineKeyboardButton(text="Экспортировать preview CSV", callback_data=f"discovery:export:{preview_id}")],
            [InlineKeyboardButton(text="Отмена", callback_data="discovery:cancel")],
        ]
    )


def discovery_after_import_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Запустить research", callback_data="research_queue:from_last_import")],
            [InlineKeyboardButton(text="Назад", callback_data="company:list")],
        ]
    )
