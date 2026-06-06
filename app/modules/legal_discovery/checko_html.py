from __future__ import annotations

import asyncio
import json
import math
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from app.config import Settings, get_settings
from app.modules.legal_discovery.checko_parser import (
    CheckoListItem,
    CheckoParseDiagnostics,
    CheckoProfileData,
    parse_checko_list_page_with_diagnostics,
    parse_checko_profile_page,
)
from app.modules.legal_discovery.okved_catalog import normalize_okved_code, resolve_okved_by_query
from app.modules.legal_discovery.schemas import (
    LegalDiscoveredCompany,
    LegalDiscoveryDirector,
    LegalDiscoveryFounder,
)
from app.modules.research.browser_backend import (
    BrowserBackend,
    BrowserBackendError,
    get_browser_backend,
)


CAPTCHA_MARKERS = ("captcha", "капча", "проверка", "robot", "робот")
ACCESS_DENIED_MARKERS = ("access denied", "доступ ограничен", "forbidden", "denied")


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
        region_query = region or city or self._settings.checko_html_region or None
        self.last_debug_info = {
            "requested_okved": None,
            "requested_region": region_query,
            "requested_url": None,
            "final_url": None,
            "title": None,
            "status": None,
            "html_chars": 0,
            "text_chars": 0,
            "company_links_found": 0,
            "raw_candidates_found": 0,
            "parsed_candidates_count": 0,
            "parser_candidates_count": 0,
            "candidates_before_region": 0,
            "profile_fetch_success": 0,
            "profile_fetch_failed": 0,
            "filtered_by_region_count": 0,
            "valid_companies_count": 0,
            "invalid_candidates_count": 0,
            "skipped_not_company_count": 0,
            "weak_data_count": 0,
            "contains_organisations_text": False,
            "contains_captcha_words": False,
            "contains_access_denied_words": False,
            "debug_snapshot_path": None,
            "before_region_html_path": None,
            "after_region_html_path": None,
            "region_modal_opened": False,
            "region_search_filled": False,
            "region_option_clicked": None,
            "region_apply_clicked": False,
            "region_filter_applied": False,
            "region_filter_error": None,
            "sample_company_links": [],
            "sample_rejected": [],
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
            for page_index, url in enumerate(urls, start=1):
                page = await backend.fetch_checko_list_page(url, region_query=region_query)
                self._record_page_debug(page=page, requested_url=url)
                self._ensure_page_success(page, stage="list", url=url)

                try:
                    parsed_items, parse_diagnostics = parse_checko_list_page_with_diagnostics(
                        page.html or "",
                        self._settings.checko_html_base_url,
                    )
                except Exception as exc:
                    raise BrowserBackendError(
                        f"Checko parsing failed during list parse for {page.final_url or url}: {exc}",
                        status_code=503,
                    ) from exc

                self._record_parse_diagnostics(parse_diagnostics)
                snapshot_path = self._save_debug_snapshot(
                    page=page,
                    requested_url=url,
                    okved_code=resolved_code,
                    region_query=region_query,
                    page_index=page_index,
                    diagnostics=parse_diagnostics,
                )
                if snapshot_path:
                    self.last_debug_info["debug_snapshot_path"] = snapshot_path
                list_items.extend(parsed_items)
                await self._maybe_delay()

            profile_map: dict[str, CheckoProfileData] = {}
            profile_failed_urls: set[str] = set()
            if include_profiles and self._settings.checko_html_profile_enabled:
                effective_concurrency = self._resolve_concurrency(concurrency)
                semaphore = asyncio.Semaphore(effective_concurrency)

                async def load_profile(item: CheckoListItem) -> None:
                    if not item.profile_url:
                        return
                    async with semaphore:
                        page = await backend.fetch_page(item.profile_url)
                        if page.status != "success":
                            profile_failed_urls.add(item.profile_url)
                            item.warnings.append("profile_fetch_failed")
                            self.last_debug_info["profile_fetch_failed"] += 1
                            return
                        try:
                            profile_map[item.profile_url] = parse_checko_profile_page(page.html or "", self._settings.checko_html_base_url)
                        except Exception as exc:
                            profile_failed_urls.add(item.profile_url)
                            item.warnings.append("profile_parse_failed")
                            self.last_debug_info["profile_fetch_failed"] += 1
                            return
                        self.last_debug_info["profile_fetch_success"] += 1
                        await self._maybe_delay()

                await asyncio.gather(*(load_profile(item) for item in list_items))

            companies: list[LegalDiscoveredCompany] = []
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
                self.last_debug_info["candidates_before_region"] += 1
                if validation == "weak":
                    merged.confidence = "low"
                    self.last_debug_info["weak_data_count"] += 1
                    if "missing_requisites" not in merged.warnings:
                        merged.warnings.append("missing_requisites")
                if item.profile_url in profile_failed_urls:
                    merged.status = None
                    merged.confidence = "low"
                    if "profile_fetch_failed" not in merged.warnings:
                        merged.warnings.append("profile_fetch_failed")
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

    def _record_page_debug(self, *, page, requested_url: str) -> None:
        html_text = page.html or ""
        body_text = page.text or ""
        title = page.title or ""
        combined_text = " ".join(part for part in [title, body_text, html_text[:3000]] if part)
        self.last_debug_info.update(
            {
                "requested_url": requested_url,
                "final_url": page.final_url or requested_url,
                "title": title,
                "status": page.status,
                "html_chars": len(html_text),
                "text_chars": len(body_text),
                "contains_organisations_text": "организац" in _normalize_region_text(combined_text),
                "contains_captcha_words": _contains_any_marker(combined_text, CAPTCHA_MARKERS),
                "contains_access_denied_words": _contains_any_marker(combined_text, ACCESS_DENIED_MARKERS),
            }
        )
        for key in (
            "region_modal_opened",
            "region_search_filled",
            "region_option_clicked",
            "region_apply_clicked",
            "region_filter_applied",
            "region_filter_error",
        ):
            if key in getattr(page, "debug_data", {}):
                self.last_debug_info[key] = page.debug_data.get(key)

    def _record_parse_diagnostics(self, diagnostics: CheckoParseDiagnostics) -> None:
        debug = diagnostics.to_debug_dict()
        self.last_debug_info["company_links_found"] += int(debug.get("company_links_found", 0) or 0)
        self.last_debug_info["raw_candidates_found"] += int(debug.get("raw_candidates_found", 0) or 0)
        self.last_debug_info["parsed_candidates_count"] += int(debug.get("parsed_candidates_count", 0) or 0)
        self.last_debug_info["parser_candidates_count"] += int(debug.get("parser_candidates_count", 0) or 0)
        self.last_debug_info["skipped_not_company_count"] += int(debug.get("skipped_not_company_count", 0) or 0)
        if debug.get("sample_company_links") and not self.last_debug_info.get("sample_company_links"):
            self.last_debug_info["sample_company_links"] = list(debug["sample_company_links"])
        if debug.get("sample_rejected") and not self.last_debug_info.get("sample_rejected"):
            self.last_debug_info["sample_rejected"] = list(debug["sample_rejected"])

    def _save_debug_snapshot(
        self,
        *,
        page,
        requested_url: str,
        okved_code: str,
        region_query: str | None,
        page_index: int,
        diagnostics: CheckoParseDiagnostics,
    ) -> str | None:
        if not self._settings.checko_html_debug:
            return None
        debug_dir = self._settings.checko_html_debug_dir
        debug_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        region_slug = _slugify_region(region_query)
        page_suffix = f"_p{page_index}" if page_index > 1 else ""
        stem = f"checko_list_{timestamp}_{okved_code}_{region_slug}{page_suffix}"
        html_path = debug_dir / f"{stem}.html"
        text_path = debug_dir / f"{stem}.txt"
        meta_path = debug_dir / f"{stem}.json"
        html_path.write_text(page.html or "", encoding="utf-8")
        text_path.write_text(page.text or "", encoding="utf-8")
        before_region_html_path = None
        after_region_html_path = None
        before_region_html = getattr(page, "debug_data", {}).get("before_region_html")
        after_region_html = getattr(page, "debug_data", {}).get("after_region_html")
        if before_region_html is not None:
            before_path = debug_dir / f"{stem}_before_region.html"
            before_path.write_text(before_region_html, encoding="utf-8")
            before_region_html_path = str(before_path)
            self.last_debug_info["before_region_html_path"] = before_region_html_path
        if after_region_html is not None:
            after_path = debug_dir / f"{stem}_after_region.html"
            after_path.write_text(after_region_html, encoding="utf-8")
            after_region_html_path = str(after_path)
            self.last_debug_info["after_region_html_path"] = after_region_html_path
        metadata = {
            "requested_url": requested_url,
            "final_url": page.final_url or requested_url,
            "title": page.title or "",
            "status": page.status,
            "html_chars": len(page.html or ""),
            "text_chars": len(page.text or ""),
            "okved_code": okved_code,
            "region_query": region_query,
            "contains_company_links": diagnostics.company_links_found,
            "contains_organisations_text": self.last_debug_info.get("contains_organisations_text", False),
            "contains_captcha_words": self.last_debug_info.get("contains_captcha_words", False),
            "contains_access_denied_words": self.last_debug_info.get("contains_access_denied_words", False),
            "parser_candidates_count": diagnostics.valid_items,
            "candidates_before_region": self.last_debug_info.get("candidates_before_region", 0),
            "profile_fetch_success": self.last_debug_info.get("profile_fetch_success", 0),
            "profile_fetch_failed": self.last_debug_info.get("profile_fetch_failed", 0),
            "valid_companies_count": self.last_debug_info.get("valid_companies_count", 0),
            "skipped_not_company": diagnostics.to_debug_dict()["skipped_not_company_count"],
            "filtered_by_region": self.last_debug_info.get("filtered_by_region_count", 0),
            "weak_data": self.last_debug_info.get("weak_data_count", 0),
            "region_modal_opened": self.last_debug_info.get("region_modal_opened", False),
            "region_search_filled": self.last_debug_info.get("region_search_filled", False),
            "region_option_clicked": self.last_debug_info.get("region_option_clicked"),
            "region_apply_clicked": self.last_debug_info.get("region_apply_clicked", False),
            "region_filter_applied": self.last_debug_info.get("region_filter_applied", False),
            "region_filter_error": self.last_debug_info.get("region_filter_error"),
            "before_region_html_path": before_region_html_path,
            "after_region_html_path": after_region_html_path,
            "sample_company_links": diagnostics.sample_company_links,
            "sample_rejected": diagnostics.sample_rejected,
        }
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(meta_path)

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
        has_list_level_core = bool(item.profile_url and item.legal_name and (item.raw_text or item.address))
        if not has_list_level_core:
            return "invalid"
        if not include_profiles:
            return "valid"
        if not profile:
            return "weak"
        legal_name = profile.legal_name or item.legal_name
        short_name = profile.short_name or item.short_name or legal_name
        if (profile.inn or profile.ogrn) and legal_name and short_name:
            return "valid"
        if legal_name and short_name and item.profile_url and (profile.legal_address or item.address or item.raw_text):
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
        ((company.raw_payload or {}).get("profile") or {}).get("legal_address") if company.raw_payload else None,
    ]
    haystack = " ".join(_normalize_region_text(part) for part in haystack_parts if part)
    return any(variant and variant in haystack for variant in variants)


