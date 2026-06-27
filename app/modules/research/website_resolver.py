from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.crm.constants import ContactType
from app.modules.crm.models import Company, ContactPoint
from app.modules.crm.service import get_company
from app.modules.insights.schemas import CompanyInsightSnapshotCreate
from app.modules.insights.service import create_company_insight_snapshot
from app.modules.intelligence.providers import get_search_provider
from app.modules.intelligence.schemas import SearchResult
from app.modules.research.http_fetcher import fetch_url


WEBSITE_DENYLIST_DOMAINS = {
    "rmsp-pp.nalog.ru",
    "rmsp-np.nalog.ru",
    "pb.nalog.ru",
    "nalog.ru",
    "nalog.gov.ru",
    "checko.ru",
    "rusprofile.ru",
    "list-org.com",
    "sbis.ru",
    "spark-interfax.ru",
    "chrome.google.com",
    "chromewebstore.google.com",
    "yandex.ru",
    "yandex.com",
    "2gis.ru",
    "zoon.ru",
    "prodoctorov.ru",
    "yell.ru",
    "flamp.ru",
    "orgpage.ru",
    "spravker.ru",
    "vk.com",
    "t.me",
}

WEBSITE_DENYLIST_HOST_PATH_PREFIXES: dict[str, tuple[str, ...]] = {
    "google.com": ("/chrome", "/webstore", "/maps"),
    "yandex.ru": ("/maps",),
    "yandex.com": ("/maps",),
}
WEBSITE_DENYLIST_PATH_PREFIXES = (
    "/company/",
    "/firm/",
    "/card/",
    "/org/",
    "/organization/",
    "/business/",
    "/details/",
    "/info/",
    "/profile/",
    "/ organizations/",
)


class WebsiteHealthResult(BaseModel):
    url: str
    final_url: str | None = None
    is_alive: bool
    status_code: int | None = None
    content_type: str | None = None
    error: str | None = None
    checked_at: datetime
    needs_manual_review: bool = False


class WebsiteSearchOutcome(BaseModel):
    company_id: int
    status: str
    selected_url: str | None = None
    selected_confidence: str | None = None
    candidate_urls: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    diagnostics: dict[str, int | str] = Field(default_factory=dict)


def normalize_website_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{host}{path}"


def _extract_host(url: str) -> str:
    return urlparse(normalize_website_url(url)).netloc.lower().replace("www.", "")


def is_denied_website_url(url: str) -> bool:
    parsed = urlparse(normalize_website_url(url))
    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.lower()
    if any(host == domain or host.endswith(f".{domain}") for domain in WEBSITE_DENYLIST_DOMAINS):
        return True
    for domain, prefixes in WEBSITE_DENYLIST_HOST_PATH_PREFIXES.items():
        if host == domain or host.endswith(f".{domain}"):
            if any(path.startswith(prefix) for prefix in prefixes):
                return True
    for prefix in WEBSITE_DENYLIST_PATH_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def is_probable_official_website(url: str, company_context: dict[str, Any]) -> bool:
    if is_denied_website_url(url):
        return False
    host = _extract_host(url)
    name_tokens = " ".join(
        [
            company_context.get("name") or "",
            company_context.get("legal_name") or "",
            company_context.get("short_name") or "",
        ]
    ).lower()
    city = (company_context.get("city") or "").lower()
    phone_tail = "".join(ch for ch in (company_context.get("phone") or "") if ch.isdigit())[-4:]
    score = 0
    if phone_tail and phone_tail in (company_context.get("snippet") or ""):
        score += 1
    if city and city in (company_context.get("snippet") or "").lower():
        score += 1
    if any(token and len(token) > 3 and token in host for token in name_tokens.replace('"', " ").split()):
        score += 2
    if company_context.get("inn") and company_context["inn"] in (company_context.get("snippet") or ""):
        score += 2
    return score >= 2


