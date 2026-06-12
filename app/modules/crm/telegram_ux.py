from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.crm.constants import TaskStatus
from app.modules.crm.models import CRMUser, Company, FollowUpTask
from app.modules.crm.service import format_datetime
from app.modules.crm.touch_service import TOUCH_PLAN
from app.modules.digest.models import DigestSettings
from app.modules.legal_discovery.models import LegalDiscoveryCursor
from app.modules.lead_fit.schemas import LeadFitScore


TELEGRAM_TEXT_LIMIT = 3500
LIST_PREVIEW_LIMIT = 10
REASON_LIMIT = 120

LEAD_GROUP_META = {
    "A_hot_priority": {"title": "🔥 Горячие / A", "short": "🔥 Горячие"},
    "B_warm_potential": {"title": "🟡 Перспективные / B", "short": "🟡 Перспективные"},
    "C_neutral_database": {"title": "⚪ Нейтральные / C", "short": "⚪ Нейтральные"},
    "D_low_priority": {"title": "🔻 Низкий приоритет / D", "short": "🔻 Низкий приоритет"},
    "excluded_do_not_contact": {"title": "🚫 Исключённые", "short": "🚫 Исключённые"},
}

TOUCH_STAGE_LABELS = {
    stage.value: f"{index}. {title}"
    for index, (stage, _, title) in enumerate(TOUCH_PLAN, start=1)
}
TOUCH_STAGE_INDEX = {
    stage.value: index
    for index, (stage, _, _) in enumerate(TOUCH_PLAN, start=1)
}


def clamp_text(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> str:
    if len(text) <= limit:
        return text
    clipped = text[: limit - 3].rstrip()
    return f"{clipped}..."


def shorten_text(text: str | None, limit: int = REASON_LIMIT) -> str:
    value = (text or "").strip()
    if not value:
        return "нет данных"
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3].rstrip()}..."


def format_lead_group_count_lines(summary) -> list[str]:
    return [
        f"{LEAD_GROUP_META['A_hot_priority']['title']}: {summary.A_hot_priority}",
        f"{LEAD_GROUP_META['B_warm_potential']['title']}: {summary.B_warm_potential}",
        f"{LEAD_GROUP_META['C_neutral_database']['title']}: {summary.C_neutral_database}",
        f"{LEAD_GROUP_META['D_low_priority']['title']}: {summary.D_low_priority}",
        f"{LEAD_GROUP_META['excluded_do_not_contact']['title']}: {summary.excluded_do_not_contact}",
    ]


def render_lead_groups_menu(summary) -> str:
    lines = ["🏷 Группы лидов", ""]
    lines.extend(format_lead_group_count_lines(summary))
    return clamp_text("\n".join(lines))


def render_lead_group_companies(
    group: str,
    companies: list[Company],
    lead_fit_scores: dict[int, LeadFitScore | None],
    *,
    page: int = 0,
) -> str:
    title = LEAD_GROUP_META[group]["title"]
    start = page * LIST_PREVIEW_LIMIT
    visible = companies[start : start + LIST_PREVIEW_LIMIT]
    lines = [f"🏷 {title}", ""]
    if not visible:
        lines.append("В этой группе пока нет компаний.")
        return clamp_text("\n".join(lines))

    for index, company in enumerate(visible, start=start + 1):
        location = ", ".join(part for part in [company.city, company.region] if part) or "город/регион не указаны"
        score = company.lead_fit_score if company.lead_fit_score is not None else "—"
        lines.append(f"{index}. {company.name} — {location} — score {score}")
        lead_fit = lead_fit_scores.get(company.id)
        reason = lead_fit.reasons[0] if lead_fit and lead_fit.reasons else company.notes or "нужна дополнительная проверка"
        lines.append(f"   Причина: {shorten_text(reason, 160)}")
        lines.append("")
    return clamp_text("\n".join(lines).rstrip())


def render_lead_fit_block(lead_fit: LeadFitScore | None) -> str:
    if lead_fit is None:
        return "🏷 Приоритет не рассчитан"

    lines = [f"🏷 Приоритет: {lead_fit.group_label} / {lead_fit.total_score}"]
    if lead_fit.reasons:
        lines.append("Причины:")
        lines.extend(f"— {shorten_text(reason)}" for reason in lead_fit.reasons[:4])
    if lead_fit.disqualifiers:
        lines.append("Ограничения:")
        lines.extend(f"— {shorten_text(reason)}" for reason in lead_fit.disqualifiers[:2])
    lines.extend(["", "Следующий шаг:", shorten_text(lead_fit.recommended_next_action, 220)])
    return "\n".join(lines)


