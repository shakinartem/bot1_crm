from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.ai.providers import get_ai_provider
from app.modules.crm.constants import ContactType, InteractionType
from app.modules.crm.models import Company, ContactPoint, LeadInteraction
from app.modules.crm.service import get_company
from app.modules.enrichment.fetcher import fetch_website
from app.modules.enrichment.schemas import dump_json_text
from app.modules.enrichment.service import build_enrichment_context_for_company
from app.modules.enrichment.analyzer import build_enrichment_hypotheses
from app.modules.intelligence.legal_lookup import find_legal_by_inn, search_legal_by_name
from app.modules.intelligence.models import IntelligenceSnapshot
from app.modules.intelligence.providers import get_search_provider
from app.modules.intelligence.schemas import (
    Bot2IntelligenceContextRead,
    CompanyIntelligenceResult,
    IntelligenceSnapshotRead,
    LegalCompany,
    ParsedCompanySite,
    WebsiteCandidate,
    WebsiteResolutionResult,
    parse_candidates,
    parse_contacts,
    parse_references,
    parse_signals,
    parse_socials,
)
from app.modules.intelligence.site_parser import parse_company_site
from app.modules.intelligence.website_resolver import resolve_official_website


async def enrich_company_intelligence(
    session: AsyncSession,
    company_id: int,
    inn: str | None = None,
    use_ai: bool = True,
) -> CompanyIntelligenceResult:
    company = await get_company(session, company_id)
    if not company:
        raise ValueError("Company not found")

    legal_candidates = await _resolve_legal_candidates(company, inn)
    if not legal_candidates:
        snapshot = await _save_snapshot(
            session,
            company_id=company_id,
            status="failed",
            error_message="Legal company was not found",
        )
        return CompanyIntelligenceResult(
            company_id=company_id,
            status="failed",
            error_message="Legal company was not found",
            snapshot_id=snapshot.id,
        )

    if len(legal_candidates) > 1 and not _has_clear_winner(legal_candidates):
        snapshot = await _save_snapshot(
            session,
            company_id=company_id,
            status="needs_review",
            inn=company.inn or inn,
            website_candidates_json=dump_json_text([]),
            raw_references_json=dump_json_text([]),
            error_message="Multiple legal candidates found",
        )
        return CompanyIntelligenceResult(
            company_id=company_id,
            status="needs_review",
            legal_candidates=legal_candidates,
            error_message="Multiple legal candidates found",
            snapshot_id=snapshot.id,
        )

    legal = _select_best_legal(legal_candidates)
    updated_fields = _apply_legal_company(company, legal)

    resolution = await resolve_official_website(
        legal,
        get_search_provider(),
        city=company.city or legal.city,
        known_phone=company.phone,
    )
    parsed_site: ParsedCompanySite | None = None
    hypotheses: list[str] = []
    ai_summary: str | None = None
    status = "partial"
    error_message: str | None = None

    if resolution.selected_url:
        fetch = await fetch_website(resolution.selected_url, timeout=get_settings().intelligence_request_timeout)
        if fetch.html:
            parsed_site = parse_company_site(fetch.html, fetch.final_url or resolution.selected_url)
            hypotheses = build_enrichment_hypotheses(_site_to_analysis(parsed_site))
            ai_summary = await _build_ai_summary(company, legal, resolution, parsed_site, hypotheses, use_ai=use_ai)
            updated_fields.extend(_apply_site_to_company(company, resolution, parsed_site))
            await _sync_contact_points(session, company, parsed_site)
            status = "success" if resolution.confidence >= 60 else "partial"
        else:
            status = "partial"
            error_message = fetch.error_message or "Website fetch failed"
    else:
        status = "partial"
        error_message = "Official website was not resolved"

    session.add(company)
    session.add(
        LeadInteraction(
            company_id=company_id,
            type=InteractionType.NOTE.value,
            summary=_build_interaction_summary(legal, resolution, updated_fields, error_message),
            created_by="intelligence_service",
        )
    )
    snapshot = await _save_snapshot(
        session,
        company_id=company_id,
        status=status,
        inn=legal.inn,
        legal_name=legal.legal_name,
        ogrn=legal.ogrn,
        legal_address=legal.address,
        legal_status=legal.status,
        okved=legal.okved,
        website_url=resolution.selected_url,
        website_confidence=resolution.confidence,
        website_candidates_json=dump_json_text([item.model_dump() for item in resolution.candidates]),
        parsed_contacts_json=dump_json_text(parsed_site.contacts.model_dump() if parsed_site else {}),
        parsed_socials_json=dump_json_text(parsed_site.socials.model_dump() if parsed_site else {}),
        parsed_signals_json=dump_json_text(parsed_site.signals.model_dump() if parsed_site else {}),
        hypotheses_json=dump_json_text(hypotheses),
        ai_summary=ai_summary,
        raw_references_json=dump_json_text([item.model_dump() for item in resolution.references]),
        error_message=error_message,
        flush_only=True,
    )
    await session.commit()
    await session.refresh(snapshot)

    return CompanyIntelligenceResult(
        company_id=company_id,
        status=status,
        legal_candidates=[],
        selected_legal=legal,
        website_resolution=resolution,
        parsed_site=parsed_site,
        hypotheses=hypotheses,
        ai_summary=ai_summary,
        error_message=error_message,
        snapshot_id=snapshot.id,
        updated_fields=_unique(updated_fields),
    )


