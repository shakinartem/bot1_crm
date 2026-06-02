from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.crm.constants import CRMUserRole


class CRMUserCreate(BaseModel):
    telegram_user_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    role: CRMUserRole = CRMUserRole.MANAGER


class CRMUserUpdate(BaseModel):
    username: str | None = None
    full_name: str | None = None
    role: CRMUserRole | None = None
    is_active: bool | None = None


class CRMUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None = None


class AssignmentResult(BaseModel):
    company_id: int
    assigned_user_id: int | None = None
    assigned_user_name: str | None = None
    status: str


class CompanyAssignRequest(BaseModel):
    user_id: int | None = None
