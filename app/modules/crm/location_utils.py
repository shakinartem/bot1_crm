from __future__ import annotations

import re


FEDERAL_CITY_ALIASES = {
    "москва": ("Москва", "Москва"),
    "санкт-петербург": ("Санкт-Петербург", "Санкт-Петербург"),
    "санкт петербург": ("Санкт-Петербург", "Санкт-Петербург"),
}

REGION_PATTERNS = (
    re.compile(r"\b([А-ЯЁ][А-ЯЁа-яё\-\s]+?\s+область)\b"),
    re.compile(r"\b([А-ЯЁ][А-ЯЁа-яё\-\s]+?\s+край)\b"),
    re.compile(r"\b(Республика\s+[А-ЯЁ][А-ЯЁа-яё\-\s]+)\b"),
)
CITY_PATTERNS = (
    re.compile(r"\bг\.\s*о\.\s*город\s+([А-ЯЁ][А-ЯЁа-яё\-\s]+?)(?=,|$)", re.IGNORECASE),
    re.compile(r"\bгород\s+([А-ЯЁ][А-ЯЁа-яё\-\s]+?)(?=,|$)", re.IGNORECASE),
    re.compile(r"\bг\.\s*([А-ЯЁ][А-ЯЁа-яё\-\s]+?)(?=,|$)", re.IGNORECASE),
)


def extract_region_city_from_address(address: str) -> dict[str, str | None]:
    text = _normalize_spaces(address)
    if not text:
        return {"region": None, "city": None}

    region = _extract_region(text)
    city = _extract_city(text)

    if city:
        alias = FEDERAL_CITY_ALIASES.get(city.lower().replace("ё", "е"))
        if alias:
            city, region = alias

    if not region and city:
        alias = FEDERAL_CITY_ALIASES.get(city.lower().replace("ё", "е"))
        if alias:
            city, region = alias

    return {"region": region, "city": city}


def _extract_region(text: str) -> str | None:
    for pattern in REGION_PATTERNS:
        match = pattern.search(text)
        if match:
            return _clean_location_value(match.group(1))
    city = _extract_city(text)
    if city:
        alias = FEDERAL_CITY_ALIASES.get(city.lower().replace("ё", "е"))
        if alias:
            return alias[1]
    return None


def _extract_city(text: str) -> str | None:
    for pattern in CITY_PATTERNS:
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        return _clean_location_value(matches[-1].group(1))
    return None


def _clean_location_value(value: str) -> str:
    cleaned = _normalize_spaces(value).strip(" ,.")
    return cleaned[0].upper() + cleaned[1:] if cleaned else cleaned


def _normalize_spaces(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\n", " ")).strip()
