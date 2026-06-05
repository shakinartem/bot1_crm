from __future__ import annotations

import asyncio
import math
import re
from dataclasses import asdict
from typing import Any
from urllib.parse import urlencode

from app.config import Settings, get_settings
from app.modules.legal_discovery.checko_parser import CheckoListItem, CheckoProfileData, parse_checko_list_page, parse_checko_profile_page
from app.modules.legal_discovery.okved_catalog import normalize_okved_code, resolve_okved_by_query
from app.modules.legal_discovery.schemas import (
    LegalDiscoveredCompany,
    LegalDiscoveryDirector,
    LegalDiscoveryFounder,
)
from app.modules.research.browser_backend import (
    BrowserBackend,
    BrowserBackendError,
    MockBrowserBackend,
    get_browser_backend,
)


class CheckoHtmlLegalDiscoveryProvider:
    code = "checko_html"
    title = "Checko HTML"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        browser_backend: BrowserBackend | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self.enabled = self._settings.checko_html_enabled or self._settings.legal_discovery_provider == "checko_html"
        self._browser_backend = browser_backend
        self.last_debug_info: dict[str, Any] = {}

    async def search_companies(
        self,
        query: str,
        okved_code: str | None = None,
        okved_title: str | None = None,
        city: str | None = None,
        region: str | None = None,
        limit: int = 50,
        only_main_okved: bool = True,
        only_active: bool = True,
        include_profiles: bool = True,
        concurrency: int | None = None,
    ) -> list[LegalDiscoveredCompany]:
        self.last_debug_info = {
            "requested_okved": None,
            "requested_region": region or city or self._settings.checko_html_region or None,
            "final_url": None,
            "parsed_candidates_count": 0,
            "filtered_by_region_count": 0,
            "valid_companies_count": 0,
            "invalid_candidates_count": 0,
            "skipped_not_company_count": 0,
        }
        if not self.enabled:
            return []

        resolved_code = normalize_okved_code(okved_code)
        resolved_title = okved_title
        if not resolved_code:
            guessed = resolve_okved_by_query(query)
            if not guessed:
                raise ValueError("OKVED is required. Provide a valid code like 86.23 or pick a popular category.")
            resolved_code = guessed.normalized_code
            resolved_title = guessed.title
        self.last_debug_info["requested_okved"] = resolved_code

        backend = self._browser_backend or get_browser_backend(self._settings)
        try:
            urls = self._build_list_urls(resolved_code, limit)
            list_items: list[CheckoListItem] = []
            for url in urls:
                page = await backend.fetch_page(url)
                self._ensure_page_success(page, stage="list", url=url)
                parse_debug: dict[str, Any] = {}
                try:
                    parsed_items = parse_checko_list_page(page.html or "", self._settings.checko_html_base_url, debug=parse_debug)
                except Exception as exc:
                    raise BrowserBackendError(
                        f"Checko parsing failed during list parse for {page.final_url or url}: {exc}",
                        status_code=503,
                    ) from exc
                self.last_debug_info["final_url"] = page.final_url or url
                self.last_debug_info["parsed_candidates_count"] += parse_debug.get("parsed_candidates_count", 0)
                self.last_debug_info["skipped_not_company_count"] += parse_debug.get("skipped_not_company_count", 0)
                list_items.extend(parsed_items)
                await self._maybe_delay()

            profile_map: dict[str, CheckoProfileData] = {}
            if include_profiles and self._settings.checko_html_profile_enabled:
                effective_concurrency = self._resolve_concurrency(concurrency)
                semaphore = asyncio.Semaphore(effective_concurrency)

                async def load_profile(item: CheckoListItem) -> None:
                    if not item.profile_url:
                        return
                    async with semaphore:
                        page = await backend.fetch_page(item.profile_url)
                        self._ensure_page_success(page, stage="profile", url=item.profile_url)
                        try:
                            profile_map[item.profile_url] = parse_checko_profile_page(page.html or "", self._settings.checko_html_base_url)
                        except Exception as exc:
                            raise BrowserBackendError(
                                f"Checko parsing failed during profile parse for {page.final_url or item.profile_url}: {exc}",
                                status_code=503,
                            ) from exc
                        await self._maybe_delay()

                await asyncio.gather(*(load_profile(item) for item in list_items))

            companies: list[LegalDiscoveredCompany] = []
            region_query = region or city or self._settings.checko_html_region or None
            for item in list_items:
                profile = profile_map.get(item.profile_url or "")
                merged = self._merge_item(
                    item=item,
                    profile=profile,
                    okved_code=resolved_code,
                    okved_title=resolved_title,
                    requested_region=region_query,
                )
                validation = self._validate_candidate(item, profile, include_profiles=include_profiles)
                if validation == "invalid":
                    self.last_debug_info["invalid_candidates_count"] += 1
                    continue
                if validation == "weak":
                    merged.confidence = "low"
                    if "missing_requisites" not in merged.warnings:
                        merged.warnings.append("missing_requisites")
                if region_query and not matches_region_filter(merged, region_query):
                    self.last_debug_info["filtered_by_region_count"] += 1
                    continue
                if region_query and not merged.region:
                    merged.region = region_query
                status = self._normalize_status(merged.status)
                merged.status = status
                if only_active and status == "inactive":
                    continue
                companies.append(merged)

            self.last_debug_info["valid_companies_count"] = len(companies)
            return companies[:limit]
        finally:
            if self._browser_backend is None:
                await backend.close()

    def _build_list_urls(self, okved_code: str, limit: int) -> list[str]:
        pages = max(1, min(self._settings.checko_html_max_pages, math.ceil(limit / 20)))
        results: list[str] = []
        for page in range(1, pages + 1):
            params = {"code": okved_code or "all", "page": page}
            results.append(f"{self._settings.checko_html_base_url.rstrip('/')}/company/select?{urlencode(params)}")
        return results

    def _resolve_concurrency(self, requested: int | None) -> int:
        value = requested or self._settings.checko_html_profile_concurrency or self._settings.checko_html_concurrency
        return max(1, min(value, self._settings.checko_html_max_concurrency))

    async def _maybe_delay(self) -> None:
        delay_ms = max(0, self._settings.checko_html_page_delay_ms)
        if delay_ms:
            await asyncio.sleep(delay_ms / 1000)

    def _ensure_page_success(self, page, *, stage: str, url: str) -> None:
        if page.status == "success":
            return
        detail = page.error_message or f"browser backend returned status={page.status}"
        status_code = 503
        if page.status == "failed" and "disabled" in detail.lower():
            status_code = 400
        raise BrowserBackendError(
            f"Checko HTML browser backend failed during {stage} fetch for {url}: {detail}",
            status_code=status_code,
        )

    def _merge_item(
        self,
        *,
        item: CheckoListItem,
        profile: CheckoProfileData | None,
        okved_code: str,
        okved_title: str | None,
        requested_region: str | None,
    ) -> LegalDiscoveredCompany:
        warnings = list(item.warnings)
        if not profile:
            warnings.append("missing_profile")
        confidence = "low"
        if profile and profile.inn and profile.ogrn:
            confidence = "high"
        elif profile:
            confidence = "medium"
        director = None
        if profile and profile.director_name:
            director = LegalDiscoveryDirector(
                full_name=profile.director_name,
                role=profile.director_role,
                inn=profile.director_inn,
                since_date=profile.director_since_date,
            )
        elif item.director_name:
            director = LegalDiscoveryDirector(full_name=item.director_name, role=item.director_role)
        founders = [
            LegalDiscoveryFounder(full_name=founder.full_name, role=founder.role, inn=founder.inn, share_text=founder.share_text)
            for founder in (profile.founders if profile else [])
        ]
        legal_name = (profile.legal_name if profile else None) or item.legal_name
        short_name = (profile.short_name if profile else None) or item.short_name or legal_name
        address = (profile.legal_address if profile else None) or item.address
        city = _extract_city_from_address(address)
        region = _extract_region_from_address(address)
        status = self._normalize_status((profile.status if profile else None) or item.status)
        return LegalDiscoveredCompany(
            provider=self.code,
            inn=profile.inn if profile else None,
            ogrn=profile.ogrn if profile else None,
            kpp=profile.kpp if profile else None,
            okpo=profile.okpo if profile else None,
            legal_name=legal_name,
            short_name=short_name,
            address=address,
            city=city,
            region=region,
            status=status,
            okved=(profile.okved_code if profile else None) or okved_code,
            okved_name=(profile.okved_name if profile else None) or okved_title,
            phones=profile.phones if profile else [],
            emails=profile.emails if profile else [],
            websites=profile.websites if profile else [],
            telegram_links=profile.telegram_links if profile else [],
            vk_links=profile.vk_links if profile else [],
            instagram_links=profile.instagram_links if profile else [],
            whatsapp_links=profile.whatsapp_links if profile else [],
            youtube_links=profile.youtube_links if profile else [],
            map_links=profile.map_links if profile else [],
            director=director,
            founders=founders,
            checko_profile_url=item.profile_url,
            text_excerpt=profile.text_excerpt if profile else item.raw_text,
            raw_payload={
                "list": asdict(item),
                "profile": asdict(profile) if profile else None,
                "requested_region": requested_region,
            },
            confidence=confidence,
            warnings=warnings,
        )

    def _validate_candidate(self, item: CheckoListItem, profile: CheckoProfileData | None, *, include_profiles: bool) -> str:
        if not include_profiles:
            return "valid" if item.profile_url else "invalid"
        if not item.profile_url:
            return "invalid"
        if not profile:
            return "weak" if item.legal_name and item.address else "invalid"
        legal_name = profile.legal_name or item.legal_name
        short_name = profile.short_name or item.short_name or legal_name
        has_core = bool(profile.inn and profile.ogrn and legal_name and short_name)
        if has_core:
            return "valid"
        if legal_name and short_name and item.profile_url and (profile.legal_address or item.address):
            return "weak"
        return "invalid"

    def _normalize_status(self, value: str | None) -> str | None:
        lowered = (value or "").strip().lower()
        if not lowered:
            return None
        if lowered in {"active", "registered"} or "действ" in lowered:
            return "active"
        if lowered in {"inactive"} or "ликвид" in lowered or "прекращ" in lowered:
            return "inactive"
        return None


