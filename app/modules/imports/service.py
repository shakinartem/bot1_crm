from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.modules.crm.constants import ContactType, InteractionType
from app.modules.crm.models import Company, ContactPoint, LeadInteraction
from app.modules.crm.schemas import CompanyCreate
from app.modules.crm.service import create_company
from app.modules.imports.dedupe import (
    CompanyIdentity,
    DeduplicationIndex,
    build_company_identity,
    normalize_phone,
    normalize_website,
)


ImportMode = Literal["skip", "update"]

CANONICAL_COLUMNS = [
    "name",
    "legal_name",
    "inn",
    "ogrn",
    "phone",
    "website",
    "address",
    "city",
    "region",
    "source",
    "notes",
    "social_links",
    "maps_url",
    "vk_url",
    "instagram_url",
    "telegram_url",
    "rating",
    "reviews_count",
]

COLUMN_ALIASES = {
    "name": {
        "name",
        "company",
        "company_name",
        "clinic",
        "clinic_name",
        "название",
        "компания",
        "клиника",
        "название клиники",
        "организация",
    },
    "legal_name": {
        "legal_name",
        "legal",
        "full_name",
        "юридическое название",
        "юр название",
        "юр. название",
        "полное название",
        "организация полное",
    },
    "inn": {"inn", "инн"},
    "ogrn": {"ogrn", "огрн"},
    "phone": {
        "phone",
        "phones",
        "телефон",
        "телефоны",
        "номер",
        "номер телефона",
        "contact_phone",
    },
    "website": {
        "website",
        "site",
        "url",
        "сайт",
        "сайт организации",
        "ссылка",
    },
    "address": {"address", "адрес", "юридический адрес", "фактический адрес"},
    "city": {"city", "город", "населенный пункт"},
    "region": {"region", "регион", "область", "республика"},
    "notes": {"notes", "note", "comment", "comments", "заметки", "комментарий", "комментарии"},
    "source": {"source", "источник", "откуда"},
    "social_links": {"social_links"},
    "maps_url": {"maps_url"},
    "vk_url": {"vk_url"},
    "instagram_url": {"instagram_url"},
    "telegram_url": {"telegram_url"},
    "rating": {"rating"},
    "reviews_count": {"reviews_count"},
}

DELIMITER_LABELS = {
    ",": "comma (,)",
    ";": "semicolon (;)",
    "\t": "tab",
}

HEADER_NORMALIZE_RE = re.compile(r"[\s._/-]+")
FILENAME_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(slots=True)
class PreparedImportRow:
    line_number: int
    mapped_data: dict[str, Any]
    preview_data: dict[str, str]
    identity: CompanyIdentity
    duplicate_reasons: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ImportPreview:
    file_name: str
    file_path: str | None
    encoding: str
    delimiter: str
    detected_columns: list[str]
    mapped_columns: dict[str, str]
    total_rows: int
    valid_rows: int
    empty_name_rows: int
    potential_duplicates: int
    preview_rows: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "file_path": self.file_path,
            "encoding": self.encoding,
            "delimiter": self.delimiter,
            "detected_columns": self.detected_columns,
            "mapped_columns": self.mapped_columns,
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "empty_name_rows": self.empty_name_rows,
            "potential_duplicates": self.potential_duplicates,
            "preview_rows": self.preview_rows,
            "warnings": self.warnings,
            "errors": self.errors,
        }


@dataclass(slots=True)
class ImportCommitReport:
    file_name: str
    file_path: str | None
    import_mode: ImportMode
    total_rows: int
    valid_rows: int
    added: int = 0
    updated: int = 0
    skipped_duplicates: int = 0
    error_rows: int = 0
    errors: list[str] = field(default_factory=list)
    added_company_ids: list[int] = field(default_factory=list)
    updated_company_ids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "file_path": self.file_path,
            "import_mode": self.import_mode,
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "added": self.added,
            "updated": self.updated,
            "skipped_duplicates": self.skipped_duplicates,
            "error_rows": self.error_rows,
            "errors": self.errors,
            "added_company_ids": self.added_company_ids,
            "updated_company_ids": self.updated_company_ids,
        }


def save_import_file(file_bytes: bytes, file_name: str | None) -> Path:
    settings = get_settings()
    imports_dir = settings.storage_path / "imports"
    imports_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file_name or "import.csv").name
    stem = FILENAME_SANITIZE_RE.sub("_", Path(safe_name).stem) or "import"
    suffix = Path(safe_name).suffix or ".csv"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = imports_dir / f"{timestamp}_{stem}{suffix}"
    file_path.write_bytes(file_bytes)
    return file_path


