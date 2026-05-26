from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.database import async_session_factory
from app.modules.analytics.keyboards import (
    analytics_cities_markup,
    analytics_cold_base_markup,
    analytics_export_markup,
    analytics_funnel_markup,
    analytics_funnel_status_markup,
    analytics_menu_markup,
    analytics_score_actions_markup,
    analytics_scores_filter_markup,
    analytics_sources_markup,
)
from app.modules.analytics.service import (
    build_city_analytics,
    build_cold_base,
    build_funnel_analytics,
    build_source_analytics,
    export_analytics_csv,
    list_lead_scores,
)
from app.modules.crm.keyboards import main_menu, stats_company_list_markup
from app.modules.crm.service import humanize_company_status, list_companies_by_status

router = Router(name="analytics")


@router.message(F.text == "📈 Аналитика")
async def analytics_root(message: Message) -> None:
    await message.answer(_analytics_menu_text(), reply_markup=analytics_menu_markup())


@router.callback_query(F.data == "analytics:menu")
async def analytics_menu_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть аналитику.", show_alert=True)
        return
    await _safe_edit_message(callback.message, _analytics_menu_text(), reply_markup=analytics_menu_markup())
    await callback.answer()


@router.callback_query(F.data == "analytics:back")
async def analytics_back_callback(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer("Главное меню CRM.", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "analytics:funnel")
async def analytics_funnel_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть воронку.", show_alert=True)
        return
    async with async_session_factory() as session:
        funnel = await build_funnel_analytics(session)
    await _safe_edit_message(callback.message, _render_funnel(funnel), reply_markup=analytics_funnel_markup())
    await callback.answer()


@router.callback_query(F.data == "analytics:funnel:statuses")
async def analytics_funnel_statuses_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть статусы.", show_alert=True)
        return
    await _safe_edit_message(callback.message, "Выберите статус для просмотра лидов.", reply_markup=analytics_funnel_status_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("analytics:funnel:status:"))
async def analytics_funnel_status_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть список лидов.", show_alert=True)
        return
    status = callback.data.rsplit(":", 1)[-1]
    async with async_session_factory() as session:
        companies = await list_companies_by_status(session, status, limit=20)
    text = _render_status_companies(status, companies)
    markup = stats_company_list_markup(companies) if companies else analytics_funnel_status_markup()
    await _safe_edit_message(callback.message, text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data == "analytics:sources")
@router.callback_query(F.data == "analytics:sources:best")
async def analytics_sources_best(callback: CallbackQuery) -> None:
    await _show_sources(callback, best_first=True)


@router.callback_query(F.data == "analytics:sources:weak")
async def analytics_sources_weak(callback: CallbackQuery) -> None:
    await _show_sources(callback, best_first=False)


@router.callback_query(F.data == "analytics:cities")
@router.callback_query(F.data == "analytics:cities:best")
async def analytics_cities_best(callback: CallbackQuery) -> None:
    await _show_cities(callback, best_first=True)


@router.callback_query(F.data == "analytics:cities:overdue")
async def analytics_cities_overdue(callback: CallbackQuery) -> None:
    await _show_cities(callback, best_first=False)


@router.callback_query(F.data.startswith("analytics:scores:"))
async def analytics_scores_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть скоринг.", show_alert=True)
        return

    filter_code = callback.data.rsplit(":", 1)[-1]
    async with async_session_factory() as session:
        items = await list_lead_scores(
            session,
            limit=20,
            grade="hot" if filter_code == "hot" else ("priority" if filter_code == "priority" else None),
            without_tasks=filter_code == "no_task",
            overdue_only=filter_code == "overdue",
        )
    text = _render_scores(items)
    reply_markup = analytics_score_actions_markup(items, filter_code) or analytics_scores_filter_markup(filter_code)
    await _safe_edit_message(callback.message, text, reply_markup=reply_markup)
    await callback.answer()


@router.callback_query(F.data == "analytics:cold")
async def analytics_cold_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть холодную базу.", show_alert=True)
        return

    async with async_session_factory() as session:
        items = await build_cold_base(session, limit=20)
    text = _render_cold_base(items)
    await _safe_edit_message(callback.message, text, reply_markup=analytics_cold_base_markup(items) or analytics_menu_markup())
    await callback.answer()


@router.callback_query(F.data == "analytics:export")
async def analytics_export_menu_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть экспорт аналитики.", show_alert=True)
        return
    await _safe_edit_message(callback.message, "Выберите CSV-экспорт аналитики.", reply_markup=analytics_export_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("analytics:export:"))
async def analytics_export_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось экспортировать аналитику.", show_alert=True)
        return

    export_type = callback.data.rsplit(":", 1)[-1]
    async with async_session_factory() as session:
        result = await export_analytics_csv(session, export_type)
    await callback.message.answer_document(
        FSInputFile(result.file_path),
        caption=f"Экспорт готов: {result.filename}",
    )
    await callback.answer("CSV экспорт отправлен.")


async def _show_sources(callback: CallbackQuery, *, best_first: bool) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть источники.", show_alert=True)
        return
    async with async_session_factory() as session:
        items = await build_source_analytics(session, limit=20, best_first=best_first)
    await _safe_edit_message(callback.message, _render_sources(items), reply_markup=analytics_sources_markup())
    await callback.answer()


async def _show_cities(callback: CallbackQuery, *, best_first: bool) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть города.", show_alert=True)
        return
    async with async_session_factory() as session:
        items = await build_city_analytics(session, limit=20, best_first=best_first)
    await _safe_edit_message(callback.message, _render_cities(items), reply_markup=analytics_cities_markup())
    await callback.answer()


def _analytics_menu_text() -> str:
    return "\n".join(
        [
            "📈 Аналитика CRM",
            "",
            "Выберите раздел:",
        ]
    )


def _render_funnel(funnel) -> str:
    conversions = [
        f"Новый → Интерес: {_fmt_pct(funnel.new_to_interested_conversion)}",
        f"Интерес → Консультация: {_fmt_pct(funnel.interested_to_consultation_conversion)}",
        f"Консультация → КП: {_fmt_pct(funnel.consultation_to_proposal_conversion)}",
        f"КП → Сделка: {_fmt_pct(funnel.proposal_to_won_conversion)}",
    ]
    return "\n".join(
        [
            "📊 Воронка продаж",
            "",
            f"Всего компаний: {funnel.total_companies}",
            "",
            f"Новые: {funnel.new_count}",
            f"Нужен ресёрч: {funnel.research_needed_count}",
            f"Подготовлены: {funnel.prepared_count}",
            f"Запланирован звонок: {funnel.call_planned_count}",
            f"Был звонок: {funnel.called_count}",
            f"Не дозвонились: {funnel.no_answer_count}",
            f"Интерес: {funnel.interested_count}",
            f"Консультация назначена: {funnel.consultation_planned_count}",
            f"КП отправлено: {funnel.proposal_sent_count}",
            f"Сделки выиграны: {funnel.deal_won_count}",
            f"Сделки проиграны: {funnel.deal_lost_count}",
            f"Не контактировать: {funnel.do_not_contact_count}",
            "",
            "Конверсии:",
            *conversions,
            "",
            funnel.note,
        ]
    )


def _render_status_companies(status: str, companies: list) -> str:
    lines = [f"Лиды в статусе: {humanize_company_status(status)}", ""]
    if not companies:
        lines.append("Список пуст.")
        return "\n".join(lines)
    for company in companies:
        lines.append(f"#{company.id} {company.name} — {company.city or 'город не указан'}")
    return "\n".join(lines)


def _render_sources(items: list) -> str:
    lines = ["🧲 Источники лидов", ""]
    if not items:
        lines.append("Пока нет данных.")
        return "\n".join(lines)
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"{index}. {item.source}",
                f"Всего: {item.total_companies}",
                f"Интерес: {item.interested_count}",
                f"Консультации: {item.consultation_planned_count}",
                f"КП: {item.proposal_sent_count}",
                f"Сделки: {item.deal_won_count}",
                f"Конверсия в интерес: {_fmt_pct(item.conversion_to_interested)}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _render_cities(items: list) -> str:
    lines = ["🏙 Города / регионы", ""]
    if not items:
        lines.append("Пока нет данных.")
        return "\n".join(lines)
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"{index}. {item.city}",
                f"Всего: {item.total_companies}",
                f"Интерес: {item.interested_count}",
                f"Консультации: {item.consultation_planned_count}",
                f"КП: {item.proposal_sent_count}",
                f"Сделки: {item.deal_won_count}",
                f"Просроченных задач: {item.overdue_tasks}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _render_scores(items: list) -> str:
    lines = ["🔥 Приоритетные лиды", ""]
    if not items:
        lines.append("Подходящих лидов не найдено.")
        return "\n".join(lines)
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"{index}. {item.company_name} — {item.score}/100 — {item.grade}",
                f"Причины: {', '.join(item.reasons[:3])}.",
                f"Следующий шаг: {item.next_best_action}.",
                *( [item.proposal_recommendation] if item.proposal_recommendation else [] ),
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _render_cold_base(items: list) -> str:
    lines = ["🧊 Холодная база", ""]
    if not items:
        lines.append("Холодная база пуста.")
        return "\n".join(lines)
    for index, item in enumerate(items, start=1):
        missing = ", ".join(item.missing_fields) or "контекст"
        lines.extend(
            [
                f"{index}. {item.company_name} — {item.score}/100",
                f"Не хватает: {missing}",
                f"Следующий шаг: {item.next_best_action}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "н/д"
    return f"{value:.1f}%"


async def _safe_edit_message(message: Message, text: str, *, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await message.edit_reply_markup(reply_markup=reply_markup)
