from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def import_preview_markup(import_mode: str) -> InlineKeyboardMarkup:
    skip_label = "✅ Пропускать дубли" if import_mode == "skip" else "Пропускать дубли"
    update_label = "✅ Обновлять карточки" if import_mode == "update" else "Обновлять карточки"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=skip_label, callback_data="import:mode:skip"),
                InlineKeyboardButton(text=update_label, callback_data="import:mode:update"),
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
            [InlineKeyboardButton(text="Открыть добавленные компании", callback_data="import:report:added")],
            [InlineKeyboardButton(text="Задачи по новым лидам", callback_data="import:report:tasks")],
            [InlineKeyboardButton(text="Назад в меню", callback_data="import:report:menu")],
        ]
    )
