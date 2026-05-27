from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


EnrichmentStatus = Literal["success", "partial", "failed", "manual"]
SignalName = Literal[
    "has_online_booking",
    "has_callback_form",
    "has_prices",
    "has_doctors_page",
    "has_reviews_section",
    "has_contacts_page",
    "has_social_links",
    "has_messenger_links",
    "has_privacy_policy",
    "has_promotions",
    "has_implantation_keywords",
    "has_orthodontics_keywords",
    "has_children_dentistry_keywords",
    "has_emergency_keywords",
]


def dump_json_text(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def parse_json_text(value: str | None, default: Any) -> Any:
    if not value:
        if isinstance(default, list):
            return list(default)
        if isinstance(default, dict):
            return dict(default)
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        if isinstance(default, list):
            return list(default)
        if isinstance(default, dict):
            return dict(default)
        return default


class FetchResult(BaseModel):
    url: str
    final_url: str | None = None
    status: EnrichmentStatus
    http_status: int | None = None
    html: str | None = None
    error_message: str | None = None


class DetectedLinksRead(BaseModel):
    internal_links: list[str] = Field(default_factory=list)
    external_links: list[str] = Field(default_factory=list)


class DetectedContactsRead(BaseModel):
    phones: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    whatsapp_links: list[str] = Field(default_factory=list)
    telegram_links: list[str] = Field(default_factory=list)


class WebsiteSignalRead(BaseModel):
    has_online_booking: bool = False
    has_callback_form: bool = False
    has_prices: bool = False
    has_doctors_page: bool = False
    has_reviews_section: bool = False
    has_contacts_page: bool = False
    has_social_links: bool = False
    has_messenger_links: bool = False
    has_privacy_policy: bool = False
    has_promotions: bool = False
    has_implantation_keywords: bool = False
    has_orthodontics_keywords: bool = False
    has_children_dentistry_keywords: bool = False
    has_emergency_keywords: bool = False


class WebsiteAnalysis(BaseModel):
    page_title: str | None = None
    meta_description: str | None = None
    raw_text_excerpt: str | None = None
    detected_links: DetectedLinksRead = Field(default_factory=DetectedLinksRead)
    detected_socials: dict[str, list[str]] = Field(default_factory=dict)
    detected_maps: dict[str, list[str]] = Field(default_factory=dict)
    detected_contacts: DetectedContactsRead = Field(default_factory=DetectedContactsRead)
    signals: WebsiteSignalRead = Field(default_factory=WebsiteSignalRead)


class EnrichmentRequest(BaseModel):
    website_url: str | None = None
    use_ai: bool = True


class EnrichmentSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    website_url: str | None = None
    status: str
    fetched_at: datetime | None = None
    http_status: int | None = None
    page_title: str | None = None
    meta_description: str | None = None
    detected_links: DetectedLinksRead = Field(default_factory=DetectedLinksRead)
    detected_socials: dict[str, list[str]] = Field(default_factory=dict)
    detected_maps: dict[str, list[str]] = Field(default_factory=dict)
    detected_contacts: DetectedContactsRead = Field(default_factory=DetectedContactsRead)
    signals: WebsiteSignalRead = Field(default_factory=WebsiteSignalRead)
    hypotheses: list[str] = Field(default_factory=list)
    ai_summary: str | None = None
    raw_text_excerpt: str | None = None
    error_message: str | None = None
    created_at: datetime


class EnrichmentResultRead(BaseModel):
    company_id: int
    website_url: str | None = None
    status: str
    http_status: int | None = None
    page_title: str | None = None
    meta_description: str | None = None
    detected_links: DetectedLinksRead = Field(default_factory=DetectedLinksRead)
    detected_socials: dict[str, list[str]] = Field(default_factory=dict)
    detected_maps: dict[str, list[str]] = Field(default_factory=dict)
    detected_contacts: DetectedContactsRead = Field(default_factory=DetectedContactsRead)
    signals: WebsiteSignalRead = Field(default_factory=WebsiteSignalRead)
    hypotheses: list[str] = Field(default_factory=list)
    ai_summary: str | None = None
    raw_text_excerpt: str | None = None
    error_message: str | None = None
    snapshot_id: int | None = None
    fetched_at: datetime | None = None


class Bot2EnrichmentContextRead(BaseModel):
    latest_snapshot_at: datetime | None = None
    website_url: str | None = None
    status: str | None = None
    signals: WebsiteSignalRead = Field(default_factory=WebsiteSignalRead)
    hypotheses: list[str] = Field(default_factory=list)
    ai_summary: str | None = None
    detected_socials: dict[str, list[str]] = Field(default_factory=dict)
    detected_maps: dict[str, list[str]] = Field(default_factory=dict)

