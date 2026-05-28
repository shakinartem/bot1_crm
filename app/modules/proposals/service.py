from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.modules.ai.providers import get_ai_provider
from app.modules.ai.service import prepare_cold_call
from app.modules.crm.constants import (
    COMPANY_STATUS_LABELS,
    PRIORITY_LABELS,
    CompanyStatus,
    InteractionType,
    LeadPriority,
    TaskStatus,
)
from app.modules.crm.models import Company, FollowUpTask, LeadInteraction
from app.modules.crm.schemas import InteractionCreate
from app.modules.crm.service import add_interaction, get_company, humanize_company_status
from app.modules.enrichment.service import build_enrichment_context_for_company
from app.modules.intelligence.service import build_intelligence_context_for_company
from app.modules.proposals.models import ProposalDraft
from app.modules.proposals.packages import PACKAGE_ORDER, SERVICE_PACKAGES, ServicePackage
from app.modules.proposals.prompts import build_commercial_proposal_prompt
from app.modules.proposals.schemas import PackageSuggestion


PACKAGE_KEYWORDS = {
    "maps_reputation": ("карты", "отзывы", "репутация", "2гис", "яндекс", "гео"),
    "smm_funnel": ("соцсети", "контент", "рилс", "посты", "instagram", "vk", "telegram"),
    "crm_bot": ("заявки теряются", "администратор", "crm", "бот", "не фиксируют", "перезвон"),
}
CONTRACT_RESULT_MARKERS = ("contract_sent", "договор отправлен", "подготовить/проверить кп и договор")


@dataclass(slots=True)
class ProposalGenerationResult:
    title: str
    content: str
    file_path: Path
    selected_packages: list[PackageSuggestion]
    used_ai: bool


@dataclass(slots=True)
class ContractDraftResult:
    title: str
    content: str
    file_path: Path
    selected_packages: list[PackageSuggestion]


@dataclass(slots=True)
class ServiceAppendixResult:
    title: str
    content: str
    file_path: Path
    selected_packages: list[PackageSuggestion]


def list_service_packages() -> list[ServicePackage]:
    return [SERVICE_PACKAGES[code] for code in PACKAGE_ORDER]


