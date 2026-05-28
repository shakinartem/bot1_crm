from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ResearchJobCreateRequest(BaseModel):
    company_ids: list[int] = Field(default_factory=list)
    job_type: str = "full_research"
    priority: str = "medium"
    max_attempts: int = 3


class ResearchBatchRunRequest(BaseModel):
    concurrency: int = 5
    limit: int = 100


class ResearchJobRead(BaseModel):
    id: int
    company_id: int
    job_type: str
    status: str
    priority: str
    attempts: int
    max_attempts: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    result: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime | None = None


class ResearchQueueStatusRead(BaseModel):
    total: int = 0
    pending: int = 0
    running: int = 0
    success: int = 0
    failed: int = 0
    blocked: int = 0
    needs_manual_review: int = 0
    cancelled: int = 0


class ResearchJobResultSummary(BaseModel):
    company_id: int
    status: str
    website_url: str | None = None
    website_confidence: float | None = None
    error_message: str | None = None
