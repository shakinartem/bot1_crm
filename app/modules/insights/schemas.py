from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CompanyInsightSnapshotCreate(BaseModel):
    company_id: int
    insight_type: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, max_length=255)
    status: str = Field(default="success", min_length=1, max_length=32)
    payload: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    source: str | None = Field(default=None, max_length=128)
    version: str | None = Field(default=None, max_length=64)


class CompanyInsightSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    insight_type: str
    title: str | None = None
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    source: str | None = None
    version: str | None = None
    created_at: datetime
    updated_at: datetime
