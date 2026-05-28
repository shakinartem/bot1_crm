from __future__ import annotations

from datetime import datetime
from functools import partial
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field

from app.config import Settings
from app.modules.enrichment.schemas import WebsiteSignalRead
from app.modules.intelligence.schemas import ParsedCompanyContacts, ParsedCompanySocials, SearchResult


FetchStatus = Literal["success", "failed", "blocked", "non_html", "timeout"]
ResearchStatus = Literal["success", "partial", "failed", "blocked", "needs_manual_review"]


class FetchResult(BaseModel):
    url: str
    final_url: str | None = None
    status: FetchStatus
    http_status: int | None = None
    html: str | None = None
    text_excerpt: str | None = None
    error_message: str | None = None
    blocked_reason: str | None = None


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


class ParsedCompanySite(BaseModel):
    page_title: str | None = None
    meta_description: str | None = None
    text_excerpt: str | None = None
    contacts: ParsedCompanyContacts = Field(default_factory=ParsedCompanyContacts)
    socials: ParsedCompanySocials = Field(default_factory=ParsedCompanySocials)
    signals: WebsiteSignalRead = Field(default_factory=WebsiteSignalRead)


class ResearchResult(BaseModel):
    company_id: int
    status: ResearchStatus
    website_url: str | None = None
    website_confidence: float | None = None
    page_title: str | None = None
    parsed_site: ParsedCompanySite | None = None
    hypotheses: list[str] = Field(default_factory=list)
    ai_summary: str | None = None
    error_message: str | None = None
    blocked_reason: str | None = None
    snapshot_id: int | None = None
    updated_fields: list[str] = Field(default_factory=list)
    result_meta: dict[str, Any] = Field(default_factory=dict)


class ResearchResultRead(BaseModel):
    company_id: int
    status: str
    website_url: str | None = None
    website_confidence: float | None = None
    page_title: str | None = None
    hypotheses: list[str] = Field(default_factory=list)
    ai_summary: str | None = None
    error_message: str | None = None
    blocked_reason: str | None = None
    snapshot_id: int | None = None
    updated_fields: list[str] = Field(default_factory=list)


class ResearchRunRequest(BaseModel):
    force: bool = False


class ResearchContextRead(BaseModel):
    latest_snapshot_at: datetime | None = None
    status: str | None = None
    website_url: str | None = None
    website_confidence: float | None = None
    parsed_contacts: ParsedCompanyContacts = Field(default_factory=ParsedCompanyContacts)
    parsed_socials: ParsedCompanySocials = Field(default_factory=ParsedCompanySocials)
    parsed_signals: WebsiteSignalRead = Field(default_factory=WebsiteSignalRead)
    hypotheses: list[str] = Field(default_factory=list)
    ai_summary: str | None = None


FetchBackend = Callable[[str], Awaitable[FetchResult]]


def get_fetch_backend(settings: Settings) -> FetchBackend:
    from app.modules.research.browser_fetcher import fetch_with_browser
    from app.modules.research.http_fetcher import fetch_url

    if settings.research_fetch_backend.lower() == "browser":
        return fetch_with_browser
    return partial(
        fetch_url,
        timeout=settings.research_request_timeout,
        max_chars=settings.research_max_html_chars,
    )
