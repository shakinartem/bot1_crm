from __future__ import annotations

from app.modules.crm.models import Company
from app.modules.intelligence.schemas import LegalCompany
from app.modules.research.schemas import WebsiteCandidate, WebsiteResolutionResult
from app.modules.research.website_resolver import (
    is_denied_website_url,
    normalize_website_url,
)


async def resolve_company_website(
    company: Company,
    legal_company: LegalCompany | None = None,
) -> WebsiteResolutionResult:
    del legal_company
    if company.website and not is_denied_website_url(company.website):
        normalized = normalize_website_url(company.website)
        candidate = WebsiteCandidate(
            url=normalized,
            confidence=90.0,
            reasons=["Website already present in CRM and not denied."],
            is_official_candidate=True,
        )
        return WebsiteResolutionResult(
            selected_url=normalized,
            confidence=90.0,
            reasons=candidate.reasons,
            candidates=[candidate],
        )
    return WebsiteResolutionResult(
        selected_url=None,
        confidence=0.0,
        warnings=["Use run_website_search_for_company for active search-based resolution."],
    )
