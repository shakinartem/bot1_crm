from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.constants import ContactType
from app.modules.crm.models import Company, ContactPoint
from app.modules.crm.service import get_company
from app.modules.insights.schemas import CompanyInsightSnapshotCreate
from app.modules.insights.service import create_company_insight_snapshot, get_latest_company_insight, safe_load_payload
from app.modules.intelligence.providers import get_search_provider
from app.modules.intelligence.schemas import SearchResult
from app.modules.research.website_resolver import normalize_website_url
from app.modules.research.schemas import MapsScore


def build_yandex_maps_queries(company: Company) -> list[str]:
    """
    Build search queries for Yandex Maps discovery.

    Priority order (with address):
    1. {short_name} {address}
    2. {short_name} {city} {address}
    3. {legal_name} {address}
    4. {phone} {address}
    5. {inn} {short_name} Яндекс Карты (fallback)

    Without address:
    6. {short_name} {city} Яндекс Карты
    7. {legal_name} {city} Яндекс Карты
    8. {phone} Яндекс Карты
    """
    queries: list[str] = []
    short_name = (company.name or company.legal_name or "").strip()
    legal_name = (company.legal_name or "").strip()
    address = (company.address or "").strip()
    city = (company.city or "").strip()
    phone = (company.phone or "").strip()

    # --- With address (highest priority) ---
    if address:
        if short_name:
            # 1. Название + адрес
            queries.append(f"{short_name} {address}")
        if legal_name and legal_name != short_name:
            # 2. Юридическое название + адрес
            queries.append(f"{legal_name} {address}")
        if city and short_name:
            # 3. Название + город + адрес
            queries.append(f"{short_name} {city} {address}")
        if phone:
            # 4. Телефон + адрес
            queries.append(f"{phone} {address}")

    # --- Fallback without address ---
    if not address:
        if short_name and city:
            queries.append(f"{short_name} {city} Яндекс Карты")
        if legal_name and legal_name != short_name and city:
            queries.append(f"{legal_name} {city} Яндекс Карты")
        if phone:
            queries.append(f"{phone} Яндекс Карты")

    # --- INN fallback ---
    if company.inn and short_name:
        queries.append(f"{company.inn} {short_name} Яндекс Карты")

    # --- Deduplicate while preserving order ---
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        qn = q.strip().lower()
        if qn not in seen:
            seen.add(qn)
            unique.append(q)

    return unique


def score_yandex_maps_card(company: Company, maps_result: SearchResult | dict[str, Any]) -> MapsScore:
    """
    Score a Yandex Maps card against a company profile.

    Stricter scoring: verified only if ≥2 strong signals match (name + address/phone/website/city).
    If only city matches, status is 'mismatch', not 'verified'.
    """
    payload = maps_result.model_dump() if isinstance(maps_result, BaseModel) else dict(maps_result or {})
    url = _normalize_map_url(payload.get("url"))
    title = _combine_text(payload.get("title"), payload.get("snippet"))
    score = 0
    reasons: list[str] = []
    warnings: list[str] = []
    matched_fields: list[str] = []

    name_tokens = _company_name_tokens(company)
    if name_tokens and _text_matches(title, name_tokens):
        score += 25
        matched_fields.append("name")
        reasons.append("Название совпадает с карточкой")

    if company.address and _text_matches(title, [company.address.lower()[:30]]):
        score += 25
        matched_fields.append("address")
        reasons.append("Адрес совпадает")

    if company.city and _text_matches(title, [company.city.lower()]):
        score += 10
        matched_fields.append("city")
        reasons.append("Город совпадает")

    phone_tail = "".join(ch for ch in (company.phone or "") if ch.isdigit())[-4:]
    if phone_tail and phone_tail in title:
        score += 15
        matched_fields.append("phone")
        reasons.append("Телефон найден в тексте")

    if company.website and _text_matches(title, [normalize_website_url(company.website)]):
        score += 10
        matched_fields.append("website")
        reasons.append("Сайт совпадает")

    if company.inn and company.inn in title:
        score += 10
        matched_fields.append("inn")
        reasons.append("ИНН найден в тексте")

    rating = _coerce_float(payload.get("rating"))
    reviews_count = _coerce_int(payload.get("reviews_count"))
    photos_present = bool(payload.get("photos_present")) if payload.get("photos_present") is not None else None
    website_present = bool(payload.get("website_present")) if payload.get("website_present") is not None else None
    phone_present = bool(payload.get("phone_present")) if payload.get("phone_present") is not None else None
    address_present = bool(payload.get("address_present")) if payload.get("address_present") is not None else None

    if rating is not None:
        score += 10
        reasons.append(f"Рейтинг: {rating:.1f}")
    if reviews_count:
        score += 5
        reasons.append(f"Отзывов: {reviews_count}")
    if photos_present:
        score += 5

    # Strong signal penalty: if only city matched → low score
    if matched_fields == ["city"]:
        score = max(0, score - 20)
        warnings.append("Совпал только город — низкая уверенность")

    # No name match → penalty
    if "name" not in matched_fields and company.name:
        score -= 15
        warnings.append("Название не подтвердилось")

    # No address match when company has address → penalty
    if "address" not in matched_fields and company.address:
        score -= 10
        warnings.append("Адрес не подтвердился")

    # Status determination: stricter rules
    strong_signals = {"name", "address", "phone", "website", "inn"}
    strong_matched = [f for f in matched_fields if f in strong_signals]

    if len(strong_matched) >= 2 and score >= 60 and _is_yandex_maps_url(url):
        status = "verified"
    elif score >= 45 and _is_yandex_maps_url(url):
        status = "candidate"
    elif matched_fields:
        status = "mismatch"
    else:
        status = "not_found"

    if not _is_yandex_maps_url(url):
        warnings.append("URL не похож на Яндекс Карты")
        if status in ("verified", "candidate"):
            status = "mismatch"

    return MapsScore(
        total_score=max(0, min(100, score)),
        status=status,
        reasons=reasons[:5],
        warnings=warnings[:5],
        matched_fields=matched_fields[:6],
        yandex_maps_url=url if _is_yandex_maps_url(url) else None,
        rating=rating,
        reviews_count=reviews_count,
        photos_present=photos_present,
        website_present=website_present,
        phone_present=phone_present,
        address_present=address_present,
    )