async def suggest_packages_for_company(session: AsyncSession, company_id: int) -> list[PackageSuggestion]:
    company = await _load_company_context(session, company_id)
    if not company:
        return []

    ai_call_prep = await prepare_cold_call(session, company_id)
    haystack = _build_analysis_text(company, ai_call_prep)
    suggestions: dict[str, PackageSuggestion] = {}
    enrichment = await build_enrichment_context_for_company(session, company_id)
    intelligence = await build_intelligence_context_for_company(session, company_id)

    data_is_sparse = _is_sparse(company)
    if data_is_sparse:
        suggestions["audit_roadmap"] = _make_suggestion(
            "audit_roadmap",
            "Данных о текущей воронке мало, безопасный первый шаг — диагностика.",
            "high",
        )

    if not (company.website or "").strip():
        suggestions["landing_start"] = _make_suggestion(
            "landing_start",
            "У клиники не указан сайт, значит сначала важно собрать рабочую посадочную под запись.",
            "high",
        )
        suggestions.setdefault(
            "audit_roadmap",
            _make_suggestion(
                "audit_roadmap",
                "Перед полноценным запуском полезно быстро диагностировать путь пациента и точки потери заявок.",
                "medium",
            ),
        )

    if enrichment:
        if not (enrichment.signals.has_online_booking or enrichment.signals.has_callback_form):
            suggestions.setdefault(
                "landing_start",
                _make_suggestion(
                    "landing_start",
                    "По быстрому research не видно явной записи или callback-формы, поэтому стоит начать с посадочной точки и конверсии сайта.",
                    "high",
                ),
            )
            suggestions.setdefault(
                "audit_roadmap",
                _make_suggestion(
                    "audit_roadmap",
                    "Research показывает риск потери пациента между сайтом и обращением, поэтому безопасный первый шаг — диагностическая карта воронки.",
                    "high",
                ),
            )

    if intelligence:
        if not (intelligence.parsed_signals.has_online_booking or intelligence.parsed_signals.has_callback_form):
            suggestions.setdefault(
                "landing_start",
                _make_suggestion(
                    "landing_start",
                    "Intelligence не подтверждает явную онлайн-запись или форму, поэтому безопасный первый шаг — усилить точку входа и конверсию сайта.",
                    "high",
                ),
            )
            suggestions.setdefault(
                "audit_roadmap",
                _make_suggestion(
                    "audit_roadmap",
                    "INN-first intelligence показывает риск потери пациента до обращения, поэтому стоит начать с диагностического roadmap.",
                    "high",
                ),
            )
        if not intelligence.parsed_signals.has_reviews_section:
            suggestions.setdefault(
                "maps_reputation",
                _make_suggestion(
                    "maps_reputation",
                    "На сайте не видно сильных review-сигналов, поэтому стоит усилить локальную репутацию и карты.",
                    "medium",
                ),
            )
        if not (
            intelligence.parsed_socials.vk_links
            or intelligence.parsed_socials.telegram_links
            or intelligence.parsed_socials.instagram_links
        ):
            suggestions.setdefault(
                "smm_funnel",
                _make_suggestion(
                    "smm_funnel",
                    "Intelligence не нашел явных соцсетей, поэтому полезно проверить прогрев и контентную воронку вне сайта.",
                    "medium",
                ),
            )
        if intelligence.parsed_signals.has_implantation_keywords:
            suggestions.setdefault(
                "complex_growth",
                _make_suggestion(
                    "complex_growth",
                    "На сайте есть сигналы имплантации, поэтому можно осторожно обсуждать комплексный рост вокруг дорогих услуг.",
                    "medium",
                ),
            )
            suggestions.setdefault(
                "landing_start",
                _make_suggestion(
                    "landing_start",
                    "Имплантация требует сильной упаковки доверия и записи, поэтому landing-first шаг выглядит безопасно.",
                    "medium",
                ),
            )
        if any("теряется" in item.lower() for item in intelligence.hypotheses):
            suggestions.setdefault(
                "crm_bot",
                _make_suggestion(
                    "crm_bot",
                    "Intelligence дает гипотезу потери пациента в воронке, поэтому стоит рассмотреть CRM/follow-up автоматизацию.",
                    "medium",
                ),
            )
        if not enrichment.signals.has_reviews_section or not any(enrichment.detected_maps.values()):
            suggestions.setdefault(
                "maps_reputation",
                _make_suggestion(
                    "maps_reputation",
                    "В research мало сигналов отзывов или карт, поэтому стоит усилить локальное доверие и репутационные точки входа.",
                    "medium",
                ),
            )
        if not any(enrichment.detected_socials.values()):
            suggestions.setdefault(
                "smm_funnel",
                _make_suggestion(
                    "smm_funnel",
                    "В research не обнаружены явные соцсети, поэтому стоит проверить, как клиника прогревает аудиторию вне сайта.",
                    "medium",
                ),
            )
        if enrichment.signals.has_implantation_keywords:
            suggestions.setdefault(
                "complex_growth",
                _make_suggestion(
                    "complex_growth",
                    "На сайте видны сигналы имплантации, поэтому можно осторожно обсуждать комплексный рост вокруг более дорогих услуг.",
                    "medium",
                ),
            )
        if any("теряется" in item.lower() for item in enrichment.hypotheses):
            suggestions.setdefault(
                "crm_bot",
                _make_suggestion(
                    "crm_bot",
                    "Research даёт гипотезу потери пациента на пути до обращения, поэтому стоит рассмотреть CRM- и follow-up-автоматизацию.",
                    "medium",
                ),
            )
            suggestions.setdefault(
                "audit_roadmap",
                _make_suggestion(
                    "audit_roadmap",
                    "Research указывает на возможные точки потери пациента, поэтому стоит начать с диагностического roadmap.",
                    "high",
                ),
            )

    for code, keywords in PACKAGE_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            confidence = "medium" if code != "crm_bot" else "high"
            suggestions[code] = _make_suggestion(
                code,
                _keyword_reason(code),
                confidence,
            )

    if company.status in {
        CompanyStatus.INTERESTED.value,
        CompanyStatus.CONSULTATION_PLANNED.value,
        CompanyStatus.PROPOSAL_SENT.value,
    }:
        suggestions["complex_growth"] = _make_suggestion(
            "complex_growth",
            "Текущий статус показывает интерес к дальнейшему диалогу, поэтому можно предлагать комплексную систему роста.",
            "medium",
        )
        suggestions.setdefault(
            "audit_roadmap",
            _make_suggestion(
                "audit_roadmap",
                "Даже при интересе со стороны клиники диагностика помогает быстрее уточнить объём и приоритеты.",
                "medium",
            ),
        )

    if company.status == CompanyStatus.PROPOSAL_SENT.value or any(marker in haystack for marker in CONTRACT_RESULT_MARKERS):
        suggestions["complex_growth"] = _make_suggestion(
            "complex_growth",
            "Клиника уже на этапе обсуждения КП/договора, поэтому логично показать комплексный контур работ.",
            "high",
        )
        suggestions["smm_funnel"] = _make_suggestion(
            "smm_funnel",
            "На этапе КП полезно показать регулярный канал прогрева и входящих обращений через контент.",
            "medium",
        )
        suggestions["maps_reputation"] = _make_suggestion(
            "maps_reputation",
            "После консультации стоит усилить доверие через карты, отзывы и локальную упаковку.",
            "medium",
        )

    if not suggestions:
        suggestions["audit_roadmap"] = _make_suggestion(
            "audit_roadmap",
            "Если данных недостаточно или выраженный запрос не найден, диагностика остаётся самым безопасным первым шагом.",
            "low",
        )

    ordered = [suggestions[code] for code in PACKAGE_ORDER if code in suggestions]
    return ordered


