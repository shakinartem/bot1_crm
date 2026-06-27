from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from io import StringIO
from typing import Any, Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.constants import ContactType, InteractionType
from app.modules.crm.models import Company, ContactPoint, LeadInteraction
from app.modules.crm.schemas import CompanyCreate
from app.modules.crm.service import create_company
from app.modules.imports.dedupe import build_company_identity
from app.modules.lead_fit.service import recalculate_companies_lead_fit
from app.modules.research.phone_parser import normalize_phone_ru
from app.modules.research.website_resolver import is_denied_website_url, normalize_website_url


RowStatus = Literal["imported", "updated", "duplicate", "skipped", "error"]
ImportMode = Literal["create_only", "update_existing", "upsert"]

EMPTY_VALUES = {"", "-", "—", "нет", "н/д", "н/а", "no", "n/a", "none", "null"}

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# --- Extended column aliases for CSV import ---

CSV_COLUMN_ALIASES: dict[str, set[str]] = {
    "legal_name": {
        "legal_name", "legal", "full_name", "юридическое название",
        "юр название", "юр. название", "полное название",
        "организация полное", "юридическое имя",
    },
    "display_name": {
        "display_name", "short_name", "name", "company_name",
        "company", "клиника", "название", "компания",
        "название компании", "организация", "наименование",
        "краткое наименование",
    },
    "inn": {"inn", "инн", "иин", "иинн"},
    "ogrn": {"ogrn", "огрн", "оогрн"},
    "city": {"city", "город", "населённый пункт", "населенный пункт", "г."},
    "region": {"region", "регион", "область", "республика", "край", "округ"},
    "address": {
        "address", "адрес", "юридический адрес", "фактический адрес",
        "почтовый адрес", "адрес местонахождения",
    },
    "phone": {
        "phone", "phones", "телефон", "телефоны", "номер",
        "номер телефона", "contact_phone", "контактный телефон",
        "тел", "тел.",
    },
    "email": {
        "email", "e-mail", "e_mail", "почта", "эл. почта",
        "электронная почта", "contact_email",
    },
    "website": {
        "website", "site", "url", "сайт", "сайт организации",
        "ссылка", "вебсайт", "web_site", "web-site",
    },
    "checko_profile_url": {
        "checko_profile_url", "checko_url", "checko", "ссылка checko",
        "checko ссылка", "checko_profile", "checko_link",
    },
    "yandex_maps_url": {
        "yandex_maps_url", "map_url", "maps", "карта", "яндекс карты",
        "ссылка на карты", "maps_url", "yandex_map",
    },
    "status": {"status", "статус", "состояние"},
    "priority": {"priority", "приоритет", "приоритетность"},
    "notes": {
        "notes", "note", "заметки", "комментарий", "комментарии",
        "примечание", "примечания",
    },
    "source": {"source", "источник", "откуда"},
}

HEADER_NORMALIZE_RE = re.compile(r"[\s._/-]+")


@dataclass(slots=True)
class RowResult:
    row_number: int
    status: RowStatus
    company_id: int | None = None
    inn: str | None = None
    legal_name: str | None = None
    message: str = ""


@dataclass(slots=True)
class CsvCompanyImportResult:
    total_rows: int = 0
    imported_count: int = 0
    updated_count: int = 0
    duplicate_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    warnings: list[str] = field(default_factory=list)
    row_results: list[RowResult] = field(default_factory=list)


# ============================================================
# 1. CSV dialect detection
# ============================================================


def detect_csv_dialect(file_bytes: bytes) -> tuple[str | None, str, str | None]:
    """Detect encoding and delimiter from CSV bytes.

    Returns (decoded_text, encoding, delimiter) or (None, encoding, None) on failure.
    """
    decoded_text, encoding = _decode_csv(file_bytes)
    if decoded_text is None:
        return None, encoding or "unknown", None

    delimiter = _detect_delimiter(decoded_text)
    if delimiter is None:
        return None, encoding or "unknown", None

    return decoded_text, encoding or "utf-8", delimiter


