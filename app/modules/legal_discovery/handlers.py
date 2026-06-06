from __future__ import annotations

import csv
from io import StringIO

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.database import async_session_factory
from app.modules.crm.keyboards import CANCEL_TEXT, flow_menu, main_menu
from app.modules.legal_discovery.keyboards import (
    discovery_after_import_markup,
    discovery_browser_error_markup,
    discovery_limit_markup,
    discovery_niche_markup,
    discovery_preview_markup,
    discovery_provider_markup,
    discovery_zero_result_markup,
)
from app.modules.legal_discovery.service import (
    get_legal_discovery_preview,
    import_legal_discovery_preview,
    preview_callback_token,
    run_legal_discovery_preview,
)
from app.modules.research.browser_backend import BrowserBackendError

router = Router(name="legal_discovery")

DISCOVERY_BROWSER_ERROR_INSTALL_TEXT = (
    'Не удалось открыть Checko через браузерный backend. Проверьте BROWSER_BACKEND=camoufox '
    'и установку Camoufox: python -m pip install -U "camoufox[geoip]" && python -m camoufox fetch'
)
DISCOVERY_BROWSER_ERROR_TIMEOUT_TEXT = (
    "Checko отвечает слишком долго через браузерный backend. "
    "Попробуйте CAMOUFOX_HEADLESS=true, уменьшите CHECKO_HTML_MAX_PAGES до 1 и CHECKO_HTML_CONCURRENCY до 3."
)
DISCOVERY_BROWSER_ERROR_RUNTIME_TEXT = (
    "Не удалось открыть Checko через браузерный backend. "
    "Camoufox запустился, но не смог загрузить страницу. Попробуйте CAMOUFOX_HEADLESS=true и повторите попытку."
)
DISCOVERY_BROWSER_ERROR_PARSE_TEXT = (
    "Не удалось корректно разобрать выдачу Checko. Попробуйте меньший лимит, другой регион или Mock / Dev."
)


class DiscoveryStates(StatesGroup):
    niche_manual = State()
    city = State()


@router.message(F.text == "🔍 Поиск компаний")
@router.message(F.text == "/legal_discovery")
async def discovery_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🔍 Поиск компаний\n\n"
        "Дальше идём по legal discovery flow:\n"
        "источник -> ОКВЭД -> регион -> лимит -> preview -> import."
    )
    await message.answer("Выберите источник:", reply_markup=discovery_provider_markup())


