from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.crm.constants import (
    CompanyStatus,
    ContactType,
    InteractionResult,
    InteractionType,
    LeadPriority,
    TaskStatus,
)
from app.modules.enrichment.schemas import Bot2EnrichmentContextRead
from app.modules.intelligence.schemas import Bot2IntelligenceContextRead
from app.modules.research.schemas import ResearchContextRead


class CompanyBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = None
    inn: str | None = None
    ogrn: str | None = None
    address: str | None = None
    city: str | None = None
    region: str | None = None
    phone: str | None = None
    website: str | None = None
    social_links: str | None = None
    maps_url: str | None = None
    vk_url: str | None = None
    instagram_url: str | None = None
    telegram_url: str | None = None
    other_socials: str | None = None
    rating: float | None = None
    reviews_count: int | None = None
    source: str | None = None
    status: CompanyStatus = CompanyStatus.NEW
    priority: LeadPriority = LeadPriority.MEDIUM
    notes: str | None = None


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    legal_name: str | None = None
    inn: str | None = None
    ogrn: str | None = None
    address: str | None = None
    city: str | None = None
    region: str | None = None
    phone: str | None = None
    website: str | None = None
    social_links: str | None = None
    maps_url: str | None = None
    vk_url: str | None = None
    instagram_url: str | None = None
    telegram_url: str | None = None
    other_socials: str | None = None
    rating: float | None = None
    reviews_count: int | None = None
    source: str | None = None
    status: CompanyStatus | None = None
    priority: LeadPriority | None = None
    notes: str | None = None


class CompanyRead(CompanyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    priority: str
    created_at: datetime
    updated_at: datetime


class DecisionMakerCreate(BaseModel):
    company_id: int
    full_name: str
    role: str | None = None
    phone: str | None = None
    email: str | None = None
    telegram: str | None = None
    source: str | None = None
    is_primary: bool = False
    notes: str | None = None


class DecisionMakerRead(DecisionMakerCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ContactPointCreate(BaseModel):
    company_id: int
    type: ContactType
    value: str
    label: str | None = None
    is_primary: bool = False
    notes: str | None = None


class ContactPointRead(ContactPointCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class InteractionCreate(BaseModel):
    company_id: int
    decision_maker_id: int | None = None
    type: InteractionType = InteractionType.NOTE
    result: InteractionResult | None = None
    summary: str | None = None
    next_action: str | None = None
    next_action_at: datetime | None = None
    created_by: str | None = None


class InteractionRead(InteractionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class FollowUpTaskCreate(BaseModel):
    company_id: int
    title: str
    description: str | None = None
    due_at: datetime | None = None
    status: TaskStatus = TaskStatus.OPEN
    priority: LeadPriority = LeadPriority.MEDIUM


class FollowUpTaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    due_at: datetime | None = None
    status: TaskStatus | None = None
    priority: LeadPriority | None = None
    completed_at: datetime | None = None


class FollowUpTaskRead(FollowUpTaskCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    priority: str
    created_at: datetime
    completed_at: datetime | None = None


class Bot2ConsultationResultCreate(BaseModel):
    result: Literal["refused", "thinking", "contract_sent", "signed"]
    summary: str = Field(min_length=1)
    source: str = Field(default="bot2", min_length=1)


class Bot2CompanyContext(BaseModel):
    id: int
    name: str
    legal_name: str | None = None
    city: str | None = None
    region: str | None = None
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    maps_url: str | None = None
    vk_url: str | None = None
    instagram_url: str | None = None
    telegram_url: str | None = None
    other_socials: str | None = None
    social_links: str | None = None
    rating: float | None = None
    reviews_count: int | None = None
    source: str | None = None
    status: str
    priority: str
    notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class Bot2DecisionMakerContext(BaseModel):
    id: int
    full_name: str
    role: str | None = None
    phone: str | None = None
    email: str | None = None
    telegram: str | None = None
    is_primary: bool
    notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class Bot2ContactContext(BaseModel):
    id: int
    type: str
    value: str
    label: str | None = None
    is_primary: bool
    notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class Bot2InteractionContext(BaseModel):
    id: int
    type: str
    result: str | None = None
    summary: str | None = None
    next_action: str | None = None
    next_action_at: datetime | None = None
    created_by: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Bot2TaskContext(BaseModel):
    id: int
    title: str
    description: str | None = None
    due_at: datetime | None = None
    priority: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class Bot2ConsultationContextRead(BaseModel):
    company: Bot2CompanyContext
    decision_makers: list[Bot2DecisionMakerContext]
    contacts: list[Bot2ContactContext]
    recent_interactions: list[Bot2InteractionContext]
    open_tasks: list[Bot2TaskContext]
    latest_proposal: Bot2InteractionContext | None = None
    latest_call_result: Bot2InteractionContext | None = None
    recommended_next_step: str
    sales_summary: str
    enrichment: Bot2EnrichmentContextRead | None = None
    intelligence: Bot2IntelligenceContextRead | None = None
    research: ResearchContextRead | None = None
