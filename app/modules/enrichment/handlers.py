from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.database import async_session_factory
from app.modules.crm.keyboards import CANCEL_TEXT, flow_menu, main_menu
from app.modules.crm.service import get_company
from app.modules.enrichment.fetcher import normalize_website_url
from app.modules.enrichment.keyboards import (
    research_history_markup,
    research_menu_markup,
    research_result_markup,
    research_snapshot_markup,
)
from app.modules.enrichment.service import (
    enrich_company_website,
    get_enrichment_history,
    get_enrichment_snapshot,
    get_latest_enrichment,
)

router = Router(name="enrichment")


class ResearchStates(StatesGroup):
    website_url = State()


@router.callback_query(F.data.startswith("research:open:"))
async def research_open_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть Research.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        company = await get_company(session, company_id)

    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return

    await state.clear()
    text = (
        "🔎 Research / обогащение\n\n"
        f"Клиника: {company.name}\n"
        f"Сайт: {company.website or 'не указан'}\n\n"
        "Выберите действие:"
    )
    await _safe_edit_message(callback.message, text, reply_markup=research_menu_markup(company_id))
    await callback.answer()


@router.callback_query(F.data.startswith("research:check:"))
async def research_check(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось запустить Research.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    await _safe_edit_message(callback.message, "Проверяю сайт, это может занять несколько секунд...")
    async with async_session_factory() as session:
        company = await get_company(session, company_id)
        if not company:
            await callback.answer("Компания не найдена.", show_alert=True)
            return
        if not (company.website or "").strip():
            text = (
                "🔎 Research\n\n"
                "У компании пока не указан сайт.\n"
                "Можно ввести сайт вручную и сразу запустить быструю проверку."
            )
            await _safe_edit_message(callback.message, text, reply_markup=research_menu_markup(company_id))
            await callback.answer()
            return
        result = await enrich_company_website(session, company_id, use_ai=False)

    await _safe_edit_message(callback.message, _render_result_text(result), reply_markup=research_result_markup(company_id))
    await callback.answer("Research завершён.")


@router.callback_query(F.data.startswith("research:manual:start:"))
async def research_manual_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть ввод сайта.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(company_id=company_id)
    await state.set_state(ResearchStates.website_url)
    await callback.answer()
    await callback.message.answer("Введите URL сайта клиники.", reply_markup=flow_menu())


@router.message(ResearchStates.website_url)
async def research_manual_website(message: Message, state: FSMContext) -> None:
    raw_text = (message.text or "").strip()
    if raw_text == CANCEL_TEXT:
        await state.clear()
        await message.answer("Ввод сайта отменён.", reply_markup=main_menu())
        return

    try:
        normalized = normalize_website_url(raw_text)
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=flow_menu())
        return

    data = await state.get_data()
    company_id = int(data["company_id"])
    await message.answer("Проверяю сайт, это может занять несколько секунд...")
    async with async_session_factory() as session:
        result = await enrich_company_website(session, company_id, website_url=normalized, use_ai=False)

    await state.clear()
    await message.answer(_render_result_text(result), reply_markup=main_menu())
    await message.answer("Открыть дополнительные действия можно кнопками ниже.", reply_markup=research_result_markup(company_id))


