from __future__ import annotations

from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.database import async_session_factory
from app.modules.crm.keyboards import company_actions
from app.modules.crm.service import format_company_card, get_company, humanize_company_status, humanize_priority
from app.modules.proposals.keyboards import (
    manual_package_actions_markup,
    manual_package_selection_markup,
    package_suggestions_markup,
    proposal_file_markup,
    proposal_history_markup,
    proposals_menu_markup,
)
from app.modules.proposals.service import (
    generate_commercial_proposal,
    generate_contract_draft,
    generate_service_appendix,
    get_proposal_draft,
    list_company_proposal_drafts,
    parse_selected_packages,
    suggest_packages_for_company,
)

router = Router(name="proposals")


class ProposalStates(StatesGroup):
    manual_selection = State()


@router.callback_query(F.data.startswith("proposal:open:"))
async def proposal_open_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть раздел КП / Договор.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        company = await get_company(session, company_id)

    if not company:
        await callback.answer("Компания не найдена.", show_alert=True)
        return

    await state.clear()
    text = "\n".join(
        [
            "📄 КП / Договор",
            "",
            f"Клиника: {company.name}",
            f"Статус: {humanize_company_status(company.status)}",
            f"Приоритет: {humanize_priority(company.priority)}",
            "",
            "Выберите действие:",
        ]
    )
    await _safe_edit_message(callback.message, text, reply_markup=proposals_menu_markup(company_id))
    await callback.answer()


