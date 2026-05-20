import csv
from dataclasses import dataclass, field
from io import StringIO

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models import Company
from app.modules.crm.schemas import CompanyCreate
from app.modules.crm.service import create_company


CSV_COLUMNS = {
    "name",
    "legal_name",
    "inn",
    "ogrn",
    "city",
    "region",
    "address",
    "phone",
    "website",
    "social_links",
    "maps_url",
    "vk_url",
    "instagram_url",
    "telegram_url",
    "rating",
    "reviews_count",
    "source",
    "notes",
}


@dataclass
class ImportReport:
    added: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, int | list[str]]:
        return {"added": self.added, "skipped": self.skipped, "errors": self.errors}


async def _is_duplicate(
    session: AsyncSession,
    *,
    name: str | None,
    phone: str | None,
    website: str | None,
    inn: str | None,
) -> bool:
    filters = []
    if phone:
        filters.append(Company.phone == phone)
    if website:
        filters.append(Company.website == website)
    if inn:
        filters.append(Company.inn == inn)
    if name:
        filters.append(func.lower(Company.name) == name.lower())
    if not filters:
        return False
    result = await session.execute(select(Company.id).where(or_(*filters)).limit(1))
    return result.scalar_one_or_none() is not None


async def import_companies_from_csv(session: AsyncSession, csv_text: str) -> dict[str, int | list[str]]:
    report = ImportReport()
    reader = csv.DictReader(StringIO(csv_text))
    if not reader.fieldnames:
        report.errors.append("CSV не содержит заголовков.")
        return report.as_dict()

    for row_number, row in enumerate(reader, start=2):
        try:
            data = {key: (row.get(key) or "").strip() or None for key in CSV_COLUMNS}
            if not data["name"]:
                report.errors.append(f"Строка {row_number}: не заполнено name.")
                continue
            if await _is_duplicate(session, name=data["name"], phone=data["phone"], website=data["website"], inn=data["inn"]):
                report.skipped += 1
                continue
            if data["rating"] is not None:
                data["rating"] = float(str(data["rating"]).replace(",", "."))
            if data["reviews_count"] is not None:
                data["reviews_count"] = int(data["reviews_count"])
            await create_company(session, CompanyCreate(**data))
            report.added += 1
        except Exception as exc:
            report.errors.append(f"Строка {row_number}: {exc}")

    return report.as_dict()