def _decode_csv(file_bytes: bytes) -> tuple[str | None, str | None]:
    for encoding in ("utf-8-sig", "utf-8", "cp1251", "windows-1251"):
        try:
            return file_bytes.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return None, None


def _detect_delimiter(text: str) -> str | None:
    sample_lines = [line for line in text.splitlines()[:5] if line.strip()]
    sample = "\n".join(sample_lines)
    if not sample:
        return None

    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in (",", ";", "\t")}
        non_zero = {d: c for d, c in counts.items() if c > 0}
        if len(non_zero) == 1:
            return next(iter(non_zero))
        if not non_zero:
            return None
        max_count = max(non_zero.values())
        best = [d for d, c in non_zero.items() if c == max_count]
        return best[0] if len(best) == 1 else None


# ============================================================
# 2. Header normalization and mapping
# ============================================================


def normalize_csv_headers(headers: list[str]) -> dict[str, str]:
    """Map CSV headers to canonical field names.

    Returns dict mapping canonical_name -> original_header.
    """
    alias_index: dict[str, str] = {}
    for canonical, aliases in CSV_COLUMN_ALIASES.items():
        normalized_aliases = {_normalize_header(a) for a in aliases | {canonical}}
        for na in normalized_aliases:
            alias_index[na] = canonical

    mapping: dict[str, str] = {}
    used: set[str] = set()

    for header in headers:
        normalized = _normalize_header(header)
        canonical = alias_index.get(normalized)
        if canonical and canonical not in used:
            mapping[canonical] = header
            used.add(canonical)

    return mapping


def _normalize_header(value: str) -> str:
    normalized = value.strip().lower().replace("ё", "е")
    normalized = HEADER_NORMALIZE_RE.sub(" ", normalized)
    return normalized.strip()


# ============================================================
# 3. CSV parsing
# ============================================================


def parse_company_csv(file_bytes: bytes) -> tuple[list[dict[str, Any]], list[str], int]:
    """Parse CSV bytes into list of dicts with canonical field names.

    Returns (parsed_rows, warnings, total_rows).
    Empty rows are skipped.
    """
    decoded_text, encoding, delimiter = detect_csv_dialect(file_bytes)
    warnings: list[str] = []

    if decoded_text is None:
        reason = "Не удалось определить кодировку или разделитель CSV"
        if encoding:
            reason = f"Не удалось прочитать файл в {encoding}"
        warnings.append(reason)
        return [], warnings, 0

    reader = csv.DictReader(StringIO(decoded_text), delimiter=delimiter)
    fieldnames = reader.fieldnames or []
    if not fieldnames:
        warnings.append("CSV не содержит заголовков")
        return [], warnings, 0

    header_mapping = normalize_csv_headers(fieldnames)

    if "display_name" not in header_mapping:
        warnings.append("Не найдена колонка названия компании (name/company/название)")

    parsed_rows: list[dict[str, Any]] = []
    total_rows = 0

    for row_number, raw_row in enumerate(reader, start=2):
        if _row_is_empty(raw_row):
            continue

        total_rows += 1
        mapped = _map_row(raw_row, header_mapping)
        cleaned = _clean_row(mapped)
        parsed_rows.append(cleaned)

    return parsed_rows, warnings, total_rows


def _row_is_empty(row: dict[str, Any]) -> bool:
    return not any(str(v or "").strip() for v in row.values())


def _map_row(raw: dict[str, Any], mapping: dict[str, str]) -> dict[str, str | None]:
    result: dict[str, str | None] = {canonical: None for canonical in CSV_COLUMN_ALIASES}
    for canonical, header in mapping.items():
        val = raw.get(header)
        result[canonical] = str(val).strip() if val else None
    return result


