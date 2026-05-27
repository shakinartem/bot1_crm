from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.ai.providers import get_ai_provider
from app.modules.crm.models import Company, ContactPoint, LeadInteraction
from app.modules.crm.service import get_company
from app.modules.enrichment.analyzer import analyze_website_html, build_enrichment_hypotheses
from app.modules.enrichment.fetcher import fetch_website
from app.modules.enrichment.models import EnrichmentSnapshot
from app.modules.enrichment.prompts import build_enrichment_summary_prompt, build_fallback_enrichment_summary
from app.modules.enrichment.schemas import (
    Bot2EnrichmentContextRead,
    DetectedContactsRead,
    DetectedLinksRead,
    EnrichmentResultRead,
    EnrichmentSnapshotRead,
    WebsiteAnalysis,
    WebsiteSignalRead,
    dump_json_text,
    parse_json_text,
)


async def enrich_company_website(
    session: AsyncSession,
    company_id: int,
    website_url: str | None = None,
    use_ai: bool = True,
) -> EnrichmentResultRead:
    company = await get_company(session, company_id)
    if not company:
        raise ValueError("Company not found")

    resolved_url = _resolve_company_website(company, website_url)
    if not resolved_url:
        snapshot = EnrichmentSnapshot(
            company_id=company_id,
            website_url=None,
            status="manual",
            error_message="Website URL is missing",
            hypotheses_json=dump_json_text([]),
            signals_json=dump_json_text(WebsiteSignalRead().model_dump()),
            detected_links_json=dump_json_text(DetectedLinksRead().model_dump()),
            detected_socials_json=dump_json_text({}),
            detected_maps_json=dump_json_text({}),
            detected_contacts_json=dump_json_text(DetectedContactsRead().model_dump()),
        )
        session.add(snapshot)
        await session.commit()
        await session.refresh(snapshot)
        return _snapshot_to_result(snapshot)

    fetch_result = await fetch_website(resolved_url)
    analysis = WebsiteAnalysis()
    hypotheses: list[str] = []
    ai_summary: str | None = None
    status = fetch_result.status

    if fetch_result.html:
        analysis = analyze_website_html(fetch_result.html, fetch_result.final_url or fetch_result.url)
        hypotheses = build_enrichment_hypotheses(analysis)
        if use_ai:
            ai_summary = await _generate_enrichment_summary(company, analysis, hypotheses)
        if not ai_summary:
            ai_summary = build_fallback_enrichment_summary(_company_prompt_context(company), analysis, hypotheses)
    else:
        ai_summary = None

    snapshot = EnrichmentSnapshot(
        company_id=company_id,
        website_url=fetch_result.final_url or fetch_result.url,
        status=status,
        fetched_at=datetime.utcnow(),
        http_status=fetch_result.http_status,
        page_title=analysis.page_title,
        meta_description=analysis.meta_description,
        detected_links_json=dump_json_text(analysis.detected_links.model_dump()),
        detected_socials_json=dump_json_text(analysis.detected_socials),
        detected_maps_json=dump_json_text(analysis.detected_maps),
        detected_contacts_json=dump_json_text(analysis.detected_contacts.model_dump()),
        signals_json=dump_json_text(analysis.signals.model_dump()),
        hypotheses_json=dump_json_text(hypotheses),
        ai_summary=ai_summary,
        raw_text_excerpt=analysis.raw_text_excerpt,
        error_message=fetch_result.error_message,
    )
    session.add(snapshot)

    if website_url and not (company.website or "").strip() and status in {"success", "partial"}:
        company.website = fetch_result.final_url or fetch_result.url
        session.add(company)

    note_summary = "Проведен research сайта / digital-присутствия"
    if fetch_result.error_message:
        note_summary = f"{note_summary}. Ошибка: {fetch_result.error_message}"
    session.add(
        LeadInteraction(
            company_id=company_id,
            type="note",
            summary=note_summary,
            created_by="enrichment_service",
        )
    )

    await session.commit()
    await session.refresh(snapshot)
    return _snapshot_to_result(snapshot)


