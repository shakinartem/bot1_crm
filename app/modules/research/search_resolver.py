from __future__ import annotations

from urllib.parse import urlparse

from app.config import get_settings
from app.modules.crm.models import Company
from app.modules.intelligence.providers import get_search_provider
from app.modules.intelligence.schemas import LegalCompany
from app.modules.research.http_fetcher import normalize_url
from app.modules.research.schemas import WebsiteCandidate, WebsiteResolutionResult


AGGREGATOR_DOMAINS = {
    "rusprofile.ru",
    "list-org.com",
    "zachestnyibiznes.ru",
    "checko.ru",
    "sbis.ru",
    "spark-interfax.ru",
    "kartoteka.ru",
    "nalog.gov.ru",
    "egrul.nalog.ru",
    "2gis.ru",
    "yandex.ru",
    "zoon.ru",
    "prodoctorov.ru",
    "yell.ru",
}

DENTAL_KEYWORDS = (
    "стомат",
    "dental",
    "брекет",
    "элайнер",
    "имплант",
    "ортодонт",
)


async def resolve_company_website(
    company: Company,
    legal_company: LegalCompany | None = None,
) -> WebsiteResolutionResult:
    if company.website:
        candidate = WebsiteCandidate(
            url=normalize_url(company.website),
            confidence=70.0,
            reasons=["Website already present in CRM"],
            is_official_candidate=True,
        )
        return WebsiteResolutionResult(
            selected_url=candidate.url,
            confidence=candidate.confidence,
            reasons=candidate.reasons,
            candidates=[candidate],
        )

    if not legal_company:
        return WebsiteResolutionResult(warnings=["Нужны ИНН или юрданные для поиска сайта"])

    provider = get_search_provider()
    queries = _build_queries(company, legal_company)
    search_limit = get_settings().intelligence_search_limit
    collected: dict[str, tuple[object, str | None]] = {}
    references = []
    for query in queries:
        results = await provider.search(query, limit=search_limit)
        for result in results:
            normalized = normalize_url(result.url)
            if _is_aggregator(normalized):
                references.append(result)
                continue
            if normalized not in collected:
                collected[normalized] = (result, query)

    candidates: list[WebsiteCandidate] = []
    for url, (result, query) in collected.items():
        confidence, reasons, warnings, is_official = _score_candidate(company, legal_company, url, result)
        reasons.append(f"Query: {query}")
        candidates.append(
            WebsiteCandidate(
                url=url,
                title=result.title,
                snippet=result.snippet,
                confidence=confidence,
                reasons=reasons,
                warnings=warnings,
                is_official_candidate=is_official,
            )
        )

    candidates.sort(key=lambda item: item.confidence, reverse=True)
    selected = candidates[0] if candidates else None
    if selected and selected.confidence < 60:
        return WebsiteResolutionResult(
            confidence=selected.confidence,
            warnings=["Low confidence website match, manual review recommended"],
            candidates=candidates,
            references=references,
        )

    return WebsiteResolutionResult(
        selected_url=selected.url if selected else None,
        confidence=selected.confidence if selected else 0.0,
        reasons=list(selected.reasons) if selected else [],
        warnings=list(selected.warnings) if selected else [],
        candidates=candidates,
        references=references,
    )


def _build_queries(company: Company, legal_company: LegalCompany) -> list[str]:
    queries = [
        legal_company.inn,
        f"ИНН {legal_company.inn}",
        f"{legal_company.inn} официальный сайт",
        f"{legal_company.legal_name} официальный сайт",
        f"{legal_company.legal_name} {company.city or legal_company.city or ''}".strip(),
    ]
    if legal_company.short_name:
        queries.append(f"{legal_company.short_name} стоматология {company.city or legal_company.city or ''}".strip())
    return [item for item in queries if item]


def _score_candidate(
    company: Company,
    legal_company: LegalCompany,
    url: str,
    result: object,
) -> tuple[float, list[str], list[str], bool]:
    title = (getattr(result, "title", "") or "").lower()
    snippet = (getattr(result, "snippet", "") or "").lower()
    text = " ".join([title, snippet, url.lower()])
    confidence = 0.0
    reasons: list[str] = []
    warnings: list[str] = []

    if legal_company.inn and legal_company.inn in text:
        confidence += 50
        reasons.append("INN appears in search result")
    names = [company.name, legal_company.legal_name, legal_company.short_name or ""]
    if any(name and name.lower().replace('"', "")[:12] in text for name in names):
        confidence += 25
        reasons.append("Company name matches candidate")
    if company.city and company.city.lower() in text:
        confidence += 20
        reasons.append("City matches candidate")
    if company.phone and company.phone[-4:] and company.phone[-4:] in text:
        confidence += 15
        reasons.append("Known phone tail matches candidate")
    if any(keyword in text for keyword in DENTAL_KEYWORDS):
        confidence += 10
        reasons.append("Dental keywords detected")
    if _is_aggregator(url):
        confidence -= 30
        warnings.append("Aggregator domain")
    host = urlparse(url).netloc.lower()
    if host and host.startswith(("vk.", "instagram.", "t.me", "wa.me")):
        confidence -= 50
        warnings.append("Clearly not an official website")

    return confidence, reasons, warnings, confidence >= 60


def _is_aggregator(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(domain in host for domain in AGGREGATOR_DOMAINS)
