from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database import async_session_factory
from app.modules.crm.service import get_company
from app.modules.intelligence.keyboards import (
    intelligence_history_markup,
    intelligence_legal_candidates_markup,
    intelligence_menu_markup,
    intelligence_result_markup,
)
from app.modules.intelligence.schemas import LegalCompany
from app.modules.intelligence.service import (
    apply_legal_candidate_and_enrich,
    enrich_company_intelligence,
    find_legal_candidates_for_company,
    get_intelligence_history,
    get_intelligence_snapshot,
    get_latest_intelligence,
    resolve_company_website,
)

router = Router(name="intelligence")


@router.callback_query(F.data.startswith("intelligence:open:"))
async def intelligence_open_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть Intelligence.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        company = await get_company(session, company_id)
    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return
    await state.clear()
    text = (
        "🧾 INN / Intelligence\n\n"
        f"Клиника: {company.name}\n"
        f"ИНН: {company.inn or 'не указан'}\n"
        f"Сайт: {company.website or 'не найден'}\n\n"
        "Действия:"
    )
    await _safe_edit_message(callback.message, text, reply_markup=intelligence_menu_markup(company_id))
    await callback.answer()


@router.callback_query(F.data.startswith("intelligence:find_legal:"))
async def intelligence_find_legal(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось выполнить поиск.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        candidates = await find_legal_candidates_for_company(session, company_id)
    if not candidates:
        await _safe_edit_message(callback.message, "Юркандидаты не найдены.", reply_markup=intelligence_menu_markup(company_id))
        await callback.answer()
        return
    if len(candidates) == 1:
        await _safe_edit_message(
            callback.message,
            _render_legal_single(candidates[0]),
            reply_markup=intelligence_menu_markup(company_id),
        )
        await callback.answer()
        return
    await state.update_data(intelligence_legal_candidates=[item.model_dump() for item in candidates])
    await _safe_edit_message(
        callback.message,
        _render_legal_candidates(candidates),
        reply_markup=intelligence_legal_candidates_markup(company_id, len(candidates)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("intelligence:pick_legal:"))
async def intelligence_pick_legal(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось выбрать кандидата.", show_alert=True)
        return
    _, _, company_id_raw, index_raw = callback.data.split(":", 3)
    company_id = int(company_id_raw)
    index = int(index_raw) - 1
    data = await state.get_data()
    stored = data.get("intelligence_legal_candidates") or []
    if not (0 <= index < len(stored)):
        await callback.answer("Кандидат уже недоступен.", show_alert=True)
        return
    candidate = LegalCompany.model_validate(stored[index])
    await _safe_edit_message(callback.message, "Продолжаю полное обогащение по выбранному юрлицу...")
    async with async_session_factory() as session:
        result = await apply_legal_candidate_and_enrich(session, company_id, candidate, use_ai=True)
    await state.clear()
    await _safe_edit_message(callback.message, _render_result(result), reply_markup=intelligence_result_markup(company_id))
    await callback.answer("Обогащение завершено.")


@router.callback_query(F.data.startswith("intelligence:check_inn:"))
async def intelligence_check_inn(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось проверить ИНН.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        company = await get_company(session, company_id)
        if not company or not company.inn:
            await _safe_edit_message(
                callback.message,
                "У компании пока нет ИНН. Сначала найдите ИНН по названию.",
                reply_markup=intelligence_menu_markup(company_id),
            )
            await callback.answer()
            return
        result = await enrich_company_intelligence(session, company_id, inn=company.inn, use_ai=False)
    await _safe_edit_message(callback.message, _render_result(result), reply_markup=intelligence_result_markup(company_id))
    await callback.answer("Проверка завершена.")


@router.callback_query(F.data.startswith("intelligence:resolve_website:"))
@router.callback_query(F.data.startswith("intelligence:resolve_legal:"))
async def intelligence_resolve_website_handler(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось выполнить поиск сайта.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        resolution = await resolve_company_website(session, company_id)
    await _safe_edit_message(callback.message, _render_resolution(resolution), reply_markup=intelligence_menu_markup(company_id))
    await callback.answer()


@router.callback_query(F.data.startswith("intelligence:enrich:"))
async def intelligence_enrich(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось запустить обогащение.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    await _safe_edit_message(callback.message, "Запускаю INN-first intelligence, это может занять несколько секунд...")
    async with async_session_factory() as session:
        result = await enrich_company_intelligence(session, company_id, use_ai=True)
    if result.status == "needs_review" and result.legal_candidates:
        await _safe_edit_message(
            callback.message,
            _render_legal_candidates(result.legal_candidates),
            reply_markup=intelligence_legal_candidates_markup(company_id, len(result.legal_candidates)),
        )
    else:
        await _safe_edit_message(callback.message, _render_result(result), reply_markup=intelligence_result_markup(company_id))
    await callback.answer("Готово.")


@router.callback_query(F.data.startswith("intelligence:latest:"))
async def intelligence_latest(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть результат.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        snapshot = await get_latest_intelligence(session, company_id)
    if not snapshot:
        await _safe_edit_message(callback.message, "Intelligence пока не проводился.", reply_markup=intelligence_menu_markup(company_id))
        await callback.answer()
        return
    await _safe_edit_message(callback.message, _render_snapshot(snapshot), reply_markup=intelligence_menu_markup(company_id))
    await callback.answer()


@router.callback_query(F.data.startswith("intelligence:history:"))
async def intelligence_history(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть историю.", show_alert=True)
        return
    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        history = await get_intelligence_history(session, company_id, limit=10)
    if not history:
        await _safe_edit_message(callback.message, "История intelligence пока пуста.", reply_markup=intelligence_menu_markup(company_id))
        await callback.answer()
        return
    lines = ["📜 История intelligence", ""]
    for index, item in enumerate(history, start=1):
        lines.append(f"{index}. {item.created_at:%d.%m.%Y} — {item.status} — {item.inn or 'без ИНН'}")
    await _safe_edit_message(
        callback.message,
        "\n".join(lines),
        reply_markup=intelligence_history_markup(company_id, [item.id for item in history]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("intelligence:snapshot:"))
async def intelligence_snapshot(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть snapshot.", show_alert=True)
        return
    _, _, company_id_raw, snapshot_id_raw = callback.data.split(":", 3)
    company_id = int(company_id_raw)
    snapshot_id = int(snapshot_id_raw)
    async with async_session_factory() as session:
        snapshot = await get_intelligence_snapshot(session, company_id, snapshot_id)
    if not snapshot:
        await callback.answer("Snapshot не найден.", show_alert=True)
        return
    await _safe_edit_message(callback.message, _render_snapshot(snapshot), reply_markup=intelligence_menu_markup(company_id))
    await callback.answer()


def _render_legal_single(candidate: LegalCompany) -> str:
    return "\n".join(
        [
            "Найдено юрлицо:",
            f"- {candidate.legal_name}",
            f"- ИНН: {candidate.inn}",
            f"- Адрес: {candidate.address or 'не указан'}",
            f"- Статус: {candidate.status or 'не указан'}",
            f"- Уверенность: {candidate.confidence:.2f}",
        ]
    )


def _render_legal_candidates(candidates: list[LegalCompany]) -> str:
    lines = ["Найдено несколько юрлиц:", ""]
    for index, item in enumerate(candidates, start=1):
        lines.extend(
            [
                f"{index}. {item.legal_name}",
                f"ИНН: {item.inn}",
                f"Адрес: {item.address or 'не указан'}",
                f"Статус: {item.status or 'не указан'}",
                f"Уверенность: {item.confidence:.2f}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def _render_resolution(result) -> str:
    lines = [
        "🌐 Поиск сайта",
        "",
        f"Выбранный сайт: {result.selected_url or 'не найден'}",
        f"Confidence: {result.confidence:.0f}",
    ]
    if result.reasons:
        lines.append("Почему выбран:")
        lines.extend(f"{index}. {item}" for index, item in enumerate(result.reasons[:5], start=1))
    if result.warnings:
        lines.append("Предупреждения:")
        lines.extend(f"- {item}" for item in result.warnings[:3])
    return "\n".join(lines)


def _render_result(result) -> str:
    legal = result.selected_legal
    site = result.parsed_site
    resolution = result.website_resolution
    lines = [
        "🧠 Обогащение завершено",
        "",
        "Юр. данные:",
        f"- ИНН: {legal.inn if legal else 'не найден'}",
        f"- ОГРН: {legal.ogrn if legal else 'не найден'}",
        f"- Юр. название: {legal.legal_name if legal else 'не найдено'}",
        f"- Адрес: {legal.address if legal else 'не найден'}",
        f"- Статус: {legal.status if legal else 'не найден'}",
        "",
        "Сайт:",
        f"- найден: {resolution.selected_url if resolution else 'не найден'}",
        f"- confidence: {resolution.confidence:.0f}" if resolution else "- confidence: 0",
    ]
    if resolution and resolution.reasons:
        lines.append("- почему выбран:")
        lines.extend(f"  {index}. {item}" for index, item in enumerate(resolution.reasons[:3], start=1))
    if site:
        lines.extend(
            [
                "",
                "Контакты:",
                f"- телефоны: {', '.join(site.contacts.phones) or 'не найдены'}",
                f"- email: {', '.join(site.contacts.emails) or 'не найдены'}",
                f"- мессенджеры: {', '.join((site.socials.telegram_links + site.socials.whatsapp_links)[:3]) or 'не найдены'}",
                "",
                "Соцсети:",
                f"- VK: {', '.join(site.socials.vk_links) or 'нет'}",
                f"- Telegram: {', '.join(site.socials.telegram_links) or 'нет'}",
                f"- Instagram: {', '.join(site.socials.instagram_links) or 'нет'}",
                "",
                "Сигналы:",
                f"- онлайн-запись: {'да' if site.signals.has_online_booking else 'нет'}",
                f"- форма заявки: {'да' if site.signals.has_callback_form else 'нет'}",
                f"- цены: {'да' if site.signals.has_prices else 'нет'}",
                f"- врачи: {'да' if site.signals.has_doctors_page else 'нет'}",
                f"- отзывы: {'да' if site.signals.has_reviews_section else 'нет'}",
                "",
                "Гипотезы:",
            ]
        )
        if result.hypotheses:
            lines.extend(f"{index}. {item}" for index, item in enumerate(result.hypotheses[:3], start=1))
        else:
            lines.append("1. Явных гипотез пока нет.")
    if result.error_message:
        lines.extend(["", f"Нужна ручная проверка: {result.error_message}"])
    return "\n".join(lines)


def _render_snapshot(snapshot) -> str:
    return "\n".join(
        [
            "📌 Последний intelligence",
            "",
            f"Дата: {snapshot.created_at:%d.%m.%Y %H:%M}",
            f"Статус: {snapshot.status}",
            f"ИНН: {snapshot.inn or 'не указан'}",
            f"Юр. лицо: {snapshot.legal_name or 'не найдено'}",
            f"Сайт: {snapshot.website_url or 'не найден'}",
            f"Confidence: {(snapshot.website_confidence or 0):.0f}",
            f"Сигналы: запись {'да' if snapshot.parsed_signals.has_online_booking else 'нет'}, "
            f"отзывы {'да' if snapshot.parsed_signals.has_reviews_section else 'нет'}, "
            f"врачи {'да' if snapshot.parsed_signals.has_doctors_page else 'нет'}",
            f"Гипотезы: {len(snapshot.hypotheses)}",
            "",
            (snapshot.ai_summary or "AI-резюме пока не сформировано.")[:900],
        ]
    )


async def _safe_edit_message(message: Message, text: str, *, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await message.edit_reply_markup(reply_markup=reply_markup)
