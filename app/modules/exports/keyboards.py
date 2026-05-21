from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def export_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Все компании", callback_data="export:run:all")],
            [InlineKeyboardButton(text="Новые лиды", callback_data="export:run:status:new")],
            [InlineKeyboardButton(text="Интересные", callback_data="export:run:status:interested")],
            [InlineKeyboardButton(text="Консультации назначены", callback_data="export:run:status:consultation_planned")],
            [InlineKeyboardButton(text="КП отправлено", callback_data="export:run:status:proposal_sent")],
            [InlineKeyboardButton(text="Сделки", callback_data="export:run:status:deal_won")],
            [InlineKeyboardButton(text="По городу", callback_data="export:prompt:city")],
            [InlineKeyboardButton(text="По источнику", callback_data="export:prompt:source")],
            [InlineKeyboardButton(text="По приоритету", callback_data="export:prompt:priority")],
            [InlineKeyboardButton(text="Назад в меню", callback_data="export:menu")],
        ]
    )


def export_priority_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Низкий", callback_data="export:run:priority:low")],
            [InlineKeyboardButton(text="Средний", callback_data="export:run:priority:medium")],
            [InlineKeyboardButton(text="Высокий", callback_data="export:run:priority:high")],
            [InlineKeyboardButton(text="Назад", callback_data="export:root")],
        ]
    )


def consultation_package_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Сгенерировать мини-аудит", callback_data=f"consult:mini_audit:{company_id}")],
            [InlineKeyboardButton(text="🚀 Подготовить передачу в БОТ 2", callback_data=f"consult:handoff:{company_id}")],
            [InlineKeyboardButton(text="📤 Экспортировать эту компанию", callback_data=f"consult:export_company:{company_id}")],
            [InlineKeyboardButton(text="⬅️ Назад к карточке", callback_data=f"company:open:{company_id}")],
        ]
    )


def mini_audit_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Скопировать текст", callback_data=f"audit:copy:{company_id}")],
            [InlineKeyboardButton(text="Сохранить в историю", callback_data=f"audit:save:{company_id}")],
            [InlineKeyboardButton(text="Экспортировать в .txt", callback_data=f"audit:export:{company_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"consult:package:{company_id}")],
        ]
    )


def handoff_preview_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Экспортировать payload JSON", callback_data=f"handoff:export:{company_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"company:open:{company_id}")],
        ]
    )