@router.callback_query(F.data == "discovery:back:provider")
async def discovery_back_to_provider(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await state.update_data(discovery_provider=None)
    if callback.message:
        await _safe_edit_message(callback.message, "Выберите источник:", reply_markup=discovery_provider_markup())
    await _safe_callback_answer(callback)


@router.callback_query(F.data.startswith("discovery:provider:"))
async def discovery_pick_provider(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    provider = callback.data.rsplit(":", 1)[-1]
    await state.update_data(discovery_provider=provider)
    await _safe_edit_message(callback.message, "Выберите ОКВЭД или нишу:", reply_markup=discovery_niche_markup())
    await _safe_callback_answer(callback)


@router.callback_query(F.data.startswith("discovery:niche:"))
async def discovery_pick_niche(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    niche = callback.data.split(":", 2)[-1]
    if niche == "manual":
        await state.set_state(DiscoveryStates.niche_manual)
        await callback.message.answer("Введите ОКВЭД или нишу вручную.", reply_markup=flow_menu())
        await _safe_callback_answer(callback)
        return
    await state.update_data(discovery_query=niche)
    await state.set_state(DiscoveryStates.city)
    await callback.message.answer("Введите город или регион одним сообщением.", reply_markup=flow_menu())
    await _safe_callback_answer(callback)


@router.message(DiscoveryStates.niche_manual)
async def discovery_niche_manual(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip() == CANCEL_TEXT:
        await state.clear()
        await message.answer("Поиск компаний отменён.", reply_markup=main_menu())
        return
    await state.update_data(discovery_query=(message.text or "").strip())
    await state.set_state(DiscoveryStates.city)
    await message.answer("Введите город или регион одним сообщением.", reply_markup=flow_menu())


@router.message(DiscoveryStates.city)
async def discovery_city_input(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip() == CANCEL_TEXT:
        await state.clear()
        await message.answer("Поиск компаний отменён.", reply_markup=main_menu())
        return
    raw = (message.text or "").strip()
    await state.update_data(discovery_city=raw, discovery_region=None)
    await state.set_state(None)
    await message.answer("Выберите лимит выдачи.")
    await message.answer("Лимит:", reply_markup=discovery_limit_markup())


@router.callback_query(F.data.startswith("discovery:limit:"))
async def discovery_run_preview(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    limit = int(callback.data.rsplit(":", 1)[-1])
    await state.update_data(last_discovery_limit=limit)
    await _safe_edit_message(callback.message, "Ищу компании и собираю preview...")
    await _run_preview(callback, state, limit=limit)


@router.callback_query(F.data == "discovery:retry:small")
async def discovery_retry_small(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await state.update_data(last_discovery_limit=5)
    await _safe_edit_message(callback.message, "Повторяю поиск с меньшим лимитом...")
    await _run_preview(callback, state, limit=5)


@router.callback_query(F.data == "discovery:retry:noreg")
async def discovery_retry_without_region(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    data = await state.get_data()
    limit = int(data.get("last_discovery_limit") or 5)
    await _safe_edit_message(callback.message, "Повторяю поиск без регионального фильтра...")
    await _run_preview(callback, state, limit=limit, city=None, region=None)


@router.callback_query(F.data.startswith("discovery:import:"))
async def discovery_import(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    _, _, preview_id, mode = callback.data.split(":", 3)
    async with async_session_factory() as session:
        result = await import_legal_discovery_preview(session, preview_id, mode)
    await state.update_data(last_legal_import_company_ids=result.added_company_ids)
    text = (
        "Импорт завершён\n\n"
        f"Добавлено: {result.added_count}\n"
        f"Дубликаты: {result.skipped_duplicates}\n"
        f"Неактивные: {result.skipped_inactive}\n"
        f"Слабые данные: {result.skipped_weak}\n"
        f"Ошибки: {result.errors_count}"
    )
    await _safe_edit_message(callback.message, text, reply_markup=discovery_after_import_markup())
    await _safe_callback_answer(callback, "Импорт выполнен.")


@router.callback_query(F.data.startswith("discovery:export:"))
async def discovery_export(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    preview_id = callback.data.rsplit(":", 1)[-1]
    preview = get_legal_discovery_preview(preview_id)
    if not preview:
        await _safe_callback_answer(callback, "Preview уже недоступен.", show_alert=True)
        return
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["status", "legal_name", "inn", "ogrn", "city", "address", "warnings"])
    for item in preview.items:
        writer.writerow(
            [
                item.status,
                item.company.legal_name,
                item.company.inn,
                item.company.ogrn,
                item.company.city or "",
                item.company.address or "",
                "; ".join(item.warnings),
            ]
        )
    data = buffer.getvalue().encode("utf-8")
    file = BufferedInputFile(data, filename=f"legal_discovery_preview_{preview.preview_id[:8]}.csv")
    await callback.message.answer_document(file, caption="Preview CSV")
    await _safe_callback_answer(callback, "CSV экспортирован.")


@router.callback_query(F.data == "discovery:cancel")
async def discovery_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _safe_callback_answer(callback, "Отменено.")
    if callback.message:
        await callback.message.answer("Поиск компаний отменён.", reply_markup=main_menu())


async def _run_preview(
    callback: CallbackQuery,
    state: FSMContext,
    *,
    limit: int,
    city: str | None | object = ...,
    region: str | None | object = ...,
) -> None:
    if not callback.message:
        return
    data = await state.get_data()
    query = data.get("discovery_query") or "стоматология"
    provider = data.get("discovery_provider")
    selected_city = data.get("discovery_city") if city is ... else city
    selected_region = data.get("discovery_region") if region is ... else region
    try:
        async with async_session_factory() as session:
            preview = await run_legal_discovery_preview(
                session,
                query=query,
                city=selected_city,
                region=selected_region,
                limit=limit,
                provider_code=provider,
            )
    except BrowserBackendError as exc:
        await _safe_edit_message(
            callback.message,
            build_discovery_browser_error_text(exc),
            reply_markup=discovery_browser_error_markup(),
        )
        await _safe_callback_answer(callback, "Ошибка browser backend", show_alert=True)
        return
    except RuntimeError as exc:
        await _safe_edit_message(
            callback.message,
            build_discovery_browser_error_text(exc),
            reply_markup=discovery_browser_error_markup(),
        )
        await _safe_callback_answer(callback, "Ошибка browser backend", show_alert=True)
        return

    await state.update_data(
        last_discovery_preview_id=preview.preview_id,
        last_discovery_limit=limit,
    )
    markup = discovery_zero_result_markup() if preview.total_found == 0 else discovery_preview_markup(preview_callback_token(preview.preview_id))
    await _safe_edit_message(callback.message, _render_preview(preview), reply_markup=markup)
    await _safe_callback_answer(callback, "Preview готов.")


def _render_preview(preview) -> str:
    if preview.total_found == 0:
        return _render_zero_result_preview(preview)

    lines = [
        "Поиск компаний завершён",
        "",
        f"Найдено компаний: {preview.total_found}",
        f"Активных: {preview.active_count}",
        f"Неактивных: {preview.inactive_count}",
        f"Статус неизвестен: {preview.unknown_status_count}",
        f"Новых для CRM: {preview.new_count}",
        f"Дублей в CRM: {preview.duplicate_count}",
        f"С ИНН: {preview.with_inn_count}",
        f"С ОГРН: {preview.with_ogrn_count}",
        f"С сайтами: {preview.with_website_count}",
        f"С телефонами: {preview.with_phone_count}",
        f"Слабые данные: {preview.weak_count}",
        f"Parser candidates: {preview.parser_candidates_count}",
        f"До region post-filter: {preview.candidates_before_region}",
        f"Profile fetch ok: {preview.profile_fetch_success}",
        f"Profile fetch failed: {preview.profile_fetch_failed}",
        f"Отфильтровано по региону: {preview.filtered_by_region_count}",
        f"Отброшено как не компания: {preview.skipped_not_company_count}",
        "",
        "Первые результаты:",
    ]
    for index, item in enumerate(preview.items[:5], start=1):
        inn_value = item.company.inn or ("будет получен из профиля" if item.company.checko_profile_url else "не получен")
        lines.append(
            f"{index}. {item.company.legal_name} — ИНН {inn_value} — "
            f"{item.company.status or 'unknown'} — {item.company.city or item.company.region or 'регион не указан'}"
        )
    return "\n".join(lines)


def _render_zero_result_preview(preview) -> str:
    region_value = preview.region or preview.city or preview.debug_info.get("requested_region") or "не указан"
    okved_value = preview.okved_code or preview.debug_info.get("requested_okved") or "не указан"
    lines = [
        "Поиск компаний завершён, но компаний не найдено",
        "",
        f"ОКВЭД: {okved_value}",
        f"Регион: {region_value}",
        f"Final URL: {preview.debug_final_url or '-'}",
        f"Title: {_trim_debug_value(preview.debug_title)}",
        f"HTML: {preview.debug_html_chars} символов",
        f"Текст: {preview.debug_text_chars} символов",
        f"/company/ ссылок найдено: {preview.company_links_found}",
        f"Candidate-блоков найдено: {preview.parser_candidates_count}",
        f"До region post-filter: {preview.candidates_before_region}",
        f"Profile fetch ok: {preview.profile_fetch_success}",
        f"Profile fetch failed: {preview.profile_fetch_failed}",
        f"Отброшено как не компания: {preview.skipped_not_company_count}",
        f"Отфильтровано по региону: {preview.filtered_by_region_count}",
    ]
    if preview.debug_snapshot_path:
        lines.append(f"Debug snapshot: {preview.debug_snapshot_path}")
    if preview.debug_info.get("before_region_html_path"):
        lines.append(f"Before region HTML: {preview.debug_info['before_region_html_path']}")
    if preview.debug_info.get("after_region_html_path"):
        lines.append(f"After region HTML: {preview.debug_info['after_region_html_path']}")
    if "region_filter_applied" in preview.debug_info:
        lines.append(f"Region UI applied: {preview.debug_info.get('region_filter_applied')}")
    if preview.debug_info.get("region_filter_error"):
        lines.append(f"Region UI error: {preview.debug_info['region_filter_error']}")
    if preview.parser_candidates_count == 0:
        lines.extend(
            [
                "",
                "Парсер не нашёл карточки компаний на странице Checko.",
                "Включите CHECKO_HTML_DEBUG=true и проверьте сохранённый HTML.",
            ]
        )
    lines.extend(
        [
            "",
            "Что проверить:",
            "1. Правильно ли выбран ОКВЭД.",
            "2. Есть ли компании по этому региону на Checko.",
            "3. Не показал ли Checko защитную или пустую страницу.",
            "4. Для диагностики включите CHECKO_HTML_DEBUG=true.",
        ]
    )
    return "\n".join(lines)


def build_discovery_browser_error_text(exc: Exception) -> str:
    detail = str(exc).lower()
    if "timed out" in detail or "timeout" in detail:
        return DISCOVERY_BROWSER_ERROR_TIMEOUT_TEXT
    if "not installed" in detail or "not fetched" in detail:
        return DISCOVERY_BROWSER_ERROR_INSTALL_TEXT
    if "parse" in detail or "разобрать" in detail:
        return DISCOVERY_BROWSER_ERROR_PARSE_TEXT
    return DISCOVERY_BROWSER_ERROR_RUNTIME_TEXT


def _trim_debug_value(value: str | None, limit: int = 120) -> str:
    text = (value or "").strip()
    if not text:
        return "-"
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


async def _safe_edit_message(message: Message, text: str, *, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await message.edit_reply_markup(reply_markup=reply_markup)


async def _safe_callback_answer(callback: CallbackQuery, text: str | None = None, *, show_alert: bool = False) -> None:
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest as exc:
        if _is_expired_callback_error(exc):
            return
        raise


def _is_expired_callback_error(exc: TelegramBadRequest) -> bool:
    detail = str(exc).lower()
    return "query is too old" in detail or "query id is invalid" in detail or "response timeout expired" in detail
