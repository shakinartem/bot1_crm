from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def import_preview_markup(import_mode: str) -> InlineKeyboardMarkup:
    """Preview markup with 3 import modes: create_only, update_existing, upsert."""
    create_label = "✅ Только новые" if import_mode == "create_only" else "Только новые"
    update_label = "✅ Обновить существующие" if import_mode == "update_existing" else "Обновить существующие"
    upsert_label = "✅ Создать/обновить" if import_mode == "upsert" else "Создать/обновить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=create_label, callback_data="import:mode:create_only"),
                InlineKeyboardButton(text=update_label, callback_data="import:mode:update_existing"),
            ],
            [
                InlineKeyboardButton(text=upsert_label, callback_data="import:mode:upsert"),
            ],
            [
                InlineKeyboardButton(text="✅ Импортировать", callback_data="import:commit"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="import:cancel"),
            ],
        ]
    )


def import_report_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏷 Группы лидов", callback_data="import:report:lead_groups")],
            [InlineKeyboardButton(text="Открыть добавленные компании", callback_data="import:report:added")],
            [InlineKeyboardButton(text="Задачи по новым лидам", callback_data="import:report:tasks")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="import:report:menu")],
        ]
    )
