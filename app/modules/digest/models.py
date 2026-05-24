from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DigestSettings(Base):
    __tablename__ = "digest_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    send_time: Mapped[str] = mapped_column(String(5), default="09:00", nullable=False)
    weekdays: Mapped[str] = mapped_column(String(32), default="0,1,2,3,4", nullable=False)
    stale_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def weekdays_tuple(self) -> tuple[int, ...]:
        return tuple(int(part) for part in self.weekdays.split(",") if part.strip())

    @property
    def weekdays_label(self) -> str:
        labels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        return "-".join(labels[index] for index in self.weekdays_tuple if 0 <= index <= 6)
