from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.crm.constants import ContactType, InteractionType
from app.modules.crm.models import Company, ContactPoint, LeadInteraction
from app.modules.crm.service import get_company
from app.modules.enrichment.schemas import dump_json_text
from app.modules.intelligence.models import IntelligenceSnapshot
from app.modules.intelligence.schemas import IntelligenceSnapshotRead, LegalCompany, parse_candidates, parse_contacts, parse_references, parse_signals, parse_socials
from app.modules.intelligence.service import _get_or_find_single_legal
from app.modules.research.browser_fetcher import detect_blocked_content
from app.modules.research.schemas import ResearchContextRead, ResearchResult, get_fetch_backend
from app.modules.research.search_resolver import resolve_company_website
from app.modules.research.site_parser import build_site_hypotheses, parse_company_site


async def run_company_research(
    session: AsyncSession,
    company_id: int,
    force: bool = False,
) -> ResearchResult:
    company = await get_company(session, company_id)
    if not company:
        raise ValueError("Company not found")
    if not company.inn and not company.legal_name:
        return ResearchResult(
            company_id=company_id,
            status="needs_manual_review",
            error_message="Company needs legal identification before research",
        )
    if not force:
        latest = await get_latest_research(session, company_id)
        if latest and latest.status in {"success", "blocked"}:
            return ResearchResult(
                company_id=company_id,
                status=latest.status,
                website_url=latest.website_url,
                website_confidence=latest.website_confidence,
                page_title=None,
                hypotheses=latest.hypotheses,
                ai_summary=latest.ai_summary,
                snapshot_id=latest.id,
            )

    legal = await _get_or_find_single_legal(company)
    if not legal:
        return await _persist_research_outcome(
            session,
            company,
            legal=None,
            status="needs_manual_review",
            error_message="Legal identity is not confirmed",
        )

    resolution = await resolve_company_website(company, legal)
    if not resolution.selected_url:
        return await _persist_research_outcome(
            session,
            company,
            legal=legal,
            status="needs_manual_review",
            website_confidence=resolution.confidence,
            error_message="Official website was not resolved",
        )

    fetch = await get_fetch_backend(get_settings())(resolution.selected_url)
    blocked_reason = detect_blocked_content(fetch.html)
    if fetch.status == "blocked" or blocked_reason:
        return await _persist_research_outcome(
            session,
            company,
            legal=legal,
            status="blocked",
            website_url=resolution.selected_url,
            website_confidence=resolution.confidence,
            blocked_reason=blocked_reason or fetch.blocked_reason,
            error_message=fetch.error_message or "Blocked by target page",
        )
    if fetch.status != "success" or not fetch.html:
        return await _persist_research_outcome(
            session,
            company,
            legal=legal,
            status="failed",
            website_url=resolution.selected_url,
            website_confidence=resolution.confidence,
            error_message=fetch.error_message or "Website fetch failed",
        )

    parsed = parse_company_site(fetch.html, fetch.final_url or resolution.selected_url)
    hypotheses = build_site_hypotheses(parsed)
    updated_fields = await _apply_parsed_data(session, company, resolution.selected_url, resolution.confidence, parsed)
    return await _persist_research_outcome(
        session,
        company,
        legal=legal,
        status="success" if resolution.confidence >= 60 else "partial",
        website_url=resolution.selected_url,
        website_confidence=resolution.confidence,
        parsed=parsed,
        hypotheses=hypotheses,
        updated_fields=updated_fields,
        references=[item.model_dump() for item in resolution.references],
        candidates=[item.model_dump() for item in resolution.candidates],
    )


async def get_latest_research(session: AsyncSession, company_id: int) -> IntelligenceSnapshotRead | None:
    from app.modules.intelligence.service import get_latest_intelligence

    return await get_latest_intelligence(session, company_id)


async def get_research_history(
    session: AsyncSession,
    company_id: int,
    limit: int = 10,
) -> list[IntelligenceSnapshotRead]:
    from app.modules.intelligence.service import get_intelligence_history

    return await get_intelligence_history(session, company_id, limit=limit)


async def build_research_context_for_company(
    session: AsyncSession,
    company_id: int,
) -> ResearchContextRead | None:
    latest = await get_latest_research(session, company_id)
    if not latest:
        return None
    return ResearchContextRead(
        latest_snapshot_at=latest.created_at,
        status=latest.status,
        website_url=latest.website_url,
        website_confidence=latest.website_confidence,
        parsed_contacts=latest.parsed_contacts,
        parsed_socials=latest.parsed_socials,
        parsed_signals=latest.parsed_signals,
        hypotheses=latest.hypotheses,
        ai_summary=latest.ai_summary,
    )


