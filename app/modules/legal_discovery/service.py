from __future__ import annotations

from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.crm.constants import CompanyStatus, InteractionType, LeadPriority
from app.modules.crm.models import Company, ContactPoint, DecisionMaker, LeadInteraction
from app.modules.enrichment.schemas import dump_json_text
from app.modules.intelligence.models import IntelligenceSnapshot
from app.modules.legal_discovery.providers import get_legal_discovery_provider
from app.modules.legal_discovery.schemas import (
    LegalDiscoveredCompany,
    LegalDiscoveryDirector,
    LegalDiscoveryImportResult,
    LegalDiscoveryPreview,
    LegalDiscoveryPreviewItem,
)
from app.modules.research.browser_backend import BrowserBackendError


_PREVIEW_REGISTRY: dict[str, LegalDiscoveryPreview] = {}


async def run_legal_discovery_preview(
    session: AsyncSession,
    *,
    query: str,
    okved_code: str | None = None,
    okved_title: str | None = None,
    city: str | None = None,
    region: str | None = None,
    limit: int | None = None,
    only_main_okved: bool = True,
    only_active: bool = True,
    include_profiles: bool = True,
    concurrency: int | None = None,
    provider_code: str | None = None,
) -> LegalDiscoveryPreview:
    settings = get_settings()
    provider = get_legal_discovery_provider(settings)
    if provider_code and provider.code != provider_code:
        provider = get_legal_discovery_provider(settings.model_copy(update={"legal_discovery_provider": provider_code}))

    search_limit = limit or settings.legal_discovery_default_limit
    try:
        companies = await provider.search_companies(
            query=query,
            okved_code=okved_code,
            okved_title=okved_title,
            city=city,
            region=region,
            limit=search_limit,
            only_main_okved=only_main_okved,
            only_active=only_active,
            include_profiles=include_profiles,
            concurrency=concurrency,
        )
    except BrowserBackendError:
        raise
    except RuntimeError as exc:
        raise BrowserBackendError(str(exc), status_code=503) from exc
    items = [await _build_preview_item(session, company) for company in companies]

    preview = LegalDiscoveryPreview(
        preview_id=str(uuid4()),
        query=query,
        okved_code=okved_code,
        okved_title=okved_title,
        city=city,
        region=region,
        provider=provider.code,
        total_found=len(items),
        active_count=sum(1 for item in items if _is_active(item.company)),
        inactive_count=sum(1 for item in items if not _is_active(item.company)),
        with_inn_count=sum(1 for item in items if item.company.inn),
        with_ogrn_count=sum(1 for item in items if item.company.ogrn),
        with_phone_count=sum(1 for item in items if item.company.phones),
        with_email_count=sum(1 for item in items if item.company.emails),
        with_website_count=sum(1 for item in items if item.company.websites),
        with_socials_count=sum(
            1
            for item in items
            if item.company.telegram_links
            or item.company.vk_links
            or item.company.instagram_links
            or item.company.whatsapp_links
            or item.company.youtube_links
        ),
        with_director_count=sum(1 for item in items if item.company.director),
        with_founders_count=sum(1 for item in items if item.company.founders),
        new_count=sum(1 for item in items if item.status == "new"),
        duplicate_count=sum(1 for item in items if item.status == "duplicate_existing"),
        weak_count=sum(1 for item in items if item.status == "weak_data"),
        items=items,
    )
    _PREVIEW_REGISTRY[preview.preview_id] = preview
    return preview


def get_legal_discovery_preview(preview_id: str) -> LegalDiscoveryPreview | None:
    return _resolve_preview(preview_id)


