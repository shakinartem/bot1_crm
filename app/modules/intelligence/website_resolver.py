from __future__ import annotations

from collections import OrderedDict

from app.config import get_settings
from app.modules.enrichment.fetcher import fetch_website
from app.modules.intelligence.matcher import is_directory_domain, score_website_candidate
from app.modules.intelligence.providers.base import WebSearchProvider
from app.modules.intelligence.schemas import LegalCompany, SearchResult, WebsiteCandidate, WebsiteResolutionResult


async def resolve_official_website(
    legal_company: LegalCompany,
    search_provider: WebSearchProvider,
    city: str | None = None,
    known_phone: str | None = None,
) -> WebsiteResolutionResult:
    queries = _build_queries(legal_company, city)
    collected: OrderedDict[str, SearchResult] = OrderedDict()
    references: list[SearchResult] = []
    limit = get_settings().intelligence_search_limit

    for query in queries:
        for item in await search_provider.search(query, limit=limit):
            if item.url not in collected:
                collected[item.url] = item
            if is_directory_domain(item.url):
                references.append(item)

    candidates: list[WebsiteCandidate] = []
    for result in collected.values():
        fetch = await fetch_website(result.url, timeout=get_settings().intelligence_request_timeout)
        excerpt = (fetch.html or "")[:2000] if fetch.html else None
        confidence, reasons, warnings, is_official = score_website_candidate(
            legal_company,
            result.url,
            result.title,
            result.snippet,
            excerpt,
            city=city,
            known_phone=known_phone,
        )
        if fetch.error_message:
            warnings.append(fetch.error_message)
        candidates.append(
            WebsiteCandidate(
                url=result.url,
                title=result.title,
                snippet=result.snippet,
                confidence=confidence,
                reasons=reasons,
                warnings=warnings,
                is_official_candidate=is_official,
                fetched_excerpt=excerpt,
            )
        )

    candidates.sort(key=lambda item: item.confidence, reverse=True)
    selected = next((item for item in candidates if item.is_official_candidate), None)
    if not selected and candidates:
        selected = candidates[0]

    reasons = list(selected.reasons) if selected else []
    warnings = list(selected.warnings) if selected else []
    if selected and not selected.is_official_candidate:
        warnings.append("официальный сайт не подтвержден, нужен ручной контроль")

    return WebsiteResolutionResult(
        selected_url=selected.url if selected and selected.confidence > 0 else None,
        confidence=selected.confidence if selected else 0.0,
        reasons=reasons,
        warnings=warnings,
        candidates=candidates,
        references=references,
    )


def _build_queries(legal_company: LegalCompany, city: str | None) -> list[str]:
    queries = [
        legal_company.inn,
        f"ИНН {legal_company.inn}",
        f"{legal_company.inn} официальный сайт",
        f"{legal_company.legal_name} официальный сайт",
    ]
    if city:
        queries.append(f"{legal_company.legal_name} {city}")
    if legal_company.short_name:
        queries.append(f"{legal_company.short_name} стоматология {city or legal_company.city or ''}".strip())
    return [item for item in queries if item.strip()]