async def generate_commercial_proposal(
    session: AsyncSession,
    company_id: int,
    selected_package_codes: list[str] | None = None,
    use_ai: bool = True,
) -> ProposalGenerationResult:
    company = await _load_company_context(session, company_id)
    if not company:
        raise ValueError("Company not found")

    selected_packages = await _resolve_selected_packages(session, company_id, selected_package_codes)
    company_context = await _build_company_context(session, company)

    content: str
    used_ai = False
    if use_ai and get_settings().ai_provider.lower() != "fallback":
        prompt = build_commercial_proposal_prompt(company_context, _prompt_package_payload(selected_packages))
        try:
            ai_content = await get_ai_provider().generate(prompt)
            if ai_content:
                content = ai_content.strip()
                used_ai = True
            else:
                content = _build_fallback_commercial_proposal(company_context, selected_packages)
        except Exception:
            content = _build_fallback_commercial_proposal(company_context, selected_packages)
    else:
        content = _build_fallback_commercial_proposal(company_context, selected_packages)

    title = f"Коммерческое предложение — {company.name}"
    file_path = _write_markdown_file("commercial_proposal", company.id, content)
    await _save_draft(
        session,
        company_id=company.id,
        draft_type="commercial_proposal",
        title=title,
        content=content,
        file_path=file_path,
        selected_packages=selected_packages,
        used_ai=used_ai,
        created_by="proposal_service",
    )
    await _log_draft_note(session, company.id, "Сформировано КП")
    return ProposalGenerationResult(
        title=title,
        content=content,
        file_path=file_path,
        selected_packages=selected_packages,
        used_ai=used_ai,
    )


async def generate_contract_draft(
    session: AsyncSession,
    company_id: int,
    selected_package_codes: list[str] | None = None,
) -> ContractDraftResult:
    company = await _load_company_context(session, company_id)
    if not company:
        raise ValueError("Company not found")

    selected_packages = await _resolve_selected_packages(session, company_id, selected_package_codes)
    content = _build_contract_draft(company, selected_packages)
    title = f"Черновик договора — {company.name}"
    file_path = _write_markdown_file("contract_draft", company.id, content)
    await _save_draft(
        session,
        company_id=company.id,
        draft_type="contract_draft",
        title=title,
        content=content,
        file_path=file_path,
        selected_packages=selected_packages,
        used_ai=False,
        created_by="proposal_service",
    )
    await _log_draft_note(session, company.id, "Сформирован черновик договора")
    return ContractDraftResult(
        title=title,
        content=content,
        file_path=file_path,
        selected_packages=selected_packages,
    )