async def get_latest_enrichment(session: AsyncSession, company_id: int) -> EnrichmentSnapshotRead | None:
    result = await session.execute(
        select(EnrichmentSnapshot)
        .where(EnrichmentSnapshot.company_id == company_id)
        .order_by(EnrichmentSnapshot.created_at.desc(), EnrichmentSnapshot.id.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    return _snapshot_to_read(snapshot) if snapshot else None


async def get_enrichment_history(
    session: AsyncSession,
    company_id: int,
    limit: int = 10,
) -> list[EnrichmentSnapshotRead]:
    result = await session.execute(
        select(EnrichmentSnapshot)
        .where(EnrichmentSnapshot.company_id == company_id)
        .order_by(EnrichmentSnapshot.created_at.desc(), EnrichmentSnapshot.id.desc())
        .limit(limit)
    )
    return [_snapshot_to_read(item) for item in result.scalars().all()]


async def get_enrichment_snapshot(
    session: AsyncSession,
    company_id: int,
    snapshot_id: int,
) -> EnrichmentSnapshotRead | None:
    result = await session.execute(
        select(EnrichmentSnapshot).where(
            EnrichmentSnapshot.company_id == company_id,
            EnrichmentSnapshot.id == snapshot_id,
        )
    )
    snapshot = result.scalar_one_or_none()
    return _snapshot_to_read(snapshot) if snapshot else None


async def build_enrichment_context_for_company(
    session: AsyncSession,
    company_id: int,
) -> Bot2EnrichmentContextRead | None:
    latest = await get_latest_enrichment(session, company_id)
    if not latest:
        return None
    return Bot2EnrichmentContextRead(
        latest_snapshot_at=latest.created_at,
        website_url=latest.website_url,
        status=latest.status,
        signals=latest.signals,
        hypotheses=latest.hypotheses,
        ai_summary=latest.ai_summary,
        detected_socials=latest.detected_socials,
        detected_maps=latest.detected_maps,
    )


def _snapshot_to_result(snapshot: EnrichmentSnapshot) -> EnrichmentResultRead:
    return EnrichmentResultRead(
        company_id=snapshot.company_id,
        website_url=snapshot.website_url,
        status=snapshot.status,
        http_status=snapshot.http_status,
        page_title=snapshot.page_title,
        meta_description=snapshot.meta_description,
        detected_links=_parse_links(snapshot.detected_links_json),
        detected_socials=parse_json_text(snapshot.detected_socials_json, {}),
        detected_maps=parse_json_text(snapshot.detected_maps_json, {}),
        detected_contacts=_parse_contacts(snapshot.detected_contacts_json),
        signals=_parse_signals(snapshot.signals_json),
        hypotheses=parse_json_text(snapshot.hypotheses_json, []),
        ai_summary=snapshot.ai_summary,
        raw_text_excerpt=snapshot.raw_text_excerpt,
        error_message=snapshot.error_message,
        snapshot_id=snapshot.id,
        fetched_at=snapshot.fetched_at,
    )


def _snapshot_to_read(snapshot: EnrichmentSnapshot) -> EnrichmentSnapshotRead:
    return EnrichmentSnapshotRead(
        id=snapshot.id,
        company_id=snapshot.company_id,
        website_url=snapshot.website_url,
        status=snapshot.status,
        fetched_at=snapshot.fetched_at,
        http_status=snapshot.http_status,
        page_title=snapshot.page_title,
        meta_description=snapshot.meta_description,
        detected_links=_parse_links(snapshot.detected_links_json),
        detected_socials=parse_json_text(snapshot.detected_socials_json, {}),
        detected_maps=parse_json_text(snapshot.detected_maps_json, {}),
        detected_contacts=_parse_contacts(snapshot.detected_contacts_json),
        signals=_parse_signals(snapshot.signals_json),
        hypotheses=parse_json_text(snapshot.hypotheses_json, []),
        ai_summary=snapshot.ai_summary,
        raw_text_excerpt=snapshot.raw_text_excerpt,
        error_message=snapshot.error_message,
        created_at=snapshot.created_at,
    )


async def _generate_enrichment_summary(
    company: Company,
    analysis: WebsiteAnalysis,
    hypotheses: list[str],
) -> str | None:
    if get_settings().ai_provider.lower() == "fallback":
        return build_fallback_enrichment_summary(_company_prompt_context(company), analysis, hypotheses)
    prompt = build_enrichment_summary_prompt(_company_prompt_context(company), analysis, hypotheses)
    try:
        result = await get_ai_provider().generate(prompt)
    except Exception:
        result = None
    return (result or "").strip() or build_fallback_enrichment_summary(_company_prompt_context(company), analysis, hypotheses)


def _resolve_company_website(company: Company, website_url: str | None) -> str | None:
    if website_url and website_url.strip():
        return website_url.strip()
    if company.website and company.website.strip():
        return company.website.strip()
    for contact in company.contacts:
        if contact.type == "website" and contact.value.strip():
            return contact.value.strip()
    return None


def _company_prompt_context(company: Company) -> dict:
    return {
        "name": company.name,
        "city": company.city,
        "website": company.website,
        "source": company.source,
        "status": company.status,
    }


def _parse_links(raw: str | None) -> DetectedLinksRead:
    return DetectedLinksRead.model_validate(parse_json_text(raw, {}))


def _parse_contacts(raw: str | None) -> DetectedContactsRead:
    return DetectedContactsRead.model_validate(parse_json_text(raw, {}))


def _parse_signals(raw: str | None) -> WebsiteSignalRead:
    return WebsiteSignalRead.model_validate(parse_json_text(raw, {}))
