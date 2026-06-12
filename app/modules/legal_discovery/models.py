from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LegalDiscoveryCursor(Base):
    __tablename__ = "legal_discovery_cursors"
    __table_args__ = (UniqueConstraint("provider", "okved_code", "query_hash", name="uq_legal_discovery_cursors_query"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    okved_code: Mapped[str] = mapped_column(String(32), index=True)
    niche_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    query_hash: Mapped[str] = mapped_column(String(255), index=True)
    current_page: Mapped[int] = mapped_column(Integer, default=1)
    last_profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_inn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_ogrn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    previewed_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