@router.callback_query(F.data.startswith("proposal:menu:suggest:"))
async def proposal_suggest_packages(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось подобрать пакеты.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        suggestions = await suggest_packages_for_company(session, company_id)

    text = _render_suggestions_text(suggestions)
    await _safe_edit_message(callback.message, text, reply_markup=package_suggestions_markup(company_id))
    await callback.answer()


@router.callback_query(F.data.startswith("proposal:menu:generate:"))
async def proposal_generate_direct(callback: CallbackQuery) -> None:
    await _generate_proposal_from_codes(callback, selected_codes=None)


@router.callback_query(F.data.startswith("proposal:action:auto:"))
async def proposal_generate_auto_from_suggestions(callback: CallbackQuery) -> None:
    await _generate_proposal_from_codes(callback, selected_codes=None)


@router.callback_query(F.data.startswith("proposal:menu:contract:"))
async def proposal_contract_direct(callback: CallbackQuery) -> None:
    await _generate_contract_from_codes(callback, selected_codes=None)


@router.callback_query(F.data.startswith("proposal:menu:appendix:"))
async def proposal_appendix_direct(callback: CallbackQuery) -> None:
    await _generate_appendix_from_codes(callback, selected_codes=None)


@router.callback_query(F.data.startswith("proposal:manual:start:"))
async def proposal_manual_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть ручной выбор.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    data = await state.get_data()
    selected_codes = data.get("selected_packages", [])
    await state.set_state(ProposalStates.manual_selection)
    await state.update_data(company_id=company_id, selected_packages=selected_codes)
    text = "Выберите пакеты вручную и нажмите «Продолжить»."
    await _safe_edit_message(
        callback.message,
        text,
        reply_markup=manual_package_selection_markup(company_id, selected_codes),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("proposal:manual:toggle:"))
async def proposal_manual_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось обновить выбор.", show_alert=True)
        return

    _, _, _, company_id_raw, code = callback.data.split(":", 4)
    company_id = int(company_id_raw)
    data = await state.get_data()
    selected_codes = list(data.get("selected_packages", []))
    if code in selected_codes:
        selected_codes.remove(code)
    else:
        selected_codes.append(code)
    await state.set_state(ProposalStates.manual_selection)
    await state.update_data(company_id=company_id, selected_packages=selected_codes)
    await _safe_edit_message(
        callback.message,
        "Выберите пакеты вручную и нажмите «Продолжить».",
        reply_markup=manual_package_selection_markup(company_id, selected_codes),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("proposal:manual:continue:"))
async def proposal_manual_continue(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Не удалось продолжить.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    data = await state.get_data()
    selected_codes = data.get("selected_packages", [])
    if not selected_codes:
        await callback.answer("Сначала выберите хотя бы один пакет.", show_alert=True)
        return

    text = "Пакеты выбраны. Что сформировать дальше?"
    await _safe_edit_message(callback.message, text, reply_markup=manual_package_actions_markup(company_id))
    await callback.answer()


@router.callback_query(F.data.startswith("proposal:manual:proposal:"))
async def proposal_manual_generate(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await _generate_proposal_from_codes(callback, selected_codes=data.get("selected_packages"))


@router.callback_query(F.data.startswith("proposal:manual:contract:"))
async def proposal_manual_contract(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await _generate_contract_from_codes(callback, selected_codes=data.get("selected_packages"))


@router.callback_query(F.data.startswith("proposal:manual:appendix:"))
async def proposal_manual_appendix(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await _generate_appendix_from_codes(callback, selected_codes=data.get("selected_packages"))


@router.callback_query(F.data.startswith("proposal:menu:history:"))
async def proposal_history(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть историю.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        drafts = await list_company_proposal_drafts(session, company_id)

    text = _render_history_text(drafts)
    await _safe_edit_message(
        callback.message,
        text,
        reply_markup=proposal_history_markup(company_id, [draft.id for draft in drafts]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("proposal:history:item:"))
async def proposal_history_item(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть черновик.", show_alert=True)
        return

    _, _, _, company_id_raw, draft_id_raw = callback.data.split(":", 4)
    async with async_session_factory() as session:
        draft = await get_proposal_draft(session, int(company_id_raw), int(draft_id_raw))

    if not draft:
        await callback.answer("Черновик не найден.", show_alert=True)
        return

    snippet = draft.content[:3200]
    if len(draft.content) > 3200:
        snippet += "\n\n... (обрезано)"
    await _safe_edit_message(
        callback.message,
        f"{draft.title}\n\n{snippet}",
        reply_markup=proposal_file_markup(int(company_id_raw), draft.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("proposal:file:send:"))
async def proposal_send_file(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось отправить файл.", show_alert=True)
        return

    _, _, _, company_id_raw, draft_id_raw = callback.data.split(":", 4)
    async with async_session_factory() as session:
        draft = await get_proposal_draft(session, int(company_id_raw), int(draft_id_raw))

    if not draft:
        await callback.answer("Черновик не найден.", show_alert=True)
        return

    file_path = Path(draft.file_path)
    if not file_path.exists():
        await callback.answer("Файл не найден на диске.", show_alert=True)
        return

    await callback.message.answer_document(FSInputFile(file_path), caption=draft.title)
    await callback.answer("Файл отправлен.")


@router.callback_query(F.data.startswith("proposal:menu:files:"))
async def proposal_latest_files(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Не удалось открыть последние файлы.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        drafts = await list_company_proposal_drafts(session, company_id, limit=3)

    sent_any = False
    for draft in drafts:
        file_path = Path(draft.file_path)
        if file_path.exists():
            await callback.message.answer_document(FSInputFile(file_path), caption=draft.title)
            sent_any = True

    if not sent_any:
        await callback.message.answer("Последние proposal/contract файлы не найдены.")
    await callback.answer()


async def _generate_proposal_from_codes(callback: CallbackQuery, selected_codes: list[str] | None) -> None:
    if not callback.message:
        await callback.answer("Не удалось сформировать КП.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        result = await generate_commercial_proposal(
            session,
            company_id,
            selected_package_codes=selected_codes,
            use_ai=True,
        )

    await callback.message.answer_document(FSInputFile(result.file_path), caption=result.title)
    await callback.answer("КП готово.")


async def _generate_contract_from_codes(callback: CallbackQuery, selected_codes: list[str] | None) -> None:
    if not callback.message:
        await callback.answer("Не удалось сформировать черновик договора.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        result = await generate_contract_draft(session, company_id, selected_package_codes=selected_codes)

    await callback.message.answer_document(FSInputFile(result.file_path), caption=result.title)
    await callback.answer("Черновик договора готов.")


async def _generate_appendix_from_codes(callback: CallbackQuery, selected_codes: list[str] | None) -> None:
    if not callback.message:
        await callback.answer("Не удалось сформировать приложение.", show_alert=True)
        return

    company_id = int(callback.data.rsplit(":", 1)[-1])
    async with async_session_factory() as session:
        result = await generate_service_appendix(session, company_id, selected_package_codes=selected_codes)

    await callback.message.answer_document(FSInputFile(result.file_path), caption=result.title)
    await callback.answer("Приложение готово.")


def _render_suggestions_text(suggestions: list) -> str:
    lines = ["💰 Рекомендуемые пакеты", ""]
    for index, item in enumerate(suggestions, start=1):
        confidence = {"high": "высокая", "medium": "средняя", "low": "низкая"}.get(item.confidence, item.confidence)
        lines.extend(
            [
                f"{index}. {item.title}",
                f"Стоимость: {item.price}",
                f"Уверенность: {confidence}",
                f"Почему: {item.reason}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _render_history_text(drafts: list) -> str:
    lines = ["📜 История КП/договоров", ""]
    if not drafts:
        lines.append("Пока нет сохранённых черновиков.")
        return "\n".join(lines)

    type_labels = {
        "commercial_proposal": "КП",
        "contract_draft": "Договор",
        "service_appendix": "Приложение",
    }
    for index, draft in enumerate(drafts, start=1):
        packages = ", ".join(parse_selected_packages(draft.selected_packages))
        package_suffix = f" — packages: {packages}" if packages else ""
        lines.append(
            f"{index}. {type_labels.get(draft.draft_type, draft.draft_type)} — "
            f"{draft.created_at:%d.%m.%Y %H:%M}{package_suffix}"
        )
    return "\n".join(lines)


async def _safe_edit_message(message: Message, text: str, *, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
        await message.edit_reply_markup(reply_markup=reply_markup)