def render_touch_plan_block(tasks: list[FollowUpTask]) -> str:
    if not tasks:
        return "📅 План 7 касаний\n\nПлан ещё не создан."

    current = next((task for task in tasks if task.status == TaskStatus.OPEN.value), tasks[-1])
    next_task = None
    if current.status == TaskStatus.OPEN.value:
        current_index = tasks.index(current)
        next_task = next((task for task in tasks[current_index + 1 :] if task.status == TaskStatus.OPEN.value), None)

    current_stage = TOUCH_STAGE_LABELS.get(current.interaction_stage or "", current.title)
    lines = [
        "📅 План 7 касаний",
        "",
        f"Текущее касание: {current_stage}",
        f"Статус: {current.status}",
        f"Дата/время: {format_datetime(current.due_at)}",
    ]
    if next_task:
        next_stage = TOUCH_STAGE_LABELS.get(next_task.interaction_stage or "", next_task.title)
        lines.append(f"Следующая задача: {next_stage} — {format_datetime(next_task.due_at)}")
    else:
        lines.append("Следующая задача: новых открытых касаний нет.")
    return "\n".join(lines)


def render_open_tasks(company: Company, tasks: list[FollowUpTask]) -> str:
    lines = [f"📅 Открытые задачи: {company.name}", ""]
    if not tasks:
        lines.append("Открытых задач нет.")
        return clamp_text("\n".join(lines))

    for index, task in enumerate(tasks[:LIST_PREVIEW_LIMIT], start=1):
        stage = TOUCH_STAGE_LABELS.get(task.interaction_stage or "", task.title)
        lines.append(f"{index}. {stage}")
        lines.append(f"   Срок: {format_datetime(task.due_at)}")
        lines.append(f"   Статус: {task.status}")
        lines.append("")
    return clamp_text("\n".join(lines).rstrip())


def render_my_touches_today(tasks: list[FollowUpTask]) -> str:
    lines = ["📅 Мои касания сегодня", ""]
    if not tasks:
        lines.append("На сегодня касаний нет.")
        return "\n".join(lines)

    for index, task in enumerate(tasks[:LIST_PREVIEW_LIMIT], start=1):
        company_name = task.company.name if task.company else f"Компания #{task.company_id}"
        stage_index = TOUCH_STAGE_INDEX.get(task.interaction_stage or "", 0)
        stage_text = f"касание {stage_index}/7" if stage_index else "касание"
        due_text = format_datetime(task.due_at) if task.due_at else "без срока"
        lines.append(f"{index}. {company_name} — {stage_text} — до {due_text}")
        lines.append(f"   Задача: {shorten_text(task.title, 200)}")
        lines.append("")
    return clamp_text("\n".join(lines).rstrip())


def render_delete_confirmation(company: Company) -> str:
    return (
        f"Удалить {company.name} из активной CRM?\n"
        "История сохранится, компания будет скрыта из списков."
    )


def render_admin_reset_prompt(mode: str = "crm_only") -> str:
    if mode == "all_data":
        return (
            "Это удалит все рабочие данные, discovery cursors, research, insights, proposals и debug-файлы. "
            "Пользователи по умолчанию сохраняются.\n\n"
            "Для подтверждения отправьте точный текст:\nRESET ALL DATA"
        )
    return (
        "Это удалит CRM-данные, компании, задачи, инсайты, research/proposals и discovery cursors. "
        "Пользователи по умолчанию сохраняются.\n\n"
        "Для подтверждения отправьте точный текст:\nRESET CRM"
    )


def render_admin_reset_disabled() -> str:
    return "Reset отключён. Установите ALLOW_DB_RESET=true."


def render_admin_reset_result(result: dict[str, int | bool]) -> str:
    parts = [f"{key}={value}" for key, value in result.items() if key not in {"mode", "keep_users", "clear_debug_files"}]
    return clamp_text(f"База очищена: {', '.join(parts)}")


async def build_system_status_snapshot(session: AsyncSession) -> dict[str, Any]:
    settings = get_settings()
    total_companies = int(await session.scalar(select(func.count(Company.id))) or 0)
    total_users = int(await session.scalar(select(func.count(CRMUser.id))) or 0)
    open_tasks = int(
        await session.scalar(select(func.count(FollowUpTask.id)).where(FollowUpTask.status == TaskStatus.OPEN.value)) or 0
    )
    total_cursors = int(await session.scalar(select(func.count(LegalDiscoveryCursor.id))) or 0)
    digest_settings = int(await session.scalar(select(func.count(DigestSettings.id))) or 0)
    return {
        "companies": total_companies,
        "users": total_users,
        "open_tasks": open_tasks,
        "discovery_cursors": total_cursors,
        "digest_settings": digest_settings,
        "allow_db_reset": settings.allow_db_reset,
        "legal_discovery_provider": settings.legal_discovery_provider,
        "checko_html_enabled": settings.checko_html_enabled,
        "checko_html_base_url": settings.checko_html_base_url,
        "checko_html_debug": settings.checko_html_debug,
        "checko_html_page_delay_ms": settings.checko_html_page_delay_ms,
        "storage_path": str(settings.storage_path),
        "admin_ids": len(settings.admin_id_list),
    }