async def import_legal_discovery_preview(
    session: AsyncSession,
    preview_id: str,
    mode: str = "active_new",
    *,
    include_weak: bool = False,
    run_research_after_import: bool = False,
) -> LegalDiscoveryImportResult:
    preview = _PREVIEW_REGISTRY.get(preview_id)
    if not preview:
        preview = _resolve_preview(preview_id)
    if not preview:
        raise ValueError("Preview not found")

    result = LegalDiscoveryImportResult()
    for item in preview.items:
        if item.status == "duplicate_existing":
            result.skipped_duplicates += 1
            continue
        if not _should_import_item(item, mode, include_weak):
            if item.status == "weak_data":
                result.skipped_weak += 1
            elif item.status == "inactive":
                result.skipped_inactive += 1
            continue

        duplicate = await _find_duplicate_company(session, item.company)
        if duplicate:
            result.skipped_duplicates += 1
            continue

        try:
            company = Company(
                name=item.company.short_name or item.company.legal_name or "Unknown company",
                legal_name=item.company.legal_name,
                inn=item.company.inn,
                ogrn=item.company.ogrn,
                address=item.company.address,
                city=item.company.city,
                region=item.company.region,
                source=f"legal_discovery:{preview.provider}",
                status=CompanyStatus.RESEARCH_NEEDED.value,
                priority=_compute_priority(item.company),
            )
            session.add(company)
            await session.flush()
            await _sync_company_contacts(session, company, item.company)
            await _sync_company_decision_maker(session, company, item.company.director)
            await _save_discovery_note(session, company.id, preview.provider, item.company)
            await _save_discovery_snapshot(session, company.id, item.company)
            result.added_count += 1
            result.added_company_ids.append(company.id)
        except Exception as exc:  # pragma: no cover - defensive accounting
            result.errors_count += 1
            result.errors.append(str(exc))

    await session.commit()
    if run_research_after_import and result.added_company_ids:
        from app.modules.research_queue.service import create_research_jobs_for_companies

        await create_research_jobs_for_companies(session, result.added_company_ids)
    return result


def preview_callback_token(preview_id: str) -> str:
    return preview_id.split("-", 1)[0]


def _resolve_preview(preview_ref: str) -> LegalDiscoveryPreview | None:
    preview = _PREVIEW_REGISTRY.get(preview_ref)
    if preview:
        return preview
    matches = [item for key, item in _PREVIEW_REGISTRY.items() if key.startswith(preview_ref)]
    if len(matches) == 1:
        return matches[0]
    return None


async def _build_preview_item(session: AsyncSession, company: LegalDiscoveredCompany) -> LegalDiscoveryPreviewItem:
    warnings = list(company.warnings)
    if not company.inn or not company.ogrn or not company.legal_name:
        warnings.append("missing_requisites")
        return LegalDiscoveryPreviewItem(status="weak_data", company=company, warnings=warnings)

    duplicate = await _find_duplicate_company(session, company)
    if duplicate:
        return LegalDiscoveryPreviewItem(
            status="duplicate_existing",
            company=company,
            duplicate_company_id=duplicate.id,
            duplicate_reason=_build_duplicate_reason(duplicate, company),
            warnings=warnings,
        )
    if not _is_active(company):
        return LegalDiscoveryPreviewItem(status="inactive", company=company, warnings=warnings)
    if company.confidence == "low" or warnings:
        return LegalDiscoveryPreviewItem(status="weak_data", company=company, warnings=warnings)
    return LegalDiscoveryPreviewItem(status="new", company=company, warnings=warnings)


async def _find_duplicate_company(session: AsyncSession, company: LegalDiscoveredCompany) -> Company | None:
    conditions = []
    if company.inn:
        conditions.append(Company.inn == company.inn)
    if company.ogrn:
        conditions.append(Company.ogrn == company.ogrn)
    if company.legal_name and company.city:
        conditions.append(and_(Company.legal_name == company.legal_name, Company.city == company.city))
    if not conditions:
        return None
    result = await session.execute(select(Company).where(or_(*conditions)).limit(1))
    return result.scalar_one_or_none()


async def _sync_company_contacts(session: AsyncSession, company: Company, discovered: LegalDiscoveredCompany) -> None:
    existing: set[tuple[str, str]] = set()
    contact_map = {
        "phone": discovered.phones,
        "email": discovered.emails,
        "website": discovered.websites,
        "telegram": discovered.telegram_links,
        "vk": discovered.vk_links,
        "instagram": discovered.instagram_links,
        "whatsapp": discovered.whatsapp_links,
        "youtube": discovered.youtube_links,
        "map_url": discovered.map_links,
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
                    label="checko_html",
                    is_primary=False,
                )
            )
            existing.add(key)
    if discovered.websites and not company.website:
        company.website = discovered.websites[0]
    if discovered.phones and not company.phone:
        company.phone = discovered.phones[0]


