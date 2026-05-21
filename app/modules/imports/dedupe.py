from __future__ import annotations

import re
from dataclasses import dataclass, field


LEGAL_PREFIX_RE = re.compile(r"^(?:ооо|ип|ао|зао|оао|пао)\s+")
QUOTE_TRANSLATION = str.maketrans("", "", "\"'`«»")
WHITESPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class CompanyIdentity:
    company_id: int | None = None
    name: str | None = None
    city: str | None = None
    inn: str | None = None
    ogrn: str | None = None
    phone: str | None = None
    website: str | None = None


@dataclass(slots=True)
class DuplicateMatch:
    company_id: int | None
    reasons: list[str] = field(default_factory=list)


class DeduplicationIndex:
    def __init__(self) -> None:
        self._by_inn: dict[str, CompanyIdentity] = {}
        self._by_ogrn: dict[str, CompanyIdentity] = {}
        self._by_phone: dict[str, CompanyIdentity] = {}
        self._by_website: dict[str, CompanyIdentity] = {}
        self._by_name_city: dict[tuple[str, str], CompanyIdentity] = {}

    def add(self, identity: CompanyIdentity) -> None:
        if identity.inn:
            self._by_inn.setdefault(identity.inn, identity)
        if identity.ogrn:
            self._by_ogrn.setdefault(identity.ogrn, identity)
        if identity.phone:
            self._by_phone.setdefault(identity.phone, identity)
        if identity.website:
            self._by_website.setdefault(identity.website, identity)
        if identity.name and identity.city:
            self._by_name_city.setdefault((identity.name, identity.city), identity)

    def match(self, identity: CompanyIdentity) -> DuplicateMatch | None:
        reasons: list[str] = []
        company_id: int | None = None

        def capture(candidate: CompanyIdentity | None, reason: str) -> None:
            nonlocal company_id
            if not candidate:
                return
            reasons.append(reason)
            if company_id is None:
                company_id = candidate.company_id

        if identity.inn:
            capture(self._by_inn.get(identity.inn), "INN")
        if identity.ogrn:
            capture(self._by_ogrn.get(identity.ogrn), "OGRN")
        if identity.website:
            capture(self._by_website.get(identity.website), "website")
        if identity.phone:
            capture(self._by_phone.get(identity.phone), "phone")
        if identity.name and identity.city:
            capture(self._by_name_city.get((identity.name, identity.city)), "name+city")

        if not reasons:
            return None
        return DuplicateMatch(company_id=company_id, reasons=reasons)


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(char for char in value if char.isdigit())
    if not digits:
        return None
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return digits


def normalize_website(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    normalized = re.sub(r"^https?://", "", normalized)
    normalized = re.sub(r"^www\.", "", normalized)
    normalized = normalized.rstrip("/")
    if "/" in normalized:
        normalized = normalized.split("/", 1)[0]
    if not normalized:
        return None
    return normalized


def normalize_company_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower().replace("ё", "е")
    normalized = normalized.translate(QUOTE_TRANSLATION)
    normalized = LEGAL_PREFIX_RE.sub("", normalized)
    normalized = WHITESPACE_RE.sub(" ", normalized)
    normalized = normalized.strip(" ,.-")
    return normalized or None


def normalize_city(value: str | None) -> str | None:
    if not value:
        return None
    normalized = WHITESPACE_RE.sub(" ", value.strip().lower().replace("ё", "е"))
    return normalized or None


def build_company_identity(
    *,
    company_id: int | None = None,
    name: str | None = None,
    city: str | None = None,
    inn: str | None = None,
    ogrn: str | None = None,
    phone: str | None = None,
    website: str | None = None,
) -> CompanyIdentity:
    return CompanyIdentity(
        company_id=company_id,
        name=normalize_company_name(name),
        city=normalize_city(city),
        inn=(inn or "").strip() or None,
        ogrn=(ogrn or "").strip() or None,
        phone=normalize_phone(phone),
        website=normalize_website(website),
    )
