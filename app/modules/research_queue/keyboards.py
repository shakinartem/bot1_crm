from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def research_queue_scope_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Только новые компании", callback_data="research_queue:scope:last_import")],
            [InlineKeyboardButton(text="Только без сайта", callback_data="research_queue:scope:without_website")],
            [InlineKeyboardButton(text="Top-50", callback_data="research_queue:scope:top50")],
            [InlineKeyboardButton(text="Все из последнего импорта", callback_data="research_queue:scope:last_import_all")],
        ]
    )


def research_queue_created_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Запустить batch", callback_data="research_queue:run_batch")],
            [InlineKeyboardButton(text="📊 Статус очереди", callback_data="research_queue:status")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="research_queue:cancel")],
        ]
    )
