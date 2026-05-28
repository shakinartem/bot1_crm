from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class IntelligenceSnapshot(Base):
    __tablename__ = "intelligence_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    inn: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ogrn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    legal_address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    legal_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    okved: Mapped[str | None] = mapped_column(String(64), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    website_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    website_candidates_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_contacts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_socials_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_signals_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    hypotheses_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_references_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company = relationship("Company", back_populates="intelligence_snapshots")
