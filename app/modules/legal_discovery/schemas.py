from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DiscoveryConfidence = Literal["low", "medium", "high"]
PreviewItemStatus = Literal["new", "duplicate_existing", "weak_data", "inactive", "error"]


class LegalDiscoveredCompany(BaseModel):
    provider: str
    inn: str
    ogrn: str
    kpp: str | None = None
    legal_name: str
    short_name: str | None = None
    address: str | None = None
    city: str | None = None
    region: str | None = None
    status: str | None = None
    okved: str | None = None
    okved_name: str | None = None
    raw_payload: dict[str, Any] | None = None
    confidence: DiscoveryConfidence = "medium"
    warnings: list[str] = Field(default_factory=list)


class LegalDiscoveryPreviewItem(BaseModel):
    status: PreviewItemStatus
    company: LegalDiscoveredCompany
    duplicate_company_id: int | None = None
    duplicate_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class LegalDiscoveryPreview(BaseModel):
    preview_id: str
    query: str
    city: str | None = None
    region: str | None = None
    provider: str
    total_found: int
    active_count: int
    inactive_count: int
    new_count: int
    duplicate_count: int
    weak_count: int
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
    city: str | None = None
    region: str | None = None
    limit: int = 50
    provider: str | None = None


class LegalDiscoveryImportRequest(BaseModel):
    preview_id: str
    mode: Literal["active_new", "all_new"] = "active_new"
