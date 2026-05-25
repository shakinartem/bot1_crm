from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.modules.proposals.packages import PACKAGE_ORDER, SERVICE_PACKAGES


def proposals_menu_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Подобрать пакет", callback_data=f"proposal:menu:suggest:{company_id}")],
            [InlineKeyboardButton(text="🤖 Сгенерировать КП", callback_data=f"proposal:menu:generate:{company_id}")],
            [InlineKeyboardButton(text="🧾 Черновик договора", callback_data=f"proposal:menu:contract:{company_id}")],
            [InlineKeyboardButton(text="📎 Приложение с услугами", callback_data=f"proposal:menu:appendix:{company_id}")],
            [InlineKeyboardButton(text="📤 Последние файлы", callback_data=f"proposal:menu:files:{company_id}")],
            [InlineKeyboardButton(text="📜 История КП/договоров", callback_data=f"proposal:menu:history:{company_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"company:open:{company_id}")],
        ]
    )


def package_suggestions_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сгенерировать КП по этим пакетам", callback_data=f"proposal:action:auto:{company_id}")],
            [InlineKeyboardButton(text="Выбрать пакеты вручную", callback_data=f"proposal:manual:start:{company_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"proposal:open:{company_id}")],
        ]
    )


def manual_package_selection_markup(company_id: int, selected_codes: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    selected = set(selected_codes)
    short_labels = {
        "audit_roadmap": "Диагностика",
        "landing_start": "Лендинг",
        "maps_reputation": "Карты и репутация",
        "smm_funnel": "SMM-воронка",
        "crm_bot": "CRM/бот",
        "complex_growth": "Комплекс",
    }
    for code in PACKAGE_ORDER:
        prefix = "✅" if code in selected else "⬜"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix} {short_labels[code]}",
                    callback_data=f"proposal:manual:toggle:{company_id}:{code}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Продолжить", callback_data=f"proposal:manual:continue:{company_id}")])
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"proposal:open:{company_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def manual_package_actions_markup(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Сгенерировать КП", callback_data=f"proposal:manual:proposal:{company_id}")],
            [InlineKeyboardButton(text="📎 Сформировать приложение", callback_data=f"proposal:manual:appendix:{company_id}")],
            [InlineKeyboardButton(text="🧾 Черновик договора", callback_data=f"proposal:manual:contract:{company_id}")],
            [InlineKeyboardButton(text="⬅️ Назад к пакетам", callback_data=f"proposal:manual:start:{company_id}")],
        ]
    )


def proposal_history_markup(company_id: int, draft_ids: list[int]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"Открыть #{draft_id}", callback_data=f"proposal:history:item:{company_id}:{draft_id}")]
        for draft_id in draft_ids
    ]
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"proposal:open:{company_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def proposal_file_markup(company_id: int, draft_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Отправить файл", callback_data=f"proposal:file:send:{company_id}:{draft_id}")],
            [InlineKeyboardButton(text="⬅️ Назад к истории", callback_data=f"proposal:menu:history:{company_id}")],
        ]
    )


def package_catalog_payload() -> list[dict]:
    return [
        {
            "code": code,
            "title": SERVICE_PACKAGES[code].title,
            "price": SERVICE_PACKAGES[code].price,
            "items": list(SERVICE_PACKAGES[code].items),
            "suggested_when": list(SERVICE_PACKAGES[code].suggested_when),
            "result": SERVICE_PACKAGES[code].result,
            "client_needs": list(SERVICE_PACKAGES[code].client_needs),
        }
        for code in PACKAGE_ORDER
    ]
