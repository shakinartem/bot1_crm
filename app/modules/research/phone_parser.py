from __future__ import annotations

import re


PHONE_CANDIDATE_RE = re.compile(r"(?:(?:tel:)?\+?7|8)[\d\-\(\)\s]{9,}")
LETTER_RE = re.compile(r"[A-Za-zА-Яа-я]")


def normalize_phone_ru(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text or LETTER_RE.search(text):
        return None
    digits = "".join(char for char in text if char.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 11 and digits.startswith("7"):
        return f"+{digits}"
    return None


def extract_phones_from_text(text: str) -> list[str]:
    phones: list[str] = []
    seen: set[str] = set()
    for match in PHONE_CANDIDATE_RE.finditer(text or ""):
        normalized = normalize_phone_ru(match.group(0))
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        phones.append(normalized)
    return phones


def extract_phones_from_html(html: str) -> list[str]:
    return extract_phones_from_text(html or "")


__all__ = [
    "extract_phones_from_html",
    "extract_phones_from_text",
    "normalize_phone_ru",
]