def _normalize_region_text(value: str | None) -> str:
    text = (value or "").lower().replace("ё", "е")
    text = re.sub(r"[^\w\s-]+", " ", text, flags=re.UNICODE)
    text = re.sub(
        r"\b(\u0433|\u0433\u043e\u0440\u043e\u0434|\u043e\u0431\u043b\u0430\u0441\u0442\u044c|\u043e\u0431\u043b|\u0440\u0435\u0441\u043f\u0443\u0431\u043b\u0438\u043a\u0430|\u0440-\u043d|\u0440\u0430\u0439\u043e\u043d)\b",
        " ",
        text,
    )
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _build_region_variants(normalized_query: str) -> set[str]:
    variants = {normalized_query}
    for token in normalized_query.split():
        if len(token) < 3:
            continue
        variants.add(token)
        if token.endswith("ская"):
            variants.add(token[:-4])
        elif token.endswith("ский"):
            variants.add(token[:-4])
    return {item.strip() for item in variants if item.strip()}


def _extract_city_from_address(address: str | None) -> str | None:
    text = address or ""
    for pattern in (
        r"\bг\.\s*([А-ЯA-ZЁ][^,]+)",
        r"\bгород\s+([А-ЯA-ZЁ][^,]+)",
    ):
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


def _contains_any_marker(text: str, markers: tuple[str, ...]) -> bool:
    normalized = _normalize_region_text(text)
    return any(_normalize_region_text(marker) in normalized for marker in markers)


def _slugify_region(region_query: str | None) -> str:
    normalized = _normalize_region_text(region_query or "all")
    slug = re.sub(r"[^a-zа-я0-9]+", "_", normalized, flags=re.IGNORECASE)
    return slug.strip("_") or "all"
