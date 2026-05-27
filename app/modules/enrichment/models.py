from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EnrichmentSnapshot(Base):
    __tablename__ = "enrichment_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    website_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_links_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_socials_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_maps_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_contacts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    signals_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    hypotheses_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company = relationship("Company", back_populates="enrichment_snapshots")
