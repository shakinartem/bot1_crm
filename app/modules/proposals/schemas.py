from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PackageRead(BaseModel):
    code: str
    title: str
    price: str
    items: list[str]
    suggested_when: list[str]
    result: str
    client_needs: list[str]


class PackageSuggestion(BaseModel):
    code: str
    title: str
    price: str
    reason: str
    confidence: str


class ProposalActionRequest(BaseModel):
    selected_package_codes: list[str] | None = None
    use_ai: bool = True


class ContractActionRequest(BaseModel):
    selected_package_codes: list[str] | None = None


class ProposalGenerationResultRead(BaseModel):
    title: str
    content: str
    file_path: str
    selected_packages: list[PackageSuggestion]
    used_ai: bool


class ContractDraftResultRead(BaseModel):
    title: str
    content: str
    file_path: str
    selected_packages: list[PackageSuggestion]


class ServiceAppendixResultRead(BaseModel):
    title: str
    content: str
    file_path: str
    selected_packages: list[PackageSuggestion]


class ProposalDraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    draft_type: str
    title: str
    content: str
    file_path: str
    selected_packages: list[str] = Field(default_factory=list)
    used_ai: bool
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