async def preview_companies_from_csv(
    session: AsyncSession,
    file_bytes: bytes,
    *,
    file_name: str | None = None,
    file_path: str | None = None,
) -> dict[str, Any]:
    _, preview = await _prepare_rows(
        session,
        file_bytes,
        file_name=file_name,
        file_path=file_path,
    )
    return preview.as_dict()


async def import_companies_from_csv(
    session: AsyncSession,
    file_bytes: bytes,
    *,
    file_name: str | None = None,
    file_path: str | None = None,
    import_mode: ImportMode = "skip",
) -> dict[str, Any]:
    rows, preview = await _prepare_rows(
        session,
        file_bytes,
        file_name=file_name,
        file_path=file_path,
    )
    report = ImportCommitReport(
        file_name=preview.file_name,
        file_path=preview.file_path,
        import_mode=import_mode,
        total_rows=preview.total_rows,
        valid_rows=preview.valid_rows,
    )
    report.errors.extend(preview.errors)
    report.error_rows += len(preview.errors)

    if preview.errors:
        return report.as_dict()

    dedupe_index = await _load_deduplication_index(session)

    for row in rows:
        if row.errors:
            report.error_rows += 1
            report.errors.append(f"Строка {row.line_number} — {'; '.join(row.errors)}")
            continue

        duplicate = dedupe_index.match(row.identity)
        if duplicate:
            if import_mode == "skip":
                report.skipped_duplicates += 1
                continue
            if duplicate.company_id is not None:
                try:
                    company = await _update_existing_company(
                        session,
                        duplicate.company_id,
                        row,
                        report.file_name,
                    )
                except Exception as exc:
                    await session.rollback()
                    report.error_rows += 1
                    report.errors.append(f"Строка {row.line_number} — {exc}")
                    continue
                report.updated += 1
                report.updated_company_ids.append(company.id)
                dedupe_index.add(_company_identity_from_model(company))
                continue

        try:
            company = await create_company(session, CompanyCreate(**row.mapped_data))
        except Exception as exc:
            await session.rollback()
            report.error_rows += 1
            report.errors.append(f"Строка {row.line_number} — {exc}")
            continue

        report.added += 1
        report.added_company_ids.append(company.id)
        dedupe_index.add(_company_identity_from_model(company))

    return report.as_dict()


async def _prepare_rows(
    session: AsyncSession,
    file_bytes: bytes,
    *,
    file_name: str | None,
    file_path: str | None,
) -> tuple[list[PreparedImportRow], ImportPreview]:
    decoded_text, encoding = decode_csv_content(file_bytes)
    if decoded_text is None:
        preview = ImportPreview(
            file_name=file_name or "import.csv",
            file_path=file_path,
            encoding="unknown",
            delimiter="unknown",
            detected_columns=[],
            mapped_columns={},
            total_rows=0,
            valid_rows=0,
            empty_name_rows=0,
            potential_duplicates=0,
            errors=["Не удалось определить кодировку CSV. Поддерживаются UTF-8 и Windows-1251."],
        )
        return [], preview

    delimiter = detect_delimiter(decoded_text)
    if delimiter is None:
        preview = ImportPreview(
            file_name=file_name or "import.csv",
            file_path=file_path,
            encoding=encoding,
            delimiter="unknown",
            detected_columns=[],
            mapped_columns={},
            total_rows=0,
            valid_rows=0,
            empty_name_rows=0,
            potential_duplicates=0,
            errors=["Не удалось определить разделитель. Используйте comma (,), semicolon (;) или tab."],
        )
        return [], preview

    reader = csv.DictReader(StringIO(decoded_text), delimiter=delimiter)
    fieldnames = reader.fieldnames or []
    if not fieldnames:
        preview = ImportPreview(
            file_name=file_name or "import.csv",
            file_path=file_path,
            encoding=encoding,
            delimiter=DELIMITER_LABELS[delimiter],
            detected_columns=[],
            mapped_columns={},
            total_rows=0,
            valid_rows=0,
            empty_name_rows=0,
            potential_duplicates=0,
            errors=["CSV не содержит заголовков."],
        )
        return [], preview

    header_mapping = map_headers(fieldnames)
    reverse_mapping = {canonical: header for header, canonical in header_mapping.items()}
    rows: list[PreparedImportRow] = []
    total_rows = 0
    valid_rows = 0
    empty_name_rows = 0
    potential_duplicates = 0
    warnings: list[str] = []

    if "name" not in reverse_mapping:
        warnings.append("Не найдена колонка названия компании. Проверьте заголовки CSV.")

    dedupe_index = await _load_deduplication_index(session)

    for row_number, raw_row in enumerate(reader, start=2):
        if _row_is_empty(raw_row):
            continue

        total_rows += 1
        mapped_row = _map_row(raw_row, header_mapping)
        preview_row = _build_preview_row(mapped_row)
        prepared = _prepare_row(row_number, mapped_row, preview_row)
        duplicate = dedupe_index.match(prepared.identity)
        if duplicate:
            prepared.duplicate_reasons = duplicate.reasons
            potential_duplicates += 1

        if prepared.mapped_data["name"]:
            valid_rows += 1
        else:
            empty_name_rows += 1

        rows.append(prepared)
        if prepared.mapped_data["name"]:
            dedupe_index.add(prepared.identity)

    preview = ImportPreview(
        file_name=file_name or "import.csv",
        file_path=file_path,
        encoding=encoding,
        delimiter=DELIMITER_LABELS[delimiter],
        detected_columns=fieldnames,
        mapped_columns=reverse_mapping,
        total_rows=total_rows,
        valid_rows=valid_rows,
        empty_name_rows=empty_name_rows,
        potential_duplicates=potential_duplicates,
        preview_rows=[
            {
                "line_number": row.line_number,
                "data": row.preview_data,
                "duplicate_reasons": row.duplicate_reasons,
            }
            for row in rows[:5]
        ],
        warnings=warnings,
    )
    return rows, preview


