from __future__ import annotations

from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.crm.constants import CompanyStatus, InteractionType, LeadPriority
from app.modules.crm.models import Company, LeadInteraction
from app.modules.legal_discovery.providers import get_legal_discovery_provider
from app.modules.legal_discovery.schemas import (
    LegalDiscoveredCompany,
    LegalDiscoveryImportResult,
    LegalDiscoveryPreview,
    LegalDiscoveryPreviewItem,
)


_PREVIEW_REGISTRY: dict[str, LegalDiscoveryPreview] = {}


async def run_legal_discovery_preview(
    session: AsyncSession,
    *,
    query: str,
    city: str | None = None,
    region: str | None = None,
    limit: int | None = None,
    provider_code: str | None = None,
) -> LegalDiscoveryPreview:
    settings = get_settings()
    provider = get_legal_discovery_provider(settings)
    if provider_code and provider.code != provider_code:
        provider = get_legal_discovery_provider(settings.model_copy(update={"legal_discovery_provider": provider_code}))

    search_limit = limit or settings.legal_discovery_default_limit
    companies = await provider.search_companies(
        query=query,
        city=city,
        region=region,
        limit=search_limit,
    )
    items: list[LegalDiscoveryPreviewItem] = []
    for company in companies:
        items.append(await _build_preview_item(session, company))

    preview = LegalDiscoveryPreview(
        preview_id=str(uuid4()),
        query=query,
        city=city,
        region=region,
        provider=provider.code,
        total_found=len(items),
        active_count=sum(1 for item in items if _is_active(item.company)),
        inactive_count=sum(1 for item in items if not _is_active(item.company)),
        new_count=sum(1 for item in items if item.status == "new"),
        duplicate_count=sum(1 for item in items if item.status == "duplicate_existing"),
        weak_count=sum(1 for item in items if item.status == "weak_data"),
        items=items,
    )
    _PREVIEW_REGISTRY[preview.preview_id] = preview
    return preview


def get_legal_discovery_preview(preview_id: str) -> LegalDiscoveryPreview | None:
    return _PREVIEW_REGISTRY.get(preview_id)


async def import_legal_discovery_preview(
    session: AsyncSession,
    preview_id: str,
    mode: str = "active_new",
) -> LegalDiscoveryImportResult:
    preview = _PREVIEW_REGISTRY.get(preview_id)
    if not preview:
        raise ValueError("Preview not found")

    result = LegalDiscoveryImportResult()
    for item in preview.items:
        if item.status == "duplicate_existing":
            result.skipped_duplicates += 1
            continue
        if mode == "active_new":
            if item.status == "weak_data":
                result.skipped_weak += 1
                continue
            if not _is_active(item.company):
                result.skipped_inactive += 1
                continue
            if item.status != "new":
                continue
        elif mode == "all_new":
            if item.status not in {"new", "weak_data", "inactive"}:
                continue

        duplicate = await _find_duplicate_company(session, item.company)
        if duplicate:
            result.skipped_duplicates += 1
            continue

        try:
            company = Company(
                name=item.company.short_name or item.company.legal_name,
                legal_name=item.company.legal_name,
                inn=item.company.inn,
                ogrn=item.company.ogrn,
                address=item.company.address,
                city=item.company.city,
                region=item.company.region,
                source=f"legal_discovery:{preview.provider}",
                status=CompanyStatus.RESEARCH_NEEDED.value,
                priority=LeadPriority.MEDIUM.value if _is_active(item.company) else LeadPriority.LOW.value,
            )
            session.add(company)
            await session.flush()
            session.add(
                LeadInteraction(
                    company_id=company.id,
                    type=InteractionType.NOTE.value,
                    summary=f"Компания найдена через legal discovery: {preview.provider}",
                    created_by="legal_discovery",
                )
            )
            result.added_count += 1
            result.added_company_ids.append(company.id)
        except Exception as exc:  # pragma: no cover - defensive accounting
            result.errors_count += 1
            result.errors.append(str(exc))
    await session.commit()
    return result


async def _build_preview_item(
    session: AsyncSession,
    company: LegalDiscoveredCompany,
) -> LegalDiscoveryPreviewItem:
    warnings = list(company.warnings)
    if not company.inn or not company.ogrn or not company.legal_name:
        warnings.append("Неполные реквизиты")
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


async def _find_duplicate_company(
    session: AsyncSession,
    company: LegalDiscoveredCompany,
) -> Company | None:
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


def _build_duplicate_reason(existing: Company, discovered: LegalDiscoveredCompany) -> str:
    if existing.inn and discovered.inn and existing.inn == discovered.inn:
        return "same_inn"
    if existing.ogrn and discovered.ogrn and existing.ogrn == discovered.ogrn:
        return "same_ogrn"
    return "same_legal_name_city"


def _is_active(company: LegalDiscoveredCompany) -> bool:
    return (company.status or "").lower() in {"active", "действующее", "registered"}
