from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.modules.crm.constants import CompanyStatus, LeadPriority, TaskStatus


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inn: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    ogrn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    region: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    social_links: Mapped[str | None] = mapped_column(Text, nullable=True)
    maps_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    vk_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    instagram_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    other_socials: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviews_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default=CompanyStatus.NEW.value, index=True)
    priority: Mapped[str] = mapped_column(String(32), default=LeadPriority.MEDIUM.value, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    decision_makers: Mapped[list["DecisionMaker"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    contacts: Mapped[list["ContactPoint"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    interactions: Mapped[list["LeadInteraction"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[list["FollowUpTask"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    calls: Mapped[list["CallRecord"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    proposal_drafts: Mapped[list["ProposalDraft"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    enrichment_snapshots: Mapped[list["EnrichmentSnapshot"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )


class DecisionMaker(Base):
    __tablename__ = "decision_makers"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    full_name: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str | None] = mapped_column(String(128), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    company: Mapped[Company] = relationship(back_populates="decision_makers")
    interactions: Mapped[list["LeadInteraction"]] = relationship(back_populates="decision_maker")


class ContactPoint(Base):
    __tablename__ = "contact_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[str] = mapped_column(String(255), index=True)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    company: Mapped[Company] = relationship(back_populates="contacts")


class LeadInteraction(Base):
    __tablename__ = "lead_interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    decision_maker_id: Mapped[int | None] = mapped_column(
        ForeignKey("decision_makers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(64), index=True)
    result: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped[Company] = relationship(back_populates="interactions")
    decision_maker: Mapped[DecisionMaker | None] = relationship(back_populates="interactions")


class FollowUpTask(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default=TaskStatus.OPEN.value, index=True)
    priority: Mapped[str] = mapped_column(String(32), default=LeadPriority.MEDIUM.value, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped[Company] = relationship(back_populates="tasks")


Task = FollowUpTask


from app.modules.calls.models import CallRecord  # noqa: E402,F401
from app.modules.enrichment.models import EnrichmentSnapshot  # noqa: E402,F401
from app.modules.proposals.models import ProposalDraft  # noqa: E402,F401
