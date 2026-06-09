from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DiscoveryConfidence = Literal["low", "medium", "high"]
PreviewItemStatus = Literal["new", "duplicate_existing", "weak_data", "inactive", "error"]
BusinessStatus = Literal["active", "inactive", "unknown"]
ImportMode = Literal["active_new", "all_new", "new_with_websites", "new_with_phone_or_website"]


class PopularOkvedItem(BaseModel):
    code: str
    normalized_code: str
    title: str
    keywords: list[str] = Field(default_factory=list)


class LegalDiscoveryDirector(BaseModel):
    full_name: str
    role: str | None = None
    inn: str | None = None
    since_date: str | None = None


class LegalDiscoveryFounder(BaseModel):
    full_name: str
    role: str | None = None
    inn: str | None = None
    share_text: str | None = None


class LegalDiscoveredCompany(BaseModel):
    provider: str
    inn: str | None = None
    ogrn: str | None = None
    kpp: str | None = None
    okpo: str | None = None
    legal_name: str | None = None
    short_name: str | None = None
    address: str | None = None
    city: str | None = None
    region: str | None = None
    status: str | None = None
    okved: str | None = None
    okved_name: str | None = None
    phones: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    websites: list[str] = Field(default_factory=list)
    telegram_links: list[str] = Field(default_factory=list)
    vk_links: list[str] = Field(default_factory=list)
    instagram_links: list[str] = Field(default_factory=list)
    whatsapp_links: list[str] = Field(default_factory=list)
    youtube_links: list[str] = Field(default_factory=list)
    map_links: list[str] = Field(default_factory=list)
    director: LegalDiscoveryDirector | None = None
    founders: list[LegalDiscoveryFounder] = Field(default_factory=list)
    checko_profile_url: str | None = None
    text_excerpt: str | None = None
    raw_payload: dict[str, Any] | None = None
    confidence: DiscoveryConfidence = "medium"
    warnings: list[str] = Field(default_factory=list)


class LegalDiscoveryPreviewItem(BaseModel):
    status: PreviewItemStatus
    business_status: BusinessStatus = "unknown"
    weak_data: bool = False
    company: LegalDiscoveredCompany
    duplicate_company_id: int | None = None
    duplicate_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class LegalDiscoveryPreview(BaseModel):
    preview_id: str
    query: str
    okved_code: str | None = None
    okved_title: str | None = None
    city: str | None = None
    region: str | None = None
    provider: str
    total_found: int
    active_count: int
    inactive_count: int
    unknown_status_count: int = 0
    with_inn_count: int = 0
    with_ogrn_count: int = 0
    with_phone_count: int = 0
    with_email_count: int = 0
    with_website_count: int = 0
    with_socials_count: int = 0
    with_director_count: int = 0
    with_founders_count: int = 0
    new_count: int
    duplicate_count: int
    weak_count: int
    candidates_before_region: int = 0
    profile_fetch_success: int = 0
    profile_fetch_failed: int = 0
    filtered_by_region_count: int = 0
    skipped_not_company_count: int = 0
    invalid_candidates_count: int = 0
    parser_candidates_count: int = 0
    company_links_found: int = 0
    debug_final_url: str | None = None
    debug_title: str | None = None
    debug_html_chars: int = 0
    debug_text_chars: int = 0
    debug_snapshot_path: str | None = None
    debug_info: dict[str, Any] = Field(default_factory=dict)
    items: list[LegalDiscoveryPreviewItem] = Field(default_factory=list)


class LegalDiscoveryImportResult(BaseModel):
    added_count: int = 0
    skipped_duplicates: int = 0
    skipped_inactive: int = 0
    skipped_weak: int = 0
    errors_count: int = 0
    added_company_ids: list[int] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class LegalDiscoverySearchRequest(BaseModel):
    query: str
    okved_code: str | None = None
    okved_title: str | None = None
    city: str | None = None
    region: str | None = None
    limit: int = 50
    only_main_okved: bool = True
    only_active: bool = True
    include_profiles: bool = True
    concurrency: int | None = None
    provider: str | None = None


class LegalDiscoveryImportRequest(BaseModel):
    preview_id: str
    mode: ImportMode = "active_new"
    include_weak: bool = False
    run_research_after_import: bool = False