def _clean_row(row: dict[str, str | None]) -> dict[str, Any]:
    """Clean a parsed row: trim, normalize empties, validate email, etc."""
    cleaned: dict[str, Any] = {}

    for key, value in row.items():
        if value is None:
            cleaned[key] = None
            continue

        value = value.strip()

        # Treat empty-like values as None
        if not value or value.lower() in EMPTY_VALUES:
            cleaned[key] = None
            continue

        if key == "phone":
            normalized = normalize_phone_ru(value)
            cleaned[key] = normalized if normalized else value
        elif key == "email":
            if EMAIL_RE.match(value):
                cleaned[key] = value.lower()
            else:
                cleaned[key] = None
        elif key == "website":
            cleaned[key] = value  # Will be processed post-parse
        elif key in ("inn", "ogrn"):
            cleaned[key] = value
        else:
            cleaned[key] = value

    return cleaned


# ============================================================
# 4. CSV preview
# ============================================================


@dataclass(slots=True)
class CsvPreviewResult:
    detected_columns: list[str] = field(default_factory=list)
    total_rows: int = 0
    sample_rows: list[dict[str, Any]] = field(default_factory=list)
    inn_count: int = 0
    phone_count: int = 0
    website_count: int = 0
    warnings: list[str] = field(default_factory=list)
    can_import: bool = True


def preview_csv(file_bytes: bytes) -> CsvPreviewResult:
    """Generate a preview of the CSV without importing."""
    decoded_text, encoding, delimiter = detect_csv_dialect(file_bytes)
    result = CsvPreviewResult()

    if decoded_text is None:
        result.can_import = False
        reason = "Не удалось определить кодировку или разделитель CSV"
        if encoding:
            reason = f"Не удалось прочитать файл в {encoding}"
        result.warnings.append(reason)
        return result

    reader = csv.DictReader(StringIO(decoded_text), delimiter=delimiter)
    fieldnames = reader.fieldnames or []
    if not fieldnames:
        result.can_import = False
        result.warnings.append("CSV не содержит заголовков")
        return result

    header_mapping = normalize_csv_headers(fieldnames)
    result.detected_columns = fieldnames

    if "display_name" not in header_mapping:
        result.warnings.append("Не найдена колонка названия компании")

    sample: list[dict[str, Any]] = []
    total_rows = 0
    inn_count = 0
    phone_count = 0
    website_count = 0

    for row_number, raw_row in enumerate(reader, start=2):
        if _row_is_empty(raw_row):
            continue
        total_rows += 1
        mapped = _map_row(raw_row, header_mapping)

        if mapped.get("inn"):
            inn_count += 1
        if mapped.get("phone"):
            phone_count += 1
        if mapped.get("website"):
            website_count += 1

        if len(sample) < 5:
            sample.append(
                {
                    "row_number": row_number,
                    "legal_name": mapped.get("legal_name") or "—",
                    "display_name": mapped.get("display_name") or "—",
                    "inn": mapped.get("inn") or "—",
                    "phone": mapped.get("phone") or "—",
                    "website": mapped.get("website") or "—",
                    "city": mapped.get("city") or "—",
                }
            )

    result.total_rows = total_rows
    result.sample_rows = sample
    result.inn_count = inn_count
    result.phone_count = phone_count
    result.website_count = website_count
    result.can_import = total_rows > 0 and "display_name" in header_mapping

    return result


# ============================================================
# 5. Async import from parsed CSV
# ============================================================