async def _sync_company_decision_maker(
    session: AsyncSession,
    company: Company,
    director: LegalDiscoveryDirector | None,
) -> None:
    if not director or not director.full_name:
        return
    note_parts = [part for part in [f"INN: {director.inn}" if director.inn else None, f"since: {director.since_date}" if director.since_date else None] if part]
    session.add(
        DecisionMaker(
            company_id=company.id,
            full_name=director.full_name,
            role=director.role,
            source="checko_html",
            is_primary=True,
            notes=" | ".join(note_parts) if note_parts else None,
        )
    )


async def _save_discovery_note(session: AsyncSession, company_id: int, provider: str, discovered: LegalDiscoveredCompany) -> None:
    summary = (
        f"Legal discovery import via {provider}: "
        f"{discovered.legal_name or discovered.short_name or 'company'}; "
        f"INN {discovered.inn or '-'}; OGRN {discovered.ogrn or '-'}."
    )
    result = await session.execute(
        select(LeadInteraction).where(
            LeadInteraction.company_id == company_id,
            LeadInteraction.type == InteractionType.NOTE.value,
            LeadInteraction.summary == summary,
        )
    )
    if result.scalar_one_or_none():
        return
    session.add(
        LeadInteraction(
            company_id=company_id,
            type=InteractionType.NOTE.value,
            summary=summary,
            created_by="legal_discovery",
        )
    )


async def _save_discovery_snapshot(session: AsyncSession, company_id: int, discovered: LegalDiscoveredCompany) -> None:
    session.add(
        IntelligenceSnapshot(
            company_id=company_id,
            status="legal_discovery_import",
            inn=discovered.inn,
            legal_name=discovered.legal_name,
            ogrn=discovered.ogrn,
            legal_address=discovered.address,
            legal_status=discovered.status,
            okved=discovered.okved,
            website_url=discovered.websites[0] if discovered.websites else None,
            website_confidence=100.0 if discovered.websites else None,
            website_candidates_json=dump_json_text([]),
            parsed_contacts_json=dump_json_text(
                {
                    "phones": discovered.phones,
                    "emails": discovered.emails,
                    "addresses": [discovered.address] if discovered.address else [],
                }
            ),
            parsed_socials_json=dump_json_text(
                {
                    "vk_links": discovered.vk_links,
                    "instagram_links": discovered.instagram_links,
                    "telegram_links": discovered.telegram_links,
                    "whatsapp_links": discovered.whatsapp_links,
                    "youtube_links": discovered.youtube_links,
                    "yandex_maps_links": discovered.map_links,
                }
            ),
            parsed_signals_json=dump_json_text({}),
            hypotheses_json=dump_json_text([f"founders:{len(discovered.founders)}"]),
            ai_summary=dump_json_text(discovered.raw_payload or {}),
            raw_references_json=dump_json_text([]),
        )
    )


def _build_duplicate_reason(existing: Company, discovered: LegalDiscoveredCompany) -> str:
    if existing.inn and discovered.inn and existing.inn == discovered.inn:
        return "same_inn"
    if existing.ogrn and discovered.ogrn and existing.ogrn == discovered.ogrn:
        return "same_ogrn"
    return "same_legal_name_city"


def _is_active(company: LegalDiscoveredCompany) -> bool:
    return (company.status or "").lower() in {"active", "действует", "действующее", "registered"}


def _compute_priority(company: LegalDiscoveredCompany) -> str:
    return LeadPriority.MEDIUM.value if company.phones or company.emails or company.websites else LeadPriority.LOW.value


def _should_import_item(item: LegalDiscoveryPreviewItem, mode: str, include_weak: bool) -> bool:
    if mode == "active_new":
        if item.status == "weak_data" and not include_weak:
            return False
        return item.status in {"new", "weak_data"} and _is_active(item.company)
    if mode == "all_new":
        return item.status in {"new", "weak_data", "inactive"} and (include_weak or item.status != "weak_data")
    if mode == "new_with_websites":
        return bool(item.company.websites) and item.status in {"new", "weak_data"} and (include_weak or item.status != "weak_data")
    if mode == "new_with_phone_or_website":
        return bool(item.company.phones or item.company.websites) and item.status in {"new", "weak_data"} and (include_weak or item.status != "weak_data")
    return False