@router.callback_query(F.data.startswith("research:latest:"))
async def research_latest(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть snapshot.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        snapshot = await get_latest_enrichment(session, company_id)

    if not snapshot:
        await _safe_edit_message(callback.message, "🔎 Research пока не проводился.", reply_markup=research_menu_markup(company_id))
        await callback.answer()
        return

    await _safe_edit_message(callback.message, _render_snapshot_text(snapshot), reply_markup=research_snapshot_markup(company_id))
    await callback.answer()


@router.callback_query(F.data.startswith("research:history:"))
async def research_history(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть историю.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        history = await get_enrichment_history(session, company_id, limit=10)

    if not history:
        await _safe_edit_message(callback.message, "📜 История Research пока пуста.", reply_markup=research_menu_markup(company_id))
        await callback.answer()
        return

    lines = ["📜 История research", ""]
    for index, item in enumerate(history, start=1):
        site = item.website_url or "site missing"
        status_suffix = f" — {item.error_message}" if item.error_message and item.status == "failed" else ""
        lines.append(f"{index}. {item.created_at:%d.%m.%Y} — {item.status} — {site}{status_suffix}")

    await _safe_edit_message(
        callback.message,
        "\n".join(lines),
        reply_markup=research_history_markup(company_id, [item.id for item in history]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("research:snapshot:"))
async def research_snapshot(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть snapshot.", show_alert=True)
        return

    _, _, company_id_raw, snapshot_id_raw = callback.data.split(":", 3)
    company_id = int(company_id_raw)
    snapshot_id = int(snapshot_id_raw)
    async with async_session_factory() as session:
        snapshot = await get_enrichment_snapshot(session, company_id, snapshot_id)

    if not snapshot:
        await callback.answer("Snapshot не найден.", show_alert=True)
        return

    await _safe_edit_message(callback.message, _render_snapshot_text(snapshot), reply_markup=research_snapshot_markup(company_id))
    await callback.answer()


@router.callback_query(F.data.startswith("research:ai:"))
async def research_ai_summary(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть AI-резюме.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        latest = await get_latest_enrichment(session, company_id)
        if latest and latest.ai_summary:
            summary = latest.ai_summary
        else:
            result = await enrich_company_website(
                session,
                company_id,
                website_url=latest.website_url if latest else None,
                use_ai=True,
            )
            summary = result.ai_summary or "AI-резюме пока недоступно."

    await _safe_edit_message(callback.message, summary, reply_markup=research_snapshot_markup(company_id))
    await callback.answer("AI-резюме готово.")


def _render_result_text(result) -> str:
    socials = [key.upper() for key, value in result.detected_socials.items() if value]
    maps = [key for key, value in result.detected_maps.items() if value]
    contacts = []
    if result.detected_contacts.phones:
        contacts.append("телефон")
    if result.detected_contacts.emails:
        contacts.append("email")
    lines = [
        "🔎 Research завершён",
        "",
        f"Сайт: {result.website_url or 'не указан'}",
        f"Статус: {result.status}",
        f"HTTP: {result.http_status or 'n/a'}",
        f"Заголовок: {result.page_title or 'не найден'}",
        "",
        "Найдено:",
        f"- соцсети: {', '.join(socials) or 'нет'}",
        f"- контакты: {', '.join(contacts) or 'нет'}",
        f"- карты/площадки: {', '.join(maps) or 'нет'}",
        f"- онлайн-запись: {'да' if result.signals.has_online_booking else 'нет'}",
        f"- формы: {'да' if result.signals.has_callback_form else 'нет'}",
        f"- отзывы: {'да' if result.signals.has_reviews_section else 'нет'}",
        f"- цены: {'да' if result.signals.has_prices else 'нет'}",
        f"- врачи: {'да' if result.signals.has_doctors_page else 'нет'}",
        "",
        "Гипотезы:",
    ]
    if result.hypotheses:
        lines.extend(f"{index}. {item}" for index, item in enumerate(result.hypotheses[:3], start=1))
    else:
        lines.append("1. Явных гипотез пока нет.")
    return "\n".join(lines)


def _render_snapshot_text(snapshot) -> str:
    signal_bits = [
        f"запись: {'да' if snapshot.signals.has_online_booking else 'нет'}",
        f"отзывы: {'да' if snapshot.signals.has_reviews_section else 'нет'}",
        f"мессенджеры: {'да' if snapshot.signals.has_messenger_links else 'нет'}",
    ]
    summary = snapshot.ai_summary or "AI-резюме пока не сформировано."
    return "\n".join(
        [
            "📌 Последний research",
            "",
            f"Дата: {snapshot.created_at:%d.%m.%Y %H:%M}",
            f"Сайт: {snapshot.website_url or 'не указан'}",
            f"Статус: {snapshot.status}",
            f"Заголовок: {snapshot.page_title or 'не найден'}",
            f"Сигналы: {', '.join(signal_bits)}",
            f"Гипотезы: {len(snapshot.hypotheses)}",
            "",
            "Краткое AI-резюме:",
            summary[:800] + ("..." if len(summary) > 800 else ""),
        ]
    )


async def _safe_edit_message(message: Message, text: str, *, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await message.edit_reply_markup(reply_markup=reply_markup)
