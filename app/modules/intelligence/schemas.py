from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.enrichment.schemas import WebsiteSignalRead, dump_json_text, parse_json_text


IntelligenceStatus = Literal["success", "partial", "failed", "needs_review"]


class LegalCompany(BaseModel):
    provider: str
    inn: str
    ogrn: str | None = None
    kpp: str | None = None
    legal_name: str
    short_name: str | None = None
    address: str | None = None
    city: str | None = None
    region: str | None = None
    status: str | None = None
    okved: str | None = None
    raw_payload: dict[str, Any] | None = None
    confidence: float = 0.0


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str | None = None
    source: str
    rank: int
    raw_payload: dict[str, Any] | None = None


class WebsiteCandidate(BaseModel):
    url: str
    title: str | None = None
    snippet: str | None = None
    confidence: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    is_official_candidate: bool = False
    fetched_excerpt: str | None = None


class WebsiteResolutionResult(BaseModel):
    selected_url: str | None = None
    confidence: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    candidates: list[WebsiteCandidate] = Field(default_factory=list)
    references: list[SearchResult] = Field(default_factory=list)


class ParsedCompanyContacts(BaseModel):
    phones: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    addresses: list[str] = Field(default_factory=list)
    whatsapp_links: list[str] = Field(default_factory=list)
    telegram_links: list[str] = Field(default_factory=list)


class ParsedCompanySocials(BaseModel):
    vk_links: list[str] = Field(default_factory=list)
    instagram_links: list[str] = Field(default_factory=list)
    youtube_links: list[str] = Field(default_factory=list)
    tiktok_links: list[str] = Field(default_factory=list)
    dzen_links: list[str] = Field(default_factory=list)
    telegram_links: list[str] = Field(default_factory=list)
    whatsapp_links: list[str] = Field(default_factory=list)
    yandex_maps_links: list[str] = Field(default_factory=list)
    two_gis_links: list[str] = Field(default_factory=list)


class ParsedCompanySite(BaseModel):
    page_title: str | None = None
    meta_description: str | None = None
    text_excerpt: str | None = None
    contacts: ParsedCompanyContacts = Field(default_factory=ParsedCompanyContacts)
    socials: ParsedCompanySocials = Field(default_factory=ParsedCompanySocials)
    signals: WebsiteSignalRead = Field(default_factory=WebsiteSignalRead)


class IntelligenceRequest(BaseModel):
    inn: str | None = None
    use_ai: bool = True


class IntelligenceSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    status: str
    inn: str | None = None
    legal_name: str | None = None
    ogrn: str | None = None
    legal_address: str | None = None
    legal_status: str | None = None
    okved: str | None = None
    website_url: str | None = None
    website_confidence: float | None = None
    website_candidates: list[WebsiteCandidate] = Field(default_factory=list)
    parsed_contacts: ParsedCompanyContacts = Field(default_factory=ParsedCompanyContacts)
    parsed_socials: ParsedCompanySocials = Field(default_factory=ParsedCompanySocials)
    parsed_signals: WebsiteSignalRead = Field(default_factory=WebsiteSignalRead)
    hypotheses: list[str] = Field(default_factory=list)
    ai_summary: str | None = None
    raw_references: list[SearchResult] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime


class CompanyIntelligenceResult(BaseModel):
    company_id: int
    status: str
    legal_candidates: list[LegalCompany] = Field(default_factory=list)
    selected_legal: LegalCompany | None = None
    website_resolution: WebsiteResolutionResult | None = None
    parsed_site: ParsedCompanySite | None = None
    hypotheses: list[str] = Field(default_factory=list)
    ai_summary: str | None = None
    error_message: str | None = None
    snapshot_id: int | None = None
    updated_fields: list[str] = Field(default_factory=list)


class Bot2IntelligenceContextRead(BaseModel):
    latest_snapshot_at: datetime | None = None
    status: str | None = None
    inn: str | None = None
    legal_name: str | None = None
    ogrn: str | None = None
    legal_address: str | None = None
    legal_status: str | None = None
    okved: str | None = None
    website_url: str | None = None
    website_confidence: float | None = None
    parsed_contacts: ParsedCompanyContacts = Field(default_factory=ParsedCompanyContacts)
    parsed_socials: ParsedCompanySocials = Field(default_factory=ParsedCompanySocials)
    parsed_signals: WebsiteSignalRead = Field(default_factory=WebsiteSignalRead)
    hypotheses: list[str] = Field(default_factory=list)
    ai_summary: str | None = None


def parse_candidates(raw: str | None) -> list[WebsiteCandidate]:
    payload = parse_json_text(raw, [])
    if not isinstance(payload, list):
        return []
    return [WebsiteCandidate.model_validate(item) for item in payload]


def parse_references(raw: str | None) -> list[SearchResult]:
    payload = parse_json_text(raw, [])
    if not isinstance(payload, list):
        return []
    return [SearchResult.model_validate(item) for item in payload]


def parse_contacts(raw: str | None) -> ParsedCompanyContacts:
    return ParsedCompanyContacts.model_validate(parse_json_text(raw, {}))


def parse_socials(raw: str | None) -> ParsedCompanySocials:
    return ParsedCompanySocials.model_validate(parse_json_text(raw, {}))


def parse_signals(raw: str | None) -> WebsiteSignalRead:
    return WebsiteSignalRead.model_validate(parse_json_text(raw, {}))


__all__ = [
    "Bot2IntelligenceContextRead",
    "CompanyIntelligenceResult",
    "IntelligenceRequest",
    "IntelligenceSnapshotRead",
    "IntelligenceStatus",
    "LegalCompany",
    "ParsedCompanyContacts",
    "ParsedCompanySite",
    "ParsedCompanySocials",
    "SearchResult",
    "WebsiteCandidate",
    "WebsiteResolutionResult",
    "WebsiteSignalRead",
    "dump_json_text",
    "parse_candidates",
    "parse_contacts",
    "parse_json_text",
    "parse_references",
    "parse_signals",
    "parse_socials",
]
