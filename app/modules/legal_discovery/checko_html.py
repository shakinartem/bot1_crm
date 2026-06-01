from __future__ import annotations

import asyncio
import math
from dataclasses import asdict
from urllib.parse import urlencode

from app.config import Settings, get_settings
from app.modules.legal_discovery.checko_parser import parse_checko_list_page, parse_checko_profile_page
from app.modules.legal_discovery.okved_catalog import normalize_okved_code, resolve_okved_by_query
from app.modules.legal_discovery.schemas import (
    LegalDiscoveredCompany,
    LegalDiscoveryDirector,
    LegalDiscoveryFounder,
)
from app.modules.research.browser_backend import BrowserBackend, MockBrowserBackend, get_browser_backend


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

        backend = self._browser_backend or get_browser_backend(self._settings)
        try:
            urls = self._build_list_urls(resolved_code, limit)
            list_items = []
            for url in urls:
                page = await backend.fetch_page(url)
                list_items.extend(parse_checko_list_page(page.html or "", self._settings.checko_html_base_url))
                await self._maybe_delay()

            list_items = list_items[:limit]
            profile_map = {}
            if include_profiles and self._settings.checko_html_profile_enabled:
                effective_concurrency = self._resolve_concurrency(concurrency)
                semaphore = asyncio.Semaphore(effective_concurrency)

                async def load_profile(item: LegalDiscoveredCompany | Any) -> None:
                    if not item.profile_url:
                        return
                    async with semaphore:
                        page = await backend.fetch_page(item.profile_url)
                        profile_map[item.profile_url] = parse_checko_profile_page(page.html or "", self._settings.checko_html_base_url)
                        await self._maybe_delay()

                await asyncio.gather(*(load_profile(item) for item in list_items), return_exceptions=True)

            companies: list[LegalDiscoveredCompany] = []
            for item in list_items:
                profile = profile_map.get(item.profile_url)
                status = self._normalize_status(profile.status if profile and profile.status else item.status)
                if only_active and status and status != "active":
                    continue
                companies.append(
                    self._merge_item(
                        item=item,
                        profile=profile,
                        city=city,
                        region=region or self._settings.checko_html_region or None,
                        okved_code=resolved_code,
                        okved_title=resolved_title,
                    )
                )
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

    def _merge_item(
        self,
        *,
        item,
        profile,
        city: str | None,
        region: str | None,
        okved_code: str,
        okved_title: str | None,
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
        return LegalDiscoveredCompany(
            provider=self.code,
            inn=profile.inn if profile else None,
            ogrn=profile.ogrn if profile else None,
            kpp=profile.kpp if profile else None,
            okpo=profile.okpo if profile else None,
            legal_name=(profile.legal_name if profile else None) or item.legal_name,
            short_name=(profile.short_name if profile else None) or item.short_name,
            address=(profile.legal_address if profile else None) or item.address,
            city=city,
            region=region,
            status=self._normalize_status((profile.status if profile else None) or item.status),
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
            text_excerpt=profile.text_excerpt if profile else None,
            raw_payload={"list": asdict(item), "profile": asdict(profile) if profile else None},
            confidence=confidence,
            warnings=warnings,
        )

    def _normalize_status(self, value: str | None) -> str | None:
        lowered = (value or "").strip().lower()
        if not lowered:
            return None
        if lowered in {"active", "registered"} or "действ" in lowered:
            return "active"
        if lowered in {"inactive"} or "ликвид" in lowered or "прекращ" in lowered:
            return "inactive"
        return value
