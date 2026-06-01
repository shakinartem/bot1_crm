from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database import async_session_factory
from app.modules.crm.service import get_company
from app.modules.sales_intelligence.keyboards import (
    sales_intelligence_menu_markup,
    sales_intelligence_result_markup,
)
from app.modules.sales_intelligence.service import (
    build_closing_criteria_readiness,
    generate_cold_call_plan,
    generate_soprano_questions,
    get_latest_sales_intelligence,
)

router = Router(name="sales_intelligence")


@router.callback_query(F.data.startswith("sales:open:"))
async def sales_open_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть sales intelligence.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        company = await get_company(session, company_id)
    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return
    await state.clear()
    text = (
        "📞 Sales Intelligence\n\n"
        f"Компания: {company.name}\n"
        f"Сайт: {company.website or 'не указан'}\n"
        f"Город: {company.city or 'не указан'}\n\n"
        "Выберите, что показать:"
    )
    await _safe_edit_message(callback.message, text, reply_markup=sales_intelligence_menu_markup(company_id))
    await callback.answer()


@router.callback_query(F.data.startswith("sales:score:"))
async def sales_show_score(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть score.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        payload = await get_latest_sales_intelligence(session, company_id)
    score = payload.material_score
    text = "\n".join(
        [
            "📊 Материалы",
            "",
            f"Оценка: {score.total_score}/100 ({score.grade})",
            f"Сайт: {score.website_score}",
            f"Соцсети: {score.socials_score}",
            f"Карты: {score.maps_score}",
            f"Доверие: {score.trust_score}",
            f"Конверсия: {score.conversion_score}",
            f"Контакты: {score.contact_score}",
            "",
            "Почему:",
            *[f"- {item}" for item in score.reasons[:4]],
            "",
            "Риски:",
            *[f"- {item}" for item in score.risks[:4]],
        ]
    )
    await _safe_edit_message(callback.message, text, reply_markup=sales_intelligence_result_markup(company_id))
    await callback.answer()


@router.callback_query(F.data.startswith("sales:closing:"))
async def sales_show_closing(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть критерии.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        closing = await build_closing_criteria_readiness(session, company_id)
    items = [
        ("Финансовая возможность", closing.financial_opportunity),
        ("Осознанная потребность", closing.conscious_need),
        ("Доверие", closing.trust),
        ("ЛПР", closing.decision_maker),
        ("Здесь и сейчас", closing.here_and_now),
    ]
    lines = ["🎯 Критерии закрытия", "", closing.summary, ""]
    for title, item in items:
        lines.append(f"{title}: {item.score}/100 ({item.status})")
        if item.evidence:
            lines.append(f"- Сигнал: {item.evidence[0]}")
        if item.questions:
            lines.append(f"- Вопрос: {item.questions[0]}")
        lines.append("")
    lines.append(f"Следующий лучший вопрос: {closing.next_best_question}")
    await _safe_edit_message(
        callback.message,
        "\n".join(lines).strip(),
        reply_markup=sales_intelligence_result_markup(company_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sales:soprano:"))
async def sales_show_soprano(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть SOPRANO.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        soprano = await generate_soprano_questions(session, company_id)
    lines = [
        "🧠 SOPRANO",
        "",
        soprano.intro,
        "",
        "Рекомендуемый порядок:",
        *[f"- {item}" for item in soprano.recommended_order],
        "",
        "Situation:",
        *[f"- {item}" for item in soprano.situation[:2]],
        "",
        "Experience:",
        *[f"- {item}" for item in soprano.experience[:2]],
        "",
        "Principles:",
        *[f"- {item}" for item in soprano.principles[:2]],
    ]
    await _safe_edit_message(
        callback.message,
        "\n".join(lines),
        reply_markup=sales_intelligence_result_markup(company_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sales:plan:"))
async def sales_show_plan(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось собрать план.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    await _safe_edit_message(callback.message, "Собираю план звонка, это может занять несколько секунд...")
    async with async_session_factory() as session:
        plan = await generate_cold_call_plan(session, company_id, use_ai=True)
    lines = [
        "📞 План звонка",
        "",
        f"Режим: {plan.generation_mode}",
        f"Уверенность: {plan.confidence}",
        f"Цель: {plan.call_goal}",
        "",
        f"Причина звонка: {plan.reason_for_call}",
        "",
        "Первый оффер:",
        plan.first_offer,
        "",
        "Короткий скрипт:",
        plan.copyable_short_script,
    ]
    await _safe_edit_message(
        callback.message,
        "\n".join(lines),
        reply_markup=sales_intelligence_result_markup(company_id),
    )
    await callback.answer("План готов.")


async def _safe_edit_message(
    message: Message,
    text: str,
    *,
    reply_markup=None,
) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await message.edit_reply_markup(reply_markup=reply_markup)