async def import_companies_from_csv(
    session: AsyncSession,
    file_bytes: bytes,
    mode: ImportMode = "upsert",
    source: str = "csv_upload",
    imported_by_user_id: int | None = None,
) -> CsvCompanyImportResult:
    """Import companies from CSV bytes into the database.

    Args:
        session: Async SQLAlchemy session.
        file_bytes: Raw CSV file bytes.
        mode: Import mode - create_only, update_existing, or upsert.
        source: Source label for the import.
        imported_by_user_id: Optional user ID who triggered the import.

    Returns:
        CsvCompanyImportResult with detailed results per row.
    """
    parsed_rows, warnings, total_rows = parse_company_csv(file_bytes)
    result = CsvCompanyImportResult(total_rows=total_rows, warnings=warnings)

    if not parsed_rows:
        result.error_count = total_rows or 0
        return result

    company_ids_for_lead_fit: list[int] = []

    for row_data in parsed_rows:
        row_number = row_data.get("_row_number", 0)
        display_name = row_data.get("display_name")

        # Skip rows without a name
        if not display_name:
            result.skipped_count += 1
            result.row_results.append(
                RowResult(
                    row_number=row_number or 0,
                    status="skipped",
                    message="Не указано название компании",
                )
            )
            continue

        try:
            outcome = await _process_one_row(
                session,
                row_data,
                mode=mode,
                source=source,
                imported_by_user_id=imported_by_user_id,
            )
            result.row_results.append(outcome)

            if outcome.status == "imported":
                result.imported_count += 1
                if outcome.company_id:
                    company_ids_for_lead_fit.append(outcome.company_id)
            elif outcome.status == "updated":
                result.updated_count += 1
                if outcome.company_id:
                    company_ids_for_lead_fit.append(outcome.company_id)
            elif outcome.status == "duplicate":
                result.duplicate_count += 1
            elif outcome.status == "skipped":
                result.skipped_count += 1
            elif outcome.status == "error":
                result.error_count += 1
        except Exception as exc:
            result.error_count += 1
            result.row_results.append(
                RowResult(
                    row_number=row_number or 0,
                    status="error",
                    message=str(exc)[:200],
                )
            )

    # Post-import: run lead fit scoring for created/updated companies
    if company_ids_for_lead_fit:
        try:
            await recalculate_companies_lead_fit(session, company_ids_for_lead_fit)
        except Exception as exc:
            result.warnings.append(f"Lead fit scoring error: {exc}")

    return result


async def _process_one_row(
    session: AsyncSession,
    row_data: dict[str, Any],
    *,
    mode: ImportMode,
    source: str,
    imported_by_user_id: int | None,
) -> RowResult:
    """Process a single CSV row: find duplicate, create or update."""
    row_number = row_data.get("_row_number", 0)
    display_name = (row_data.get("display_name") or "").strip()
    legal_name = (row_data.get("legal_name") or "").strip() or None
    inn = (row_data.get("inn") or "").strip() or None
    ogrn = (row_data.get("ogrn") or "").strip() or None
    phone = row_data.get("phone") or None
    website = row_data.get("website") or None
    email = row_data.get("email") or None
    city = (row_data.get("city") or "").strip() or None
    region = (row_data.get("region") or "").strip() or None
    address = (row_data.get("address") or "").strip() or None
    checko_url = row_data.get("checko_profile_url") or None
    maps_url = row_data.get("yandex_maps_url") or None
    status = row_data.get("status") or None
    priority = row_data.get("priority") or None
    notes = row_data.get("notes") or None
    csv_source = row_data.get("source") or source

    # Website denylist check
    clean_website = None
    website_in_denylist = False
    if website:
        normalized_site = normalize_website_url(website)
        if normalized_site and is_denied_website_url(normalized_site):
            website_in_denylist = True
        else:
            clean_website = normalized_site or website

    # Checko URL validation
    clean_checko_url = None
    if checko_url:
        clean_checko_url = checko_url.strip()
        if clean_checko_url and "checko" in clean_checko_url.lower():
            pass  # valid Checko URL
        elif clean_checko_url:
            clean_checko_url = None  # Not a Checko URL, ignore

    # Build identity for deduplication
    identity = build_company_identity(
        name=display_name,
        city=city,
        inn=inn,
        ogrn=ogrn,
        phone=phone,
        website=clean_website,
    )

    # Deduplication logic
    existing = await _find_duplicate(session, identity)

    if existing:
        if mode == "create_only":
            return RowResult(
                row_number=row_number,
                status="duplicate",
                company_id=existing.id,
                inn=inn,
                legal_name=legal_name or display_name,
                message=f"Дубликат: компания #{existing.id} — {existing.name}",
            )

        # update_existing or upsert
        company = await _update_company(
            session,
            existing,
            row_data=row_data,
            clean_website=clean_website,
            website_in_denylist=website_in_denylist,
            clean_checko_url=clean_checko_url,
            maps_url=maps_url,
            email=email,
            source=csv_source,
            imported_by_user_id=imported_by_user_id,
        )
        return RowResult(
            row_number=row_number,
            status="updated",
            company_id=company.id,
            inn=inn,
            legal_name=legal_name or display_name,
            message=f"Обновлена компания #{company.id}",
        )

    # No duplicate — create new company
    company = await _create_company_from_row(
        session,
        row_data=row_data,
        display_name=display_name,
        legal_name=legal_name,
        inn=inn,
        ogrn=ogrn,
        phone=phone,
        email=email,
        clean_website=clean_website,
        website_in_denylist=website_in_denylist,
        clean_checko_url=clean_checko_url,
        maps_url=maps_url,
        city=city,
        region=region,
        address=address,
        status=status,
        priority=priority,
        notes=notes,
        source=csv_source,
        imported_by_user_id=imported_by_user_id,
    )
    return RowResult(
        row_number=row_number,
        status="imported",
        company_id=company.id,
        inn=inn,
        legal_name=legal_name or display_name,
        message=f"Создана компания #{company.id}",
    )