async def _apply_parsed_data(
    session: AsyncSession,
    company: Company,
    website_url: str,
    confidence: float,
    parsed,
) -> list[str]:
    updated_fields: list[str] = []
    if website_url and (not company.website or confidence >= 60) and company.website != website_url:
        company.website = website_url
        updated_fields.append("website")
    if not company.phone and parsed.contacts.phones:
        company.phone = parsed.contacts.phones[0]
        updated_fields.append("phone")
    if not company.vk_url and parsed.socials.vk_links:
        company.vk_url = parsed.socials.vk_links[0]
        updated_fields.append("vk_url")
    if not company.instagram_url and parsed.socials.instagram_links:
        company.instagram_url = parsed.socials.instagram_links[0]
        updated_fields.append("instagram_url")
    if not company.telegram_url and parsed.socials.telegram_links:
        company.telegram_url = parsed.socials.telegram_links[0]
        updated_fields.append("telegram_url")
    if not company.maps_url and (parsed.socials.yandex_maps_links or parsed.socials.two_gis_links):
        company.maps_url = (parsed.socials.yandex_maps_links or parsed.socials.two_gis_links)[0]
        updated_fields.append("maps_url")

    existing = {(contact.type, contact.value.strip().lower()) for contact in company.contacts}
    contact_map = {
        ContactType.PHONE.value: parsed.contacts.phones,
        ContactType.EMAIL.value: parsed.contacts.emails,
        ContactType.WEBSITE.value: [website_url] if website_url else [],
        ContactType.WHATSAPP.value: parsed.socials.whatsapp_links,
        ContactType.TELEGRAM.value: parsed.socials.telegram_links,
        ContactType.VK.value: parsed.socials.vk_links,
        ContactType.INSTAGRAM.value: parsed.socials.instagram_links,
    }
    for contact_type, values in contact_map.items():
        for value in values:
            clean = (value or "").strip()
            key = (contact_type, clean.lower())
            if not clean or key in existing:
                continue
            session.add(
                ContactPoint(
                    company_id=company.id,
                    type=contact_type,
                    value=clean,
                    label="research",
                    is_primary=False,
                )
            )
            existing.add(key)
    return updated_fields


async def _persist_research_outcome(
    session: AsyncSession,
    company: Company,
    *,
    legal: LegalCompany | None,
    status: str,
    website_url: str | None = None,
    website_confidence: float | None = None,
    parsed=None,
    hypotheses: list[str] | None = None,
    updated_fields: list[str] | None = None,
    blocked_reason: str | None = None,
    error_message: str | None = None,
    references: list[dict] | None = None,
    candidates: list[dict] | None = None,
) -> ResearchResult:
    snapshot = IntelligenceSnapshot(
        company_id=company.id,
        status=status,
        inn=company.inn if company.inn else (legal.inn if legal else None),
        legal_name=company.legal_name if company.legal_name else (legal.legal_name if legal else None),
        ogrn=company.ogrn if company.ogrn else (legal.ogrn if legal else None),
        legal_address=company.address if company.address else (legal.address if legal else None),
        legal_status=legal.status if legal else None,
        okved=legal.okved if legal else None,
        website_url=website_url,
        website_confidence=website_confidence,
        website_candidates_json=dump_json_text(candidates or []),
        parsed_contacts_json=dump_json_text(parsed.contacts.model_dump() if parsed else {}),
        parsed_socials_json=dump_json_text(parsed.socials.model_dump() if parsed else {}),
        parsed_signals_json=dump_json_text(parsed.signals.model_dump() if parsed else {}),
        hypotheses_json=dump_json_text(hypotheses or []),
        raw_references_json=dump_json_text(references or []),
        error_message=blocked_reason or error_message,
    )
    session.add(company)
    session.add(snapshot)
    session.add(
        LeadInteraction(
            company_id=company.id,
            type=InteractionType.NOTE.value,
            summary="Проведен research сайта/публичных данных",
            created_by="research_service",
        )
    )
    await session.commit()
    await session.refresh(snapshot)
    return ResearchResult(
        company_id=company.id,
        status=status,
        website_url=website_url,
        website_confidence=website_confidence,
        page_title=parsed.page_title if parsed else None,
        parsed_site=parsed,
        hypotheses=hypotheses or [],
        error_message=error_message,
        blocked_reason=blocked_reason,
        snapshot_id=snapshot.id,
        updated_fields=updated_fields or [],
    )