def render_system_status_text(snapshot: dict[str, Any]) -> str:
    lines = [
        "ℹ️ Состояние системы",
        "",
        f"Компаний: {snapshot.get('companies', 0)}",
        f"Пользователей CRM: {snapshot.get('users', 0)}",
        f"Открытых задач: {snapshot.get('open_tasks', 0)}",
        f"Discovery cursors: {snapshot.get('discovery_cursors', 0)}",
        f"Digest settings: {snapshot.get('digest_settings', 0)}",
        "",
        "Флаги:",
        f"ALLOW_DB_RESET: {'true' if snapshot.get('allow_db_reset') else 'false'}",
        f"ADMIN_IDS: {snapshot.get('admin_ids', 0)}",
        "",
        "Legal discovery:",
        f"Provider: {snapshot.get('legal_discovery_provider', 'n/a')}",
        f"Checko HTML: {'on' if snapshot.get('checko_html_enabled') else 'off'}",
        f"Base URL: {snapshot.get('checko_html_base_url', 'n/a')}",
        f"Debug: {'on' if snapshot.get('checko_html_debug') else 'off'}",
        f"Page delay ms: {snapshot.get('checko_html_page_delay_ms', 0)}",
        "",
        f"Storage: {snapshot.get('storage_path', 'n/a')}",
    ]
    return "\n".join(lines)


def render_search_settings_text() -> str:
    settings = get_settings()
    lines = [
        "🔎 Настройки поиска",
        "",
        f"LEGAL_DISCOVERY_PROVIDER: {settings.legal_discovery_provider}",
        f"LEGAL_DISCOVERY_DEFAULT_LIMIT: {settings.legal_discovery_default_limit}",
        f"CHECKO_HTML_ENABLED: {'true' if settings.checko_html_enabled else 'false'}",
        f"CHECKO_HTML_BASE_URL: {settings.checko_html_base_url}",
        f"CHECKO_HTML_ONLY_MAIN_OKVED: {'true' if settings.checko_html_only_main_okved else 'false'}",
        f"CHECKO_HTML_ONLY_ACTIVE: {'true' if settings.checko_html_only_active else 'false'}",
        f"CHECKO_HTML_PROFILE_ENABLED: {'true' if settings.checko_html_profile_enabled else 'false'}",
        f"CHECKO_HTML_PAGE_DELAY_MS: {settings.checko_html_page_delay_ms}",
        f"CHECKO_HTML_DEBUG: {'true' if settings.checko_html_debug else 'false'}",
        "",
        "Настройки только для просмотра.",
    ]
    return "\n".join(lines)


def render_website_research_result(outcome, company: Company) -> str:
    lines = ["🧠 Website research", ""]
    lines.append(f"Статус: {outcome.status}")
    lines.append(f"Компания: {company.name}")
    if outcome.selected_url:
        lines.append(f"Сайт: {outcome.selected_url}")
    if outcome.selected_confidence:
        lines.append(f"Confidence: {outcome.selected_confidence}")
    lines.append(f"Сайт записан: {'да' if company.website == outcome.selected_url and outcome.selected_url else 'нет'}")
    if outcome.references:
        lines.append(f"Denylist/отклонено: {shorten_text(outcome.references[0], 180)}")
    if outcome.reasons:
        lines.append(f"Комментарий: {shorten_text(outcome.reasons[0], 180)}")
    if outcome.selected_url is None:
        lines.append("Warning: сайт не найден или требует ручной проверки.")
    return clamp_text("\n".join(lines))


def render_company_card_sections(
    base_text: str,
    lead_fit: LeadFitScore | None,
    touch_tasks: list[FollowUpTask],
) -> str:
    blocks = [base_text, "", render_lead_fit_block(lead_fit), "", render_touch_plan_block(touch_tasks)]
    return clamp_text("\n".join(blocks))


def is_admin_telegram_id(telegram_user_id: int | None) -> bool:
    if telegram_user_id is None:
        return False
    return telegram_user_id in get_settings().admin_id_list
