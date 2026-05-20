from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.crm.constants import CompanyStatus


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = None
    inn: str | None = None
    ogrn: str | None = None
    city: str | None = None
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    maps_url: str | None = None
    vk_url: str | None = None
    instagram_url: str | None = None
    telegram_url: str | None = None
    other_socials: str | None = None
    rating: float | None = None
    reviews_count: int | None = None
    source: str | None = None
    status: CompanyStatus = CompanyStatus.NEW
    notes: str | None = None


class CompanyRead(CompanyCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class DecisionMakerCreate(BaseModel):
    company_id: int
    full_name: str
    role: str | None = None
    phone: str | None = None
    email: str | None = None
    telegram: str | None = None
    is_primary: bool = False
    notes: str | None = None