async def check_website_alive(url: str) -> WebsiteHealthResult:
    normalized = normalize_website_url(url)
    if not normalized:
        return WebsiteHealthResult(url=url, is_alive=False, error="empty_url", checked_at=datetime.utcnow())
    result = await fetch_url(
        normalized,
        timeout=get_settings().research_request_timeout,
        max_chars=4_000,
    )
    status_code = result.http_status
    allowed = status_code in {200, 301, 302, 403}
    is_alive = result.status in {"success", "non_html"} and allowed
    if status_code == 403:
        return WebsiteHealthResult(
            url=normalized,
            final_url=result.final_url,
            is_alive=True,
            status_code=status_code,
            content_type=None,
            error=result.error_message,
            checked_at=datetime.utcnow(),
            needs_manual_review=True,
        )
    return WebsiteHealthResult(
        url=normalized,
        final_url=result.final_url,
        is_alive=is_alive,
        status_code=status_code,
        content_type="text/html" if result.html else None,
        error=result.error_message,
        checked_at=datetime.utcnow(),
    )


async def run_website_search_for_company(
    session: AsyncSession,
    company_id: int,
    force: bool = False,
) -> WebsiteSearchOutcome:
    company = await get_company(session, company_id)
    if not company:
        raise ValueError("Company not found")
    context = _build_company_context(company)
    reasons: list[str] = []
    references: list[str] = []

    existing_denied = bool(company.website and is_denied_website_url(company.website))
    if company.website and not existing_denied and not force:
        health = await check_website_alive(company.website)
        if health.is_alive and not is_denied_website_url(company.website):
            outcome = WebsiteSearchOutcome(
                company_id=company.id,
                status="kept_existing",
                selected_url=normalize_website_url(company.website),
                selected_confidence="high",
                reasons=["Existing website is alive and not denied."],
            )
            await _save_website_insight(session, company, outcome, {"existing_health": health.model_dump(mode="json")})
            return outcome
        reasons.append("Existing website needs replacement.")
    elif existing_denied:
        reasons.append("Existing website is denied and will not be kept.")
        company.website = None

    provider = get_search_provider()
    search_results: list[SearchResult] = []
    seen_urls: set[str] = set()
    for query in _build_queries(company):
        for item in await provider.search(query, limit=get_settings().yandex_search_limit):
            normalized = normalize_website_url(item.url)
            if not normalized or normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            if is_denied_website_url(normalized):
                references.append(normalized)
                continue
            search_results.append(item)

    candidates: list[tuple[str, WebsiteHealthResult, bool]] = []
    rejected_count = 0
    for item in search_results:
        normalized = normalize_website_url(item.url)
        if is_denied_website_url(normalized):
            rejected_count += 1
            continue
        health = await check_website_alive(normalized)
        if not health.is_alive or health.status_code >= 400:
            rejected_count += 1
            continue
        if health.is_alive and _is_parked_or_stub(normalized, health):
            rejected_count += 1
            continue
        candidate_context = {
            **context,
            "snippet": f"{item.title or ''} {item.snippet or ''}",
        }
        official = is_probable_official_website(normalized, candidate_context)
        if official or health.is_alive:
            candidates.append((normalized, health, official))

    selected_url: str | None = None
    selected_confidence: str | None = None
    status = "not_found"
    if candidates:
        official_candidates = [item for item in candidates if item[2]]
        if official_candidates:
            selected_url = official_candidates[0][0]
            selected_confidence = "high"
            status = "resolved"
        else:
            selected_url = candidates[0][0]
            selected_confidence = "medium"
            status = "partial"

    if selected_url and selected_confidence == "high":
        company.website = selected_url
        await _add_contact_if_missing(session, company.id, ContactType.WEBSITE.value, selected_url)

    diagnostics = {
        "website_candidates_count": len(candidates),
        "website_rejected_count": rejected_count,
        "website_confidence": selected_confidence or "none",
    }
    outcome = WebsiteSearchOutcome(
        company_id=company.id,
        status=status,
        selected_url=selected_url,
        selected_confidence=selected_confidence,
        candidate_urls=[item[0] for item in candidates],
        references=references,
        reasons=reasons,
        diagnostics=diagnostics,
    )
    await _save_website_insight(
        session,
        company,
        outcome,
        {
            "queries": _build_queries(company),
            "candidates": [item[0] for item in candidates],
            "references": references,
            "diagnostics": diagnostics,
        },
    )
    company.website_confidence = selected_confidence or company.website_confidence
    session.add(company)
    await session.commit()
    return outcome