async def _find_duplicate(
    session: AsyncSession,
    identity,
) -> Company | None:
    """Find duplicate company using INN, OGRN, phone, website, or name+city."""
    conditions = []

    if identity.inn:
        conditions.append(Company.inn == identity.inn)
    if identity.ogrn:
        conditions.append(Company.ogrn == identity.ogrn)
    if identity.phone:
        conditions.append(Company.phone == identity.phone)
    if identity.website:
        conditions.append(Company.website == identity.website)

    if identity.name and identity.city:
        conditions.append(
            Company.name.ilike(f"%{identity.name}%") & Company.city.ilike(f"%{identity.city}%")
        )

    if not conditions:
        return None

    result = await session.execute(
        select(Company)
        .where(or_(*conditions))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _create_company_from_row(
    session: AsyncSession,
    *,
    row_data: dict[str, Any],
    display_name: str,
    legal_name: str | None,
    inn: str | None,
    ogrn: str | None,
    phone: str | None,
    email: str | None,
    clean_website: str | None,
    website_in_denylist: bool,
    clean_checko_url: str | None,
    maps_url: str | None,
    city: str | None,
    region: str | None,
    address: str | None,
    status: str | None,
    priority: str | None,
    notes: str | None,
    source: str,
    imported_by_user_id: int | None,
) -> Company:
    """Create a new company from parsed CSV row data."""
    company_data = {
        "name": display_name,
        "legal_name": legal_name,
        "inn": inn,
        "ogrn": ogrn,
        "phone": phone or None,
        "city": city,
        "region": region,
        "address": address,
        "checko_profile_url": clean_checko_url,
        "source": source,
    }

    # Website: only save if not in denylist
    if clean_website and not website_in_denylist:
        company_data["website"] = clean_website

    # Priority
    if priority:
        company_data["priority"] = priority

    # Status
    if status:
        company_data["status"] = status

    # Notes
    if notes:
        company_data["notes"] = notes

    try:
        company = await create_company(session, CompanyCreate(**company_data))
    except Exception as exc:
        raise ValueError(f"Ошибка создания компании: {exc}") from exc

    # Save maps_url as contact point
    if maps_url:
        session.add(
            ContactPoint(
                company_id=company.id,
                type=ContactType.MAP_URL.value,
                value=maps_url,
                label="csv_import",
                is_primary=True,
            )
        )
        company.maps_url = maps_url

    # Save email as contact point
    if email:
        session.add(
            ContactPoint(
                company_id=company.id,
                type=ContactType.EMAIL.value,
                value=email,
                label="csv_import",
                is_primary=True,
            )
        )

    # Save denylisted website as reference
    if website_in_denylist and clean_website:
        session.add(
            ContactPoint(
                company_id=company.id,
                type=ContactType.WEBSITE.value,
                value=clean_website,
                label="csv_import_denied",
                is_primary=False,
            )
        )

    # Log import interaction
    session.add(
        LeadInteraction(
            company_id=company.id,
            type=InteractionType.NOTE.value,
            summary=f"Импортирована из CSV (источник: {source})",
            created_by="csv_import",
        )
    )

    await session.commit()
    await session.refresh(company)
    return company


async def _update_company(
    session: AsyncSession,
    company: Company,
    *,
    row_data: dict[str, Any],
    clean_website: str | None,
    website_in_denylist: bool,
    clean_checko_url: str | None,
    maps_url: str | None,
    email: str | None,
    source: str,
    imported_by_user_id: int | None,
) -> Company:
    """Update an existing company with non-empty values from CSV."""
    changed: list[str] = []

    # Update text fields only if incoming is not empty and existing is empty
    for field_name in ("legal_name", "inn", "ogrn", "city", "region", "address"):
        incoming = row_data.get(field_name)
        if incoming and not getattr(company, field_name):
            setattr(company, field_name, incoming)
            changed.append(field_name)

    # Phone
    phone = row_data.get("phone")
    if phone and not company.phone:
        company.phone = phone
        changed.append("phone")

    # Website
    if clean_website and not website_in_denylist and not company.website:
        company.website = clean_website
        changed.append("website")

    # Checko URL
    if clean_checko_url and not company.checko_profile_url:
        company.checko_profile_url = clean_checko_url
        changed.append("checko_profile_url")

    # Maps URL
    if maps_url and not company.maps_url:
        company.maps_url = maps_url
        changed.append("maps_url")

    # Priority
    priority = row_data.get("priority")
    if priority and not company.priority:
        company.priority = priority
        changed.append("priority")

    # Status
    status = row_data.get("status")
    if status and not company.status:
        company.status = status
        changed.append("status")

    # Notes (append)
    notes = row_data.get("notes")
    if notes:
        if company.notes:
            company.notes = f"{company.notes}\n\nCSV import:\n{notes}"
        else:
            company.notes = notes
        changed.append("notes")

    # Source
    if not company.source:
        company.source = source

    # Save email as contact point
    if email:
        existing_email = await session.execute(
            select(ContactPoint).where(
                ContactPoint.company_id == company.id,
                ContactPoint.type == ContactType.EMAIL.value,
                ContactPoint.value == email,
            )
        )
        if not existing_email.scalar_one_or_none():
            session.add(
                ContactPoint(
                    company_id=company.id,
                    type=ContactType.EMAIL.value,
                    value=email,
                    label="csv_import",
                    is_primary=False,
                )
            )

    # Save maps_url as contact point
    if maps_url:
        existing_map = await session.execute(
            select(ContactPoint).where(
                ContactPoint.company_id == company.id,
                ContactPoint.type == ContactType.MAP_URL.value,
                ContactPoint.value == maps_url,
            )
        )
        if not existing_map.scalar_one_or_none():
            session.add(
                ContactPoint(
                    company_id=company.id,
                    type=ContactType.MAP_URL.value,
                    value=maps_url,
                    label="csv_import",
                    is_primary=False,
                )
            )

    summary = (
        f"Карточка обновлена из CSV (источник: {source})."
        if changed
        else f"CSV совпал с существующей карточкой без новых полей (источник: {source})."
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


__all__ = [
    "CsvCompanyImportResult",
    "CsvPreviewResult",
    "RowResult",
    "ImportMode",
    "detect_csv_dialect",
    "normalize_csv_headers",
    "parse_company_csv",
    "preview_csv",
    "import_companies_from_csv",
]