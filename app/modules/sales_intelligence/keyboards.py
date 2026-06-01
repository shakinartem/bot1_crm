from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def sales_intelligence_menu_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📞 Сгенерировать план", callback_data=f"sales:plan:{company_id}")],
            [
                InlineKeyboardButton(text="📊 Оценить материалы", callback_data=f"sales:score:{company_id}"),
                InlineKeyboardButton(text="🎯 Критерии", callback_data=f"sales:closing:{company_id}"),
            ],
            [InlineKeyboardButton(text="🧠 SOPRANO", callback_data=f"sales:soprano:{company_id}")],
            [
                InlineKeyboardButton(text="📄 КП / Договор", callback_data=f"proposal:open:{company_id}"),
                InlineKeyboardButton(text="🚀 В БОТ 2", callback_data=f"consult:handoff:{company_id}"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад к карточке", callback_data=f"company:open:{company_id}")],
        ]
    )


def sales_intelligence_result_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📞 План", callback_data=f"sales:plan:{company_id}"),
                InlineKeyboardButton(text="📊 Материалы", callback_data=f"sales:score:{company_id}"),
            ],
            [
                InlineKeyboardButton(text="🎯 Критерии", callback_data=f"sales:closing:{company_id}"),
                InlineKeyboardButton(text="🧠 SOPRANO", callback_data=f"sales:soprano:{company_id}"),
            ],
            [InlineKeyboardButton(text="⬅️ В меню sales intelligence", callback_data=f"sales:open:{company_id}")],
        ]
    )