def _build_queries(company: Company) -> list[str]:
    short_name = (company.name or company.legal_name or "").strip()
    legal_name = (company.legal_name or "").strip()
    queries: list[str] = []

    if company.inn:
        queries.extend([
            f"{company.inn} {short_name} сайт",
            f"{company.inn} {legal_name} сайт" if legal_name and legal_name != short_name else None,
            f"{company.inn} сайт",
            f"{company.inn} официальный сайт",
        ])
    if not company.inn and short_name:
        if company.city:
            queries.append(f"{short_name} {company.city} сайт")
        if legal_name and legal_name != short_name and company.city:
            queries.append(f"{legal_name} {company.city} сайт")
        if company.address:
            queries.append(f"{short_name} {company.address} сайт")
        if company.phone:
            queries.append(f"{company.phone} сайт")
        if short_name:
            queries.append(f'"{short_name}" официальный сайт')
    if company.ogrn:
        queries.append(f"{company.ogrn} сайт")

    seen: set[str] = set()
    unique_queries: list[str] = []
    for q in queries:
        if not q:
            continue
        qn = q.strip().lower()
        if qn not in seen:
            seen.add(qn)
            unique_queries.append(q)
    return unique_queries


def _build_company_context(company: Company) -> dict[str, Any]:
    return {
        "name": company.name,
        "legal_name": company.legal_name,
        "short_name": company.name,
        "inn": company.inn,
        "ogrn": company.ogrn,
        "city": company.city,
        "phone": company.phone,
    }


def _is_parked_or_stub(url: str, health: WebsiteHealthResult) -> bool:
    if not health.html:
        return False
    lowered = health.html.lower()
    stub_markers = [
        "domain for sale",
        "buy this domain",
        "parked domain",
        "this domain is",
        "under construction",
        "coming soon",
        "website is under construction",
    ]
    return any(marker in lowered for marker in stub_markers)


async def _add_contact_if_missing(session: AsyncSession, company_id: int, contact_type: str, value: str) -> None:
    result = await session.execute(
        select(ContactPoint).where(
            ContactPoint.company_id == company_id,
            ContactPoint.type == contact_type,
            ContactPoint.value == value,
        )
    )
    if result.scalar_one_or_none():
        return
    session.add(
        ContactPoint(
            company_id=company_id,
            type=contact_type,
            value=value,
            label="website_research",
            is_primary=False,
        )
    )


async def _save_website_insight(
    session: AsyncSession,
    company: Company,
    outcome: WebsiteSearchOutcome,
    extra_payload: dict[str, Any],
) -> None:
    payload = {"outcome": outcome.model_dump(mode="json"), **extra_payload}
    await create_company_insight_snapshot(
        session,
        CompanyInsightSnapshotCreate(
            company_id=company.id,
            insight_type="website_research",
            title="Website research",
            status=outcome.status,
            payload=payload,
            summary=outcome.selected_url or "Website not found",
            source="website_resolver",
            version="v1",
        ),
    )


__all__ = [
    "WEBSITE_DENYLIST_DOMAINS",
    "WebsiteHealthResult",
    "WebsiteSearchOutcome",
    "check_website_alive",
    "is_denied_website_url",
    "is_probable_official_website",
    "normalize_website_url",
    "run_website_search_for_company",
]