async def find_legal_candidates_for_company(
    session: AsyncSession,
    company_id: int,
) -> list[LegalCompany]:
    company = await get_company(session, company_id)
    if not company:
        raise ValueError("Company not found")
    return await _resolve_legal_candidates(company, company.inn)


async def resolve_company_website(
    session: AsyncSession,
    company_id: int,
) -> WebsiteResolutionResult:
    company = await get_company(session, company_id)
    if not company:
        raise ValueError("Company not found")
    legal = await _get_or_find_single_legal(company)
    if not legal:
        return WebsiteResolutionResult(warnings=["Нужно сначала определить юрлицо или ИНН."])
    return await resolve_official_website(
        legal,
        get_search_provider(),
        city=company.city or legal.city,
        known_phone=company.phone,
    )


async def get_latest_intelligence(session: AsyncSession, company_id: int) -> IntelligenceSnapshotRead | None:
    result = await session.execute(
        select(IntelligenceSnapshot)
        .where(IntelligenceSnapshot.company_id == company_id)
        .order_by(IntelligenceSnapshot.created_at.desc(), IntelligenceSnapshot.id.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    return _snapshot_to_read(snapshot) if snapshot else None


async def get_intelligence_history(
    session: AsyncSession,
    company_id: int,
    limit: int = 10,
) -> list[IntelligenceSnapshotRead]:
    result = await session.execute(
        select(IntelligenceSnapshot)
        .where(IntelligenceSnapshot.company_id == company_id)
        .order_by(IntelligenceSnapshot.created_at.desc(), IntelligenceSnapshot.id.desc())
        .limit(limit)
    )
    return [_snapshot_to_read(item) for item in result.scalars().all()]


async def get_intelligence_snapshot(
    session: AsyncSession,
    company_id: int,
    snapshot_id: int,
) -> IntelligenceSnapshotRead | None:
    result = await session.execute(
        select(IntelligenceSnapshot).where(
            IntelligenceSnapshot.company_id == company_id,
            IntelligenceSnapshot.id == snapshot_id,
        )
    )
    snapshot = result.scalar_one_or_none()
    return _snapshot_to_read(snapshot) if snapshot else None


async def build_intelligence_context_for_company(
    session: AsyncSession,
    company_id: int,
) -> Bot2IntelligenceContextRead | None:
    latest = await get_latest_intelligence(session, company_id)
    if not latest:
        return None
    return Bot2IntelligenceContextRead(
        latest_snapshot_at=latest.created_at,
        status=latest.status,
        inn=latest.inn,
        legal_name=latest.legal_name,
        ogrn=latest.ogrn,
        legal_address=latest.legal_address,
        legal_status=latest.legal_status,
        okved=latest.okved,
        website_url=latest.website_url,
        website_confidence=latest.website_confidence,
        parsed_contacts=latest.parsed_contacts,
        parsed_socials=latest.parsed_socials,
        parsed_signals=latest.parsed_signals,
        hypotheses=latest.hypotheses,
        ai_summary=latest.ai_summary,
    )


async def apply_legal_candidate_and_enrich(
    session: AsyncSession,
    company_id: int,
    legal_candidate: LegalCompany,
    use_ai: bool = True,
) -> CompanyIntelligenceResult:
    company = await get_company(session, company_id)
    if not company:
        raise ValueError("Company not found")
    if not company.inn:
        company.inn = legal_candidate.inn
    return await enrich_company_intelligence(session, company_id, inn=legal_candidate.inn, use_ai=use_ai)


async def _resolve_legal_candidates(company: Company, inn: str | None) -> list[LegalCompany]:
    if inn:
        found = await find_legal_by_inn(inn)
        return [found] if found else []
    return await search_legal_by_name(company.name, city=company.city, region=company.region, limit=10)


async def _get_or_find_single_legal(company: Company) -> LegalCompany | None:
    candidates = await _resolve_legal_candidates(company, company.inn)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    if _has_clear_winner(candidates):
        return _select_best_legal(candidates)
    return None


def _apply_legal_company(company: Company, legal: LegalCompany) -> list[str]:
    updated_fields: list[str] = []
    mapping = {
        "inn": legal.inn,
        "legal_name": legal.legal_name,
        "ogrn": legal.ogrn,
        "address": legal.address,
        "city": legal.city,
        "region": legal.region,
    }
    for field_name, value in mapping.items():
        if value and not getattr(company, field_name):
            setattr(company, field_name, value)
            updated_fields.append(field_name)
    return updated_fields


def _apply_site_to_company(
    company: Company,
    resolution: WebsiteResolutionResult,
    parsed_site: ParsedCompanySite,
) -> list[str]:
    updated_fields: list[str] = []
    if resolution.selected_url and (not company.website or resolution.confidence >= 75):
        if company.website != resolution.selected_url:
            company.website = resolution.selected_url
            updated_fields.append("website")
    if not company.phone and parsed_site.contacts.phones:
        company.phone = parsed_site.contacts.phones[0]
        updated_fields.append("phone")
    if not company.vk_url and parsed_site.socials.vk_links:
        company.vk_url = parsed_site.socials.vk_links[0]
        updated_fields.append("vk_url")
    if not company.instagram_url and parsed_site.socials.instagram_links:
        company.instagram_url = parsed_site.socials.instagram_links[0]
        updated_fields.append("instagram_url")
    if not company.telegram_url and parsed_site.socials.telegram_links:
        company.telegram_url = parsed_site.socials.telegram_links[0]
        updated_fields.append("telegram_url")
    if not company.maps_url:
        maps = parsed_site.socials.yandex_maps_links or parsed_site.socials.two_gis_links
        if maps:
            company.maps_url = maps[0]
            updated_fields.append("maps_url")
    return updated_fields


async def _sync_contact_points(session: AsyncSession, company: Company, parsed_site: ParsedCompanySite) -> None:
    await _add_contacts(session, company, ContactType.PHONE.value, parsed_site.contacts.phones)
    await _add_contacts(session, company, ContactType.EMAIL.value, parsed_site.contacts.emails)
    await _add_contacts(session, company, ContactType.WEBSITE.value, [company.website] if company.website else [])
    await _add_contacts(session, company, ContactType.TELEGRAM.value, parsed_site.socials.telegram_links)
    await _add_contacts(session, company, ContactType.WHATSAPP.value, parsed_site.socials.whatsapp_links)
    await _add_contacts(session, company, ContactType.VK.value, parsed_site.socials.vk_links)
    await _add_contacts(session, company, ContactType.INSTAGRAM.value, parsed_site.socials.instagram_links)


async def _add_contacts(session: AsyncSession, company: Company, contact_type: str, values: list[str]) -> None:
    existing = {(contact.type, contact.value.strip().lower()) for contact in company.contacts}
    for value in values:
        clean = (value or "").strip()
        if not clean:
            continue
        key = (contact_type, clean.lower())
        if key in existing:
            continue
        session.add(
            ContactPoint(
                company_id=company.id,
                type=contact_type,
                value=clean,
                label="intelligence",
                is_primary=False,
            )
        )
        existing.add(key)


async def _build_ai_summary(
    company: Company,
    legal: LegalCompany,
    resolution: WebsiteResolutionResult,
    parsed_site: ParsedCompanySite,
    hypotheses: list[str],
    *,
    use_ai: bool,
) -> str:
    fallback = _build_fallback_summary(company, legal, resolution, parsed_site, hypotheses)
    if not use_ai or get_settings().ai_provider.lower() == "fallback":
        return fallback
    prompt = "\n".join(
        [
            "Ты помогаешь менеджеру SHARiK digital готовиться к звонку.",
            "Сделай осторожное sales-intelligence summary без выдумывания данных.",
            f"Клиника: {company.name}",
            f"Юрлицо: {legal.legal_name}",
            f"ИНН: {legal.inn}",
            f"Сайт: {resolution.selected_url or 'не найден'}",
            f"Сигналы: онлайн-запись {'да' if parsed_site.signals.has_online_booking else 'нет'}, "
            f"форма {'да' if parsed_site.signals.has_callback_form else 'нет'}, "
            f"отзывы {'да' if parsed_site.signals.has_reviews_section else 'нет'}, "
            f"врачи {'да' if parsed_site.signals.has_doctors_page else 'нет'}",
            f"Контакты: телефоны {', '.join(parsed_site.contacts.phones) or 'не найдены'}; "
            f"email {', '.join(parsed_site.contacts.emails) or 'не найдены'}",
            "Гипотезы:",
            *[f"- {item}" for item in hypotheses[:5]],
            "Формат:",
            "1. Что видно снаружи",
            "2. Возможные слабые места",
            "3. Что спросить на звонке",
            "4. Какой безопасный первый шаг предложить",
        ]
    )
    try:
        result = await get_ai_provider().generate(prompt)
    except Exception:
        result = None
    return (result or "").strip() or fallback


def _build_fallback_summary(
    company: Company,
    legal: LegalCompany,
    resolution: WebsiteResolutionResult,
    parsed_site: ParsedCompanySite,
    hypotheses: list[str],
) -> str:
    return "\n".join(
        [
            "Быстрое резюме intelligence",
            "",
            "Что видно снаружи:",
            f"- Юрлицо: {legal.legal_name} ({legal.inn})",
            f"- Сайт: {resolution.selected_url or 'не найден'}",
            f"- Контакты: {', '.join(parsed_site.contacts.phones[:2]) or 'не найдены'}; "
            f"email: {', '.join(parsed_site.contacts.emails[:2]) or 'не найдены'}",
            "",
            "Возможные слабые места:",
            f"- Онлайн-запись: {'есть' if parsed_site.signals.has_online_booking else 'в быстрой проверке не обнаружена'}",
            f"- Форма заявки: {'есть' if parsed_site.signals.has_callback_form else 'в быстрой проверке не обнаружена'}",
            f"- Отзывы: {'есть' if parsed_site.signals.has_reviews_section else 'в быстрой проверке не обнаружены'}",
            "",
            "Что спросить на звонке:",
            "- Как сейчас пациент записывается и как быстро обрабатываются обращения?",
            "- Какие каналы дают самый качественный поток заявок?",
            "",
            "Что можно предложить как первый шаг:",
            "- Осторожно предложить диагностику digital-воронки и точек потери пациента.",
            "",
            "Осторожные гипотезы:",
            *[f"- {item}" for item in hypotheses[:5]],
        ]
    )


async def _save_snapshot(session: AsyncSession, flush_only: bool = False, **payload) -> IntelligenceSnapshot:
    snapshot = IntelligenceSnapshot(**payload)
    session.add(snapshot)
    if flush_only:
        await session.flush()
    else:
        await session.commit()
        await session.refresh(snapshot)
    return snapshot


def _snapshot_to_read(snapshot: IntelligenceSnapshot) -> IntelligenceSnapshotRead:
    return IntelligenceSnapshotRead(
        id=snapshot.id,
        company_id=snapshot.company_id,
        status=snapshot.status,
        inn=snapshot.inn,
        legal_name=snapshot.legal_name,
        ogrn=snapshot.ogrn,
        legal_address=snapshot.legal_address,
        legal_status=snapshot.legal_status,
        okved=snapshot.okved,
        website_url=snapshot.website_url,
        website_confidence=snapshot.website_confidence,
        website_candidates=parse_candidates(snapshot.website_candidates_json),
        parsed_contacts=parse_contacts(snapshot.parsed_contacts_json),
        parsed_socials=parse_socials(snapshot.parsed_socials_json),
        parsed_signals=parse_signals(snapshot.parsed_signals_json),
        hypotheses=_parse_hypotheses(snapshot.hypotheses_json),
        ai_summary=snapshot.ai_summary,
        raw_references=parse_references(snapshot.raw_references_json),
        error_message=snapshot.error_message,
        created_at=snapshot.created_at,
    )


def _parse_hypotheses(raw: str | None) -> list[str]:
    from app.modules.enrichment.schemas import parse_json_text

    payload = parse_json_text(raw, [])
    return [str(item) for item in payload] if isinstance(payload, list) else []


def _has_clear_winner(candidates: list[LegalCompany]) -> bool:
    if len(candidates) < 2:
        return True
    ordered = sorted(candidates, key=lambda item: item.confidence, reverse=True)
    return ordered[0].confidence - ordered[1].confidence >= 0.2


def _select_best_legal(candidates: list[LegalCompany]) -> LegalCompany:
    return max(candidates, key=lambda item: item.confidence)


def _build_interaction_summary(
    legal: LegalCompany,
    resolution: WebsiteResolutionResult,
    updated_fields: list[str],
    error_message: str | None,
) -> str:
    parts = [
        f"Проведено INN-first intelligence обогащение: {legal.legal_name}, ИНН {legal.inn}.",
    ]
    if resolution.selected_url:
        parts.append(f"Вероятный сайт: {resolution.selected_url} (confidence {resolution.confidence:.0f}).")
    if updated_fields:
        parts.append(f"Обновлены поля: {', '.join(_unique(updated_fields))}.")
    if error_message:
        parts.append(f"Нужна ручная проверка: {error_message}.")
    return " ".join(parts)


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _site_to_analysis(parsed_site: ParsedCompanySite):
    from app.modules.enrichment.schemas import WebsiteAnalysis

    detected_socials = {
        "vk": parsed_site.socials.vk_links,
        "instagram": parsed_site.socials.instagram_links,
        "telegram": parsed_site.socials.telegram_links,
        "whatsapp": parsed_site.socials.whatsapp_links,
        "youtube": parsed_site.socials.youtube_links,
        "tiktok": parsed_site.socials.tiktok_links,
        "dzen": parsed_site.socials.dzen_links,
    }
    detected_maps = {
        "yandex_maps": parsed_site.socials.yandex_maps_links,
        "2gis": parsed_site.socials.two_gis_links,
    }
    return WebsiteAnalysis(
        page_title=parsed_site.page_title,
        meta_description=parsed_site.meta_description,
        raw_text_excerpt=parsed_site.text_excerpt,
        detected_socials=detected_socials,
        detected_maps=detected_maps,
        detected_contacts={
            "phones": parsed_site.contacts.phones,
            "emails": parsed_site.contacts.emails,
            "whatsapp_links": parsed_site.contacts.whatsapp_links,
            "telegram_links": parsed_site.contacts.telegram_links,
        },
        signals=parsed_site.signals,
    )