async def generate_service_appendix(
    session: AsyncSession,
    company_id: int,
    selected_package_codes: list[str] | None = None,
) -> ServiceAppendixResult:
    company = await _load_company_context(session, company_id)
    if not company:
        raise ValueError("Company not found")

    selected_packages = await _resolve_selected_packages(session, company_id, selected_package_codes)
    content = _build_service_appendix(company, selected_packages)
    title = f"Приложение с услугами — {company.name}"
    file_path = _write_markdown_file("service_appendix", company.id, content)
    await _save_draft(
        session,
        company_id=company.id,
        draft_type="service_appendix",
        title=title,
        content=content,
        file_path=file_path,
        selected_packages=selected_packages,
        used_ai=False,
        created_by="proposal_service",
    )
    await _log_draft_note(session, company.id, "Сформировано приложение с услугами")
    return ServiceAppendixResult(
        title=title,
        content=content,
        file_path=file_path,
        selected_packages=selected_packages,
    )


async def list_company_proposal_drafts(
    session: AsyncSession,
    company_id: int,
    *,
    limit: int = 10,
) -> list[ProposalDraft]:
    result = await session.execute(
        select(ProposalDraft)
        .where(ProposalDraft.company_id == company_id)
        .order_by(ProposalDraft.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_proposal_draft(session: AsyncSession, company_id: int, proposal_id: int) -> ProposalDraft | None:
    result = await session.execute(
        select(ProposalDraft).where(
            ProposalDraft.company_id == company_id,
            ProposalDraft.id == proposal_id,
        )
    )
    return result.scalar_one_or_none()


def parse_selected_packages(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload if str(item) in SERVICE_PACKAGES]


async def _load_company_context(session: AsyncSession, company_id: int) -> Company | None:
    result = await session.execute(
        select(Company)
        .where(Company.id == company_id)
        .options(
            selectinload(Company.decision_makers),
            selectinload(Company.contacts),
            selectinload(Company.interactions),
            selectinload(Company.tasks),
            selectinload(Company.proposal_drafts),
            selectinload(Company.enrichment_snapshots),
        )
    )
    return result.scalar_one_or_none()


async def _build_company_context(session: AsyncSession, company: Company) -> dict:
    interactions = sorted(company.interactions, key=lambda item: item.created_at or datetime.min, reverse=True)[:8]
    tasks = sorted(
        [task for task in company.tasks if task.status == TaskStatus.OPEN.value],
        key=lambda item: (item.due_at is None, item.due_at or datetime.max),
    )[:5]
    latest_proposal = next(
        (draft for draft in sorted(company.proposal_drafts, key=lambda item: item.created_at or datetime.min, reverse=True)),
        None,
    )
    ai_call_prep = await prepare_cold_call(session, company.id)

    return {
        "name": company.name,
        "legal_name": company.legal_name,
        "city": company.city,
        "website": company.website,
        "status": company.status,
        "status_label": humanize_company_status(company.status),
        "priority": company.priority,
        "priority_label": PRIORITY_LABELS.get(company.priority, company.priority),
        "source": company.source,
        "notes": company.notes,
        "ai_call_prep": ai_call_prep,
        "latest_proposal": latest_proposal.content[:700] if latest_proposal else "",
        "recent_interactions": "\n".join(
            f"- {(item.created_at or datetime.now()):%d.%m.%Y %H:%M} | {item.type} | {item.summary or 'без комментария'}"
            for item in interactions
        ),
        "open_tasks": "\n".join(
            f"- {task.title}{f' ({task.due_at:%d.%m.%Y %H:%M})' if task.due_at else ''}"
            for task in tasks
        ),
    }


def _build_analysis_text(company: Company, ai_call_prep: str | None) -> str:
    chunks = [
        company.name,
        company.notes or "",
        company.website or "",
        ai_call_prep or "",
        " ".join(item.summary or "" for item in company.interactions[-10:]),
        " ".join(item.result or "" for item in company.interactions[-10:]),
    ]
    return " ".join(chunks).lower()


def _is_sparse(company: Company) -> bool:
    score = 0
    if company.website:
        score += 1
    if company.notes:
        score += 1
    if company.interactions:
        score += 1
    if company.contacts or company.phone:
        score += 1
    return score <= 1


def _keyword_reason(code: str) -> str:
    reasons = {
        "maps_reputation": "В заметках или истории касаний есть запрос на карты, отзывы или локальную репутацию.",
        "smm_funnel": "В заметках или касаниях есть интерес к соцсетям, контенту или регулярному прогреву.",
        "crm_bot": "По имеющимся данным есть риск потери заявок и перегрузки ручной обработкой обращений.",
    }
    return reasons[code]


def _make_suggestion(code: str, reason: str, confidence: str) -> PackageSuggestion:
    package = SERVICE_PACKAGES[code]
    return PackageSuggestion(
        code=code,
        title=package.title,
        price=package.price,
        reason=reason,
        confidence=confidence,
    )


async def _resolve_selected_packages(
    session: AsyncSession,
    company_id: int,
    selected_package_codes: list[str] | None,
) -> list[PackageSuggestion]:
    if selected_package_codes:
        items: list[PackageSuggestion] = []
        for code in PACKAGE_ORDER:
            if code in selected_package_codes:
                items.append(_make_suggestion(code, "Пакет выбран менеджером вручную.", "high"))
        return items or await suggest_packages_for_company(session, company_id)
    return await suggest_packages_for_company(session, company_id)


def _prompt_package_payload(selected_packages: list[PackageSuggestion]) -> list[dict]:
    items: list[dict] = []
    for suggestion in selected_packages:
        package = SERVICE_PACKAGES[suggestion.code]
        items.append(
            {
                "title": suggestion.title,
                "price": suggestion.price,
                "items": list(package.items),
                "reason": suggestion.reason,
            }
        )
    return items


def _build_fallback_commercial_proposal(company_context: dict, selected_packages: list[PackageSuggestion]) -> str:
    package_lines: list[str] = []
    client_requirements: list[str] = []
    for suggestion in selected_packages:
        package = SERVICE_PACKAGES[suggestion.code]
        package_lines.append(
            "\n".join(
                [
                    f"### {package.title}",
                    f"- Что входит: {', '.join(package.items)}",
                    f"- Ориентировочная стоимость: {package.price}",
                    f"- Зачем это клинике: {package.result}",
                ]
            )
        )
        client_requirements.extend(package.client_needs)

    next_step = "Предложить короткий созвон или разбор, чтобы подтвердить приоритеты и уточнить объём работ."
    if selected_packages and selected_packages[0].code == "complex_growth":
        next_step = "Предложить обсуждение комплексного плана с фиксацией первого месяца работ и ответственных со стороны клиники."

    return "\n".join(
        [
            "# Коммерческое предложение",
            "",
            f"Для: {company_context.get('name') or 'Клиника'}",
            "От: ШАРиК digital",
            "",
            "## 1. Контекст",
            (
                f"По имеющимся данным клиника находится в статусе "
                f"{company_context.get('status_label') or 'без уточнения статуса'}. "
                f"Город: {company_context.get('city') or 'не указан'}. "
                f"Сайт: {company_context.get('website') or 'не указан'}. "
                f"В заметках и касаниях отмечено: {company_context.get('notes') or 'подробности пока не зафиксированы'}."
            ),
            "",
            "## 2. Предполагаемая проблема",
            "- По имеющимся данным клиника может терять пациента между первым интересом и записью.",
            "- Стоит проверить, как связаны сайт, соцсети, карты, отзывы, формы заявки и скорость обработки обращений.",
            "- Просто вести соцсети без связки с воронкой и записью обычно недостаточно для устойчивого результата.",
            "",
            "## 3. Предлагаемое решение",
            "",
            "\n\n".join(package_lines),
            "",
            "## 4. План работ на первый месяц",
            "Неделя 1: собрать вводные, доступы и уточнить приоритеты.",
            "Неделя 2: провести диагностику текущей воронки и согласовать контур работ.",
            "Неделя 3: запустить первые улучшения по выбранным пакетам.",
            "Неделя 4: проверить обратную связь, зафиксировать результаты и следующий цикл работ.",
            "",
            "## 5. Что нужно от клиента",
            *[f"- {item}" for item in sorted(set(client_requirements))],
            "- данные по заявкам, если они уже собираются",
            "",
            "## 6. Стоимость",
            "Стоимость ориентировочная и зависит от объёма задач. Точная сумма подтверждается после диагностики и короткого согласования состава работ.",
            "",
            "## 7. Следующий шаг",
            next_step,
            "",
            "## 8. Сообщение клиенту",
            (
                "Подготовили черновой вариант решения по вашей digital-воронке. "
                "По имеющимся данным видим несколько точек, где можно усилить доверие, запись и обработку обращений. "
                "Предлагаю коротко созвониться, подтвердить приоритеты и уточнить финальный объём работ."
            ),
        ]
    )


def _build_contract_draft(company: Company, selected_packages: list[PackageSuggestion]) -> str:
    service_lines = []
    for suggestion in selected_packages:
        package = SERVICE_PACKAGES[suggestion.code]
        service_lines.append(f"### {package.title}")
        service_lines.extend(f"- {item}" for item in package.items)

    return "\n".join(
        [
            "# Черновик структуры договора",
            "",
            "## Важно",
            "Это не юридически финальный документ. Требуется проверка юристом и ручное внесение реквизитов.",
            "",
            "## 1. Стороны",
            "Исполнитель: ШАРиК digital",
            f"Заказчик: {company.legal_name or company.name}",
            "",
            "## 2. Предмет договора",
            "Оказание digital-услуг для повышения эффективности digital-воронки и привлечения/обработки заявок.",
            "",
            "## 3. Состав услуг",
            *service_lines,
            "",
            "## 4. Сроки",
            "Ориентировочно 1 месяц / по согласованию.",
            "",
            "## 5. Стоимость",
            "Ориентировочно, требует подтверждения после согласования объёма.",
            "",
            "## 6. Порядок взаимодействия",
            "- предоставление материалов",
            "- согласование",
            "- отчётность",
            "- коммуникация",
            "",
            "## 7. Порядок оплаты",
            "- предоплата / этапность — заполнить вручную",
            "- точные условия согласовать с клиентом",
            "",
            "## 8. Отчётность",
            "- ежемесячный отчёт",
            "- список выполненных работ",
            "- рекомендации на следующий период",
            "",
            "## 9. Что нужно уточнить юристом",
            "- реквизиты",
            "- точные сроки",
            "- ответственность",
            "- порядок оплаты",
            "- закрывающие документы",
            "- персональные данные",
            "- права на материалы",
        ]
    )


def _build_service_appendix(company: Company, selected_packages: list[PackageSuggestion]) -> str:
    sections: list[str] = []
    for index, suggestion in enumerate(selected_packages, start=1):
        package = SERVICE_PACKAGES[suggestion.code]
        sections.extend(
            [
                f"## Пакет {index}: {package.title}",
                "### Состав работ",
                *[f"- {item}" for item in package.items],
                "### Результат",
                f"- {package.result}",
                "### Что нужно от клиента",
                *[f"- {item}" for item in package.client_needs],
                "### Ориентировочная стоимость",
                f"- {package.price}",
                "",
            ]
        )

    return "\n".join(
        [
            "# Приложение: состав услуг",
            "",
            f"Клиент: {company.legal_name or company.name}",
            f"Дата: {datetime.now():%d.%m.%Y}",
            f"Пакеты: {', '.join(item.title for item in selected_packages)}",
            "",
            *sections,
            "## Общие условия",
            "- сроки уточняются после диагностики",
            "- стоимость может измениться при изменении объёма",
            "- финальные условия фиксируются в договоре",
        ]
    )


def _write_markdown_file(prefix: str, company_id: int, content: str) -> Path:
    settings = get_settings()
    proposals_dir = settings.storage_path / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_company_{company_id}_{datetime.now():%Y%m%d_%H%M%S}.md"
    file_path = proposals_dir / filename
    file_path.write_text(content, encoding="utf-8")
    return file_path


async def _save_draft(
    session: AsyncSession,
    *,
    company_id: int,
    draft_type: str,
    title: str,
    content: str,
    file_path: Path,
    selected_packages: list[PackageSuggestion],
    used_ai: bool,
    created_by: str,
) -> ProposalDraft:
    draft = ProposalDraft(
        company_id=company_id,
        draft_type=draft_type,
        title=title,
        content=content,
        file_path=str(file_path),
        selected_packages=json.dumps([item.code for item in selected_packages], ensure_ascii=False),
        used_ai=used_ai,
        created_by=created_by,
    )
    session.add(draft)
    await session.commit()
    await session.refresh(draft)
    return draft


async def _log_draft_note(session: AsyncSession, company_id: int, summary: str) -> None:
    await add_interaction(
        session,
        InteractionCreate(
            company_id=company_id,
            type=InteractionType.NOTE,
            summary=summary,
            created_by="proposal_service",
        ),
    )
