from __future__ import annotations

import re


_FEDERAL_CITY_ALIASES = {
    "москва": ("Москва", "Москва"),
    "санкт-петербург": ("Санкт-Петербург", "Санкт-Петербург"),
    "санкт петербург": ("Санкт-Петербург", "Санкт-Петербург"),
}


def extract_region_city_from_address(address: str) -> dict[str, str | None]:
    text = " ".join((address or "").replace("\n", " ").split())
    if not text:
        return {"region": None, "city": None}

    city = _extract_city(text)
    region = _extract_region(text)

    if city:
        alias = _FEDERAL_CITY_ALIASES.get(city.lower().replace("ё", "е"))
        if alias:
            city, region = alias

    return {"region": region, "city": city}


def _extract_city(text: str) -> str | None:
    for pattern in (
        r"\bг\.\s*([А-ЯA-ZЁ][А-ЯA-ZЁа-яa-zё\-\s]+?)(?=,|$)",
        r"\bгород\s+([А-ЯA-ZЁ][А-ЯA-ZЁа-яa-zё\-\s]+?)(?=,|$)",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _clean_location_value(match.group(1))
    return None


def _extract_region(text: str) -> str | None:
    for pattern in (
        r"([А-ЯA-ZЁ][А-ЯA-ZЁа-яa-zё\-\s]+?\s+область)\b",
        r"([А-ЯA-ZЁ][А-ЯA-ZЁа-яa-zё\-\s]+?\s+край)\b",
        r"(Республика\s+[А-ЯA-ZЁ][А-ЯA-ZЁа-яa-zё\-\s]+)\b",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _clean_location_value(match.group(1))
    return None


def _clean_location_value(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value or "").strip(" ,.")
    if not cleaned:
        return cleaned
    return cleaned[0].upper() + cleaned[1:]