async def run_yandex_maps_research_for_company(
    session: AsyncSession,
    company_id: int,
    force: bool = False,
) -> MapsScore:
    company = await get_company(session, company_id)
    if not company:
        raise ValueError("Company not found")

    if not force:
        snapshot = await get_latest_company_insight(session, company_id, "maps_research")
        payload = safe_load_payload(snapshot)
        if payload:
            try:
                return MapsScore.model_validate(payload.get("score") or payload)
            except Exception:
                pass

    provider = get_search_provider()
    queries = build_yandex_maps_queries(company)
    seen_urls: set[str] = set()
    candidates: list[SearchResult] = []
    for query in queries:
        results = await provider.search(query, limit=10)
        for result in results:
            normalized = _normalize_map_url(result.url)
            if not normalized or normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            if not _is_yandex_maps_url(normalized):
                continue
            candidates.append(result)

    scored = [score_yandex_maps_card(company, candidate) for candidate in candidates]
    scored.sort(key=lambda item: item.total_score, reverse=True)
    selected = scored[0] if scored else MapsScore(total_score=0, status="not_found")

    if selected.status in {"verified", "candidate"} and selected.yandex_maps_url:
        company.maps_url = selected.yandex_maps_url
        company.maps_rating = selected.rating
        company.maps_reviews = selected.reviews_count
        company.maps_confidence = selected.status
        company.maps_score = selected.total_score
        session.add(
            ContactPoint(
                company_id=company.id,
                type=ContactType.MAP_URL.value,
                value=selected.yandex_maps_url,
                label="maps_research",
                is_primary=True,
            )
        )
        session.add(company)
        await session.commit()

    await create_company_insight_snapshot(
        session,
        CompanyInsightSnapshotCreate(
            company_id=company.id,
            insight_type="maps_research",
            title="Yandex Maps research",
            status=selected.status,
            payload={
                "score": selected.model_dump(mode="json"),
                "queries": queries,
                "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
            },
            summary=selected.yandex_maps_url or "Maps not found",
            source="maps_research",
            version="v2",
        ),
    )

    if selected.status == "verified":
        await _recalculate_digital_score(session, company)

    return selected


def _combine_text(*parts: Any) -> str:
    return " ".join(part for part in parts if isinstance(part, str) and part.strip()).lower()


def _text_matches(text: str, needles: Iterable[str]) -> bool:
    return any(needle and needle in text for needle in needles)


def _company_name_tokens(company: Company) -> list[str]:
    tokens = [company.name or "", company.legal_name or ""]
    return [token.lower() for token in tokens if token.strip()]


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _normalize_map_url(url: str | None) -> str | None:
    value = (url or "").strip()
    if not value:
        return None
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{host}{path}"


async def _recalculate_digital_score(session: AsyncSession, company: Company) -> None:
    website_score = company.website_score or 0
    maps_score = company.maps_score or 0
    digital_score = max(0, min(100, int(website_score * 0.6 + maps_score * 0.4)))
    digital_grade = "A" if digital_score >= 80 else "B" if digital_score >= 60 else "C" if digital_score >= 40 else "D"
    company.digital_score = digital_score
    company.digital_grade = digital_grade
    session.add(company)


def _is_yandex_maps_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    return "yandex" in host and "map" in (parsed.path.lower() + host)


__all__ = [
    "build_yandex_maps_queries",
    "recalculate_digital_score",
    "run_yandex_maps_research_for_company",
    "score_yandex_maps_card",
]