def decode_csv_content(file_bytes: bytes) -> tuple[str | None, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp1251", "windows-1251"):
        try:
            return file_bytes.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return None, "unknown"


def detect_delimiter(text: str) -> str | None:
    sample_lines = [line for line in text.splitlines()[:5] if line.strip()]
    sample = "\n".join(sample_lines)
    if not sample:
        return None

    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        counts = {delimiter: sample.count(delimiter) for delimiter in (",", ";", "\t")}
        non_zero = {delimiter: count for delimiter, count in counts.items() if count > 0}
        if len(non_zero) == 1:
            return next(iter(non_zero))
        if not non_zero:
            return None
        max_count = max(non_zero.values())
        best = [delimiter for delimiter, count in non_zero.items() if count == max_count]
        return best[0] if len(best) == 1 else None


def map_headers(headers: list[str]) -> dict[str, str]:
    alias_index = {
        normalize_header(alias): canonical
        for canonical, aliases in COLUMN_ALIASES.items()
        for alias in aliases | {canonical}
    }
    mapping: dict[str, str] = {}
    used_canonical: set[str] = set()

    for header in headers:
        normalized = normalize_header(header)
        canonical = alias_index.get(normalized)
        if canonical and canonical not in used_canonical:
            mapping[header] = canonical
            used_canonical.add(canonical)
    return mapping


def normalize_header(value: str) -> str:
    normalized = value.strip().lower().replace("ё", "е")
    normalized = HEADER_NORMALIZE_RE.sub(" ", normalized)
    return normalized.strip()


def _row_is_empty(row: dict[str, Any]) -> bool:
    return not any(str(value or "").strip() for value in row.values())


def _map_row(raw_row: dict[str, Any], header_mapping: dict[str, str]) -> dict[str, str | None]:
    mapped: dict[str, str | None] = {column: None for column in CANONICAL_COLUMNS}
    for header, canonical in header_mapping.items():
        mapped[canonical] = _clean_optional(raw_row.get(header))
    return mapped


def _build_preview_row(mapped_row: dict[str, str | None]) -> dict[str, str]:
    fields = ("name", "inn", "phone", "website", "city", "source")
    return {field: mapped_row.get(field) or "—" for field in fields}


def _prepare_row(
    line_number: int,
    mapped_row: dict[str, str | None],
    preview_row: dict[str, str],
) -> PreparedImportRow:
    data = dict(mapped_row)
    errors: list[str] = []

    if not data.get("name"):
        errors.append("не найдено название клиники")

    phone_value = data.get("phone")
    normalized_phone = normalize_phone(phone_value)
    if phone_value and normalized_phone is None:
        errors.append("некорректный телефон")

    if data.get("rating") is not None:
        try:
            data["rating"] = float(str(data["rating"]).replace(",", "."))
        except ValueError:
            errors.append("некорректный рейтинг")

    if data.get("reviews_count") is not None:
        try:
            data["reviews_count"] = int(str(data["reviews_count"]).strip())
        except ValueError:
            errors.append("некорректное число отзывов")

    identity = build_company_identity(
        name=data.get("name"),
        city=data.get("city"),
        inn=data.get("inn"),
        ogrn=data.get("ogrn"),
        phone=phone_value,
        website=data.get("website"),
    )

    return PreparedImportRow(
        line_number=line_number,
        mapped_data=data,
        preview_data=preview_row,
        identity=identity,
        errors=errors,
    )


def _clean_optional(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


async def _load_deduplication_index(session: AsyncSession) -> DeduplicationIndex:
    result = await session.execute(
        select(
            Company.id,
            Company.name,
            Company.city,
            Company.inn,
            Company.ogrn,
            Company.phone,
            Company.website,
        )
    )
    index = DeduplicationIndex()
    for company_id, name, city, inn, ogrn, phone, website in result.all():
        index.add(
            build_company_identity(
                company_id=company_id,
                name=name,
                city=city,
                inn=inn,
                ogrn=ogrn,
                phone=phone,
                website=website,
            )
        )
    return index


def _company_identity_from_model(company: Company) -> CompanyIdentity:
    return build_company_identity(
        company_id=company.id,
        name=company.name,
        city=company.city,
        inn=company.inn,
        ogrn=company.ogrn,
        phone=company.phone,
        website=company.website,
    )


async def _update_existing_company(
    session: AsyncSession,
    company_id: int,
    row: PreparedImportRow,
    file_name: str,
) -> Company:
    result = await session.execute(
        select(Company)
        .where(Company.id == company_id)
        .options(selectinload(Company.contacts))
    )
    company = result.scalar_one_or_none()
    if not company:
        raise ValueError("карточка для обновления не найдена")

    imported = row.mapped_data
    changed_fields: list[str] = []

    for field_name in ("legal_name", "inn", "ogrn", "address", "city", "region", "rating", "reviews_count"):
        incoming = imported.get(field_name)
        if incoming and not getattr(company, field_name):
            setattr(company, field_name, incoming)
            changed_fields.append(field_name)

    if imported.get("phone"):
        normalized_existing_phone = normalize_phone(company.phone)
        normalized_incoming_phone = normalize_phone(imported["phone"])
        if not company.phone:
            company.phone = imported["phone"]
            changed_fields.append("phone")
        elif normalized_incoming_phone and normalized_incoming_phone != normalized_existing_phone:
            await _add_contact_if_missing(
                session,
                company,
                ContactType.PHONE.value,
                imported["phone"],
                label="CSV import",
            )

    if imported.get("website"):
        normalized_existing_site = normalize_website(company.website)
        normalized_incoming_site = normalize_website(imported["website"])
        if not company.website:
            company.website = imported["website"]
            changed_fields.append("website")
        elif normalized_incoming_site and normalized_incoming_site != normalized_existing_site:
            await _add_contact_if_missing(
                session,
                company,
                ContactType.WEBSITE.value,
                imported["website"],
                label="CSV import",
            )

    for field_name in ("social_links", "maps_url", "vk_url", "instagram_url", "telegram_url"):
        incoming = imported.get(field_name)
        if incoming and not getattr(company, field_name):
            setattr(company, field_name, incoming)
            changed_fields.append(field_name)

    if imported.get("source") and not company.source:
        company.source = imported["source"]
        changed_fields.append("source")

    if imported.get("notes"):
        company.notes = _merge_notes(company.notes, imported["notes"])
        changed_fields.append("notes")

    summary = (
        f"Карточка обновлена из CSV ({file_name}, строка {row.line_number})."
        if changed_fields
        else f"CSV совпал с существующей карточкой ({file_name}, строка {row.line_number}) без новых полей."
    )
    session.add(company)
    session.add(
        LeadInteraction(
            company_id=company.id,
            type=InteractionType.NOTE.value,
            summary=summary,
            created_by="csv_import",
        )
    )
    await session.commit()
    await session.refresh(company)
    return company


def _merge_notes(existing: str | None, incoming: str) -> str:
    if not existing:
        return incoming
    if incoming in existing:
        return existing
    return f"{existing}\n\nCSV import:\n{incoming}"


async def _add_contact_if_missing(
    session: AsyncSession,
    company: Company,
    contact_type: str,
    value: str,
    *,
    label: str | None = None,
) -> None:
    normalized_value = normalize_phone(value) if contact_type == ContactType.PHONE.value else normalize_website(value)

    for contact in company.contacts:
        if contact.type != contact_type:
            continue
        existing_normalized = (
            normalize_phone(contact.value)
            if contact_type == ContactType.PHONE.value
            else normalize_website(contact.value)
        )
        if existing_normalized and existing_normalized == normalized_value:
            return

    session.add(
        ContactPoint(
            company_id=company.id,
            type=contact_type,
            value=value,
            label=label,
            is_primary=False,
        )
    )
