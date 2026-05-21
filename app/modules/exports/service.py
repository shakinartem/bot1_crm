from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.modules.crm.handoff import build_consultation_handoff_payload
from app.modules.crm.models import Company
from app.modules.crm.service import (
    build_company_consultation_package,
    humanize_company_status,
    humanize_interaction_result,
    humanize_priority,
)


EXPORT_COLUMNS = [
    "id",
    "name",
    "legal_name",
    "inn",
    "ogrn",
    "city",
    "region",
    "address",
    "phone",
    "website",
    "status",
    "priority",
    "source",
    "notes",
    "decision_makers",
    "contacts",
    "last_interaction_at",
    "last_interaction_result",
    "next_task_title",
    "next_task_due_at",
    "created_at",
    "updated_at",
]


@dataclass(slots=True)
class ExportFilters:
    status: str | None = None
    city: str | None = None
    source: str | None = None
    priority: str | None = None
    limit: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "status": self.status,
                "city": self.city,
                "source": self.source,
                "priority": self.priority,
                "limit": self.limit,
            }.items()
            if value not in (None, "")
        }

    def slug(self) -> str:
        if self.status:
            return self.status
        if self.city:
            return f"city_{_slugify(self.city)}"
        if self.source:
            return f"source_{_slugify(self.source)}"
        if self.priority:
            return f"priority_{self.priority}"
        return "all"


@dataclass(slots=True)
class ExportResult:
    file_path: str
    filename: str
    total_exported: int
    filters_applied: dict[str, Any]
    created_at: str


def export_text_artifact(
    *,
    company_id: int,
    prefix: str,
    content: str,
    extension: str = ".txt",
) -> ExportResult:
    exports_dir = _exports_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_company_{company_id}_{timestamp}{extension}"
    file_path = exports_dir / filename
    file_path.write_text(content, encoding="utf-8")
    return ExportResult(
        file_path=str(file_path),
        filename=filename,
        total_exported=1,
        filters_applied={"company_id": company_id, "prefix": prefix, "extension": extension},
        created_at=datetime.now().isoformat(),
    )


async def export_companies_to_csv(
    session: AsyncSession,
    filters: ExportFilters,
) -> ExportResult:
    companies = await _list_companies_for_export(session, filters)
    exports_dir = _exports_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = filters.slug()
    filename = f"companies_{slug}_{timestamp}.csv" if slug != "all" else f"companies_export_{timestamp}.csv"
    file_path = exports_dir / filename

    with file_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=EXPORT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for company in companies:
            last_interaction = _last_interaction(company)
            next_task = _next_task(company)
            writer.writerow(
                {
                    "id": company.id,
                    "name": company.name,
                    "legal_name": company.legal_name or "",
                    "inn": company.inn or "",
                    "ogrn": company.ogrn or "",
                    "city": company.city or "",
                    "region": company.region or "",
                    "address": company.address or "",
                    "phone": company.phone or "",
                    "website": company.website or "",
                    "status": company.status,
                    "priority": company.priority,
                    "source": company.source or "",
                    "notes": company.notes or "",
                    "decision_makers": _join_decision_makers(company),
                    "contacts": _join_contacts(company),
                    "last_interaction_at": _format_dt(last_interaction.created_at) if last_interaction else "",
                    "last_interaction_result": (
                        humanize_interaction_result(last_interaction.result)
                        if last_interaction and last_interaction.result
                        else ""
                    ),
                    "next_task_title": next_task.title if next_task else "",
                    "next_task_due_at": _format_dt(next_task.due_at) if next_task and next_task.due_at else "",
                    "created_at": _format_dt(company.created_at),
                    "updated_at": _format_dt(company.updated_at),
                }
            )

    return ExportResult(
        file_path=str(file_path),
        filename=filename,
        total_exported=len(companies),
        filters_applied=filters.as_dict(),
        created_at=datetime.now().isoformat(),
    )


async def export_company_markdown(
    session: AsyncSession,
    company_id: int,
) -> ExportResult | None:
    package = await build_company_consultation_package(session, company_id)
    if not package:
        return None

    exports_dir = _exports_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"company_{company_id}_consultation_package_{timestamp}.md"
    file_path = exports_dir / filename
    file_path.write_text(package["markdown"], encoding="utf-8")

    return ExportResult(
        file_path=str(file_path),
        filename=filename,
        total_exported=1,
        filters_applied={"company_id": company_id, "format": "markdown"},
        created_at=datetime.now().isoformat(),
    )


async def export_handoff_payload_json(
    session: AsyncSession,
    company_id: int,
) -> ExportResult | None:
    payload = await build_consultation_handoff_payload(session, company_id)
    if not payload:
        return None

    exports_dir = _exports_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"bot2_handoff_company_{company_id}_{timestamp}.json"
    file_path = exports_dir / filename
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return ExportResult(
        file_path=str(file_path),
        filename=filename,
        total_exported=1,
        filters_applied={"company_id": company_id, "format": "json"},
        created_at=datetime.now().isoformat(),
    )


async def _list_companies_for_export(session: AsyncSession, filters: ExportFilters) -> list[Company]:
    stmt = (
        select(Company)
        .options(
            selectinload(Company.decision_makers),
            selectinload(Company.contacts),
            selectinload(Company.interactions),
            selectinload(Company.tasks),
        )
        .order_by(Company.created_at.desc())
    )
    if filters.status:
        stmt = stmt.where(Company.status == filters.status)
    if filters.city:
        stmt = stmt.where(Company.city.ilike(f"%{filters.city}%"))
    if filters.source:
        stmt = stmt.where(Company.source.ilike(f"%{filters.source}%"))
    if filters.priority:
        stmt = stmt.where(Company.priority == filters.priority)
    if filters.limit:
        stmt = stmt.limit(filters.limit)

    result = await session.execute(stmt)
    return list(result.scalars().unique().all())


def _join_decision_makers(company: Company) -> str:
    parts = []
    for dm in company.decision_makers:
        parts.append(
            " | ".join(
                bit
                for bit in [dm.full_name, dm.role, dm.phone, dm.email, dm.telegram]
                if bit
            )
        )
    return " || ".join(parts)


def _join_contacts(company: Company) -> str:
    parts = []
    for contact in company.contacts:
        label = f" ({contact.label})" if contact.label else ""
        parts.append(f"{contact.type}: {contact.value}{label}")
    return " || ".join(parts)


def _last_interaction(company: Company):
    if not company.interactions:
        return None
    return sorted(company.interactions, key=lambda item: item.created_at or datetime.min, reverse=True)[0]


def _next_task(company: Company):
    open_tasks = [task for task in company.tasks if task.status == "open"]
    if not open_tasks:
        return None
    return sorted(open_tasks, key=lambda item: (item.due_at is None, item.due_at or datetime.max))[0]


def _exports_dir() -> Path:
    exports_dir = get_settings().storage_path / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    return exports_dir


def _slugify(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_") or "value"


def _format_dt(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")