def matches_region_filter(company: LegalDiscoveredCompany, region_query: str | None) -> bool:
    if not region_query:
        return True
    normalized_query = _normalize_region_text(region_query)
    if not normalized_query or normalized_query in {"все регионы", "все"}:
        return True
    variants = _build_region_variants(normalized_query)
    haystack_parts = [
        company.address,
        company.city,
        company.region,
        company.text_excerpt,
        (company.raw_payload or {}).get("list", {}).get("raw_text") if company.raw_payload else None,
        (company.raw_payload or {}).get("profile", {}).get("legal_address") if company.raw_payload else None,
    ]
    haystack = " ".join(_normalize_region_text(part) for part in haystack_parts if part)
    return any(variant and variant in haystack for variant in variants)


def _normalize_region_text(value: str | None) -> str:
    text = (value or "").lower().replace("ё", "е")
    text = re.sub(r"[^\w\s-]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\b(г|город|область|обл|республика|р-н|район)\b", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _build_region_variants(normalized_query: str) -> set[str]:
    variants = {normalized_query}
    for token in normalized_query.split():
        if len(token) < 3:
            continue
        variants.add(token)
        if token.endswith("ская"):
            variants.add(token[:-5])
        elif token.endswith("ский"):
            variants.add(token[:-4])
    return {item.strip() for item in variants if item.strip()}


def _extract_city_from_address(address: str | None) -> str | None:
    text = address or ""
    for pattern in (r"\bг\.\s*([А-ЯA-ZЁ][^,]+)", r"\bгород\s+([А-ЯA-ZЁ][^,]+)"):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_region_from_address(address: str | None) -> str | None:
    text = address or ""
    match = re.search(r"([А-ЯA-ZЁ][^,]+область)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None
