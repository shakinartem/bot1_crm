from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin


CHECKO_BASE_URL = "https://checko.ru"
PHONE_RE = re.compile(r"\+?\d[\d\-\s()]{8,}\d")
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.IGNORECASE)
TAG_RE = re.compile(r"(?s)<[^>]+>")
LINK_RE = re.compile(r"""<a[^>]+href=["'](?P<href>[^"']+)["'][^>]*>(?P<label>.*?)</a>""", re.IGNORECASE | re.DOTALL)
JSON_LD_RE = re.compile(
    r"""<script[^>]+type=["']application/ld\+json["'][^>]*>(?P<body>.*?)</script>""",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(slots=True)
class CheckoFounder:
    full_name: str
    role: str | None = None
    inn: str | None = None
    share_text: str | None = None


@dataclass(slots=True)
class CheckoProfileData:
    short_name: str | None = None
    legal_name: str | None = None
    inn: str | None = None
    ogrn: str | None = None
    kpp: str | None = None
    okpo: str | None = None
    legal_address: str | None = None
    status: str | None = None
    okved_code: str | None = None
    okved_name: str | None = None
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    websites: list[str] = field(default_factory=list)
    telegram_links: list[str] = field(default_factory=list)
    vk_links: list[str] = field(default_factory=list)
    instagram_links: list[str] = field(default_factory=list)
    whatsapp_links: list[str] = field(default_factory=list)
    youtube_links: list[str] = field(default_factory=list)
    map_links: list[str] = field(default_factory=list)
    director_name: str | None = None
    director_role: str | None = None
    director_inn: str | None = None
    director_since_date: str | None = None
    founders: list[CheckoFounder] = field(default_factory=list)
    checko_profile_url: str | None = None
    text_excerpt: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CheckoListItem:
    legal_name: str | None = None
    short_name: str | None = None
    profile_url: str | None = None
    address: str | None = None
    director_name: str | None = None
    director_role: str | None = None
    registration_date: str | None = None
    status: str | None = None
    warnings: list[str] = field(default_factory=list)


def parse_checko_list_page(html_text: str, base_url: str = CHECKO_BASE_URL) -> list[CheckoListItem]:
    items: list[CheckoListItem] = []
    for match in LINK_RE.finditer(html_text):
        href = html.unescape(match.group("href")).strip()
        if "/company/" not in href:
            continue
        label = _clean_text(match.group("label"))
        if not label:
            continue
        block = _extract_nearby_block(html_text, match.start(), match.end())
        item = CheckoListItem(
            legal_name=label,
            short_name=label,
            profile_url=urljoin(base_url, href),
            address=_extract_labeled_value(block, ["Адрес"]),
            director_name=_extract_labeled_value(block, ["Директор", "Генеральный директор", "Руководитель"]),
            director_role=_extract_director_role(block),
            registration_date=_extract_labeled_value(block, ["Дата регистрации"]),
            status=_extract_status(block),
            warnings=[],
        )
        if not item.address:
            item.warnings.append("missing_address")
        items.append(item)
    return _dedupe_list_items(items)


def parse_checko_profile_page(html_text: str, base_url: str = CHECKO_BASE_URL) -> CheckoProfileData:
    lines = _html_to_lines(html_text)
    text = "\n".join(lines)
    profile = CheckoProfileData(
        short_name=_extract_tag_text(html_text, "h1") or _extract_labeled_value(text, ["Краткое наименование"]),
        legal_name=_extract_labeled_value(text, ["Полное наименование", "Юридическое наименование"]) or _extract_title_name(html_text),
        inn=_extract_digits_value(text, ["ИНН"]),
        ogrn=_extract_digits_value(text, ["ОГРН"]),
        kpp=_extract_digits_value(text, ["КПП"]),
        okpo=_extract_digits_value(text, ["ОКПО"]),
        legal_address=_extract_labeled_value(text, ["Юридический адрес", "Адрес"]),
        status=_extract_labeled_value(text, ["Статус"]) or _extract_status(text),
        okved_code=_extract_okved_code(text),
        okved_name=_extract_okved_name(text),
        phones=_dedupe(PHONE_RE.findall(text)),
        emails=_dedupe(EMAIL_RE.findall(text)),
        checko_profile_url=_extract_canonical_url(html_text) or _extract_jsonld_url(html_text),
        text_excerpt=text[:1500] or None,
    )
    for href, label in _extract_links(html_text, base_url):
        lowered = href.lower()
        if "telegram" in lowered or "t.me/" in lowered:
            profile.telegram_links.append(href)
        elif "vk.com" in lowered:
            profile.vk_links.append(href)
        elif "instagram.com" in lowered:
            profile.instagram_links.append(href)
        elif "wa.me/" in lowered or "whatsapp" in lowered:
            profile.whatsapp_links.append(href)
        elif "youtube.com" in lowered or "youtu.be" in lowered:
            profile.youtube_links.append(href)
        elif "maps.yandex" in lowered or "yandex.ru/maps" in lowered or "2gis" in lowered:
            profile.map_links.append(href)
        elif href.startswith("http") and "checko.ru" not in lowered:
            profile.websites.append(href)

    profile.director_name = _extract_labeled_value(text, ["Директор", "Генеральный директор", "Руководитель"])
    profile.director_role = _extract_director_role(text)
    profile.director_inn = _extract_digits_value(text, ["ИНН руководителя"])
    profile.director_since_date = _extract_labeled_value(text, ["Руководитель с", "С даты"])
    profile.founders = _extract_founders(text)

    if not profile.inn or not profile.ogrn or not profile.kpp or not profile.okpo:
        _apply_jsonld_fallback(profile, html_text)
    if not profile.inn:
        profile.warnings.append("missing_inn")
    return profile


def _apply_jsonld_fallback(profile: CheckoProfileData, html_text: str) -> None:
    payloads = _extract_jsonld_objects(html_text)
    for item in payloads:
        item_type = item.get("@type")
        if item_type != "Organization" and item_type != ["Organization"] and "name" not in item:
            continue
        profile.short_name = profile.short_name or _coerce_str(item.get("name"))
        profile.legal_name = profile.legal_name or _coerce_str(item.get("legalName"))
        profile.inn = profile.inn or _coerce_str(item.get("taxID"))
        profile.checko_profile_url = profile.checko_profile_url or _coerce_str(item.get("url"))
        address = item.get("address")
        if isinstance(address, dict):
            profile.legal_address = profile.legal_address or ", ".join(
                part for part in [_coerce_str(address.get("streetAddress")), _coerce_str(address.get("addressLocality"))] if part
            )
        identifiers = item.get("identifier")
        if isinstance(identifiers, dict):
            identifiers = [identifiers]
        if isinstance(identifiers, list):
            for ident in identifiers:
                if not isinstance(ident, dict):
                    continue
                property_id = _coerce_str(ident.get("propertyID")) or ""
                value = _coerce_str(ident.get("value"))
                if not value:
                    continue
                if property_id == "ОГРН" and not profile.ogrn:
                    profile.ogrn = value
                if property_id == "ИНН" and not profile.inn:
                    profile.inn = value
                if property_id == "КПП" and not profile.kpp:
                    profile.kpp = value
                if property_id == "ОКПО" and not profile.okpo:
                    profile.okpo = value


def _extract_jsonld_objects(html_text: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for match in JSON_LD_RE.finditer(html_text):
        body = html.unescape(match.group("body")).strip()
        if not body:
            continue
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            payloads.append(parsed)
        elif isinstance(parsed, list):
            payloads.extend(item for item in parsed if isinstance(item, dict))
    return payloads


def _extract_links(html_text: str, base_url: str) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for match in LINK_RE.finditer(html_text):
        href = urljoin(base_url, html.unescape(match.group("href")).strip())
        label = _clean_text(match.group("label"))
        results.append((href, label))
    return results


def _extract_founders(text: str) -> list[CheckoFounder]:
    results: list[CheckoFounder] = []
    section = _extract_labeled_value(text, ["Учредители", "Учредитель"])
    if not section:
        return results
    for chunk in re.split(r";|\n| \| ", section):
        clean = chunk.strip(" ,-")
        if len(clean) < 3:
            continue
        inn_match = re.search(r"ИНН[:\s]+(\d{10,12})", clean)
        share_match = re.search(r"(\d+%|\d[\d\s,.]*\s?руб\.)", clean, re.IGNORECASE)
        name = re.sub(r"ИНН[:\s]+\d{10,12}", "", clean)
        name = re.sub(r"\d+%|\d[\d\s,.]*\s?руб\.", "", name, flags=re.IGNORECASE)
        name = name.strip(" ,-")
        if not name:
            continue
        results.append(
            CheckoFounder(
                full_name=name,
                inn=inn_match.group(1) if inn_match else None,
                share_text=share_match.group(1) if share_match else None,
            )
        )
    return results


def _extract_nearby_block(html_text: str, start: int, end: int) -> str:
    left = max(0, start - 500)
    right = min(len(html_text), end + 1200)
    return _clean_text(html_text[left:right])


def _extract_canonical_url(html_text: str) -> str | None:
    match = re.search(r"""<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']+)["']""", html_text, re.IGNORECASE)
    return html.unescape(match.group(1)).strip() if match else None


def _extract_jsonld_url(html_text: str) -> str | None:
    for item in _extract_jsonld_objects(html_text):
        value = _coerce_str(item.get("url"))
        if value:
            return value
    return None


def _extract_okved_code(text: str) -> str | None:
    match = re.search(r"ОКВЭД[^0-9]*(\d{2}\.\d{2}|\d{6})", text)
    return match.group(1) if match else None


def _extract_okved_name(text: str) -> str | None:
    match = re.search(r"ОКВЭД[^:]*:\s*([^\n]+)", text)
    if not match:
        return None
    value = match.group(1).strip()
    value = re.sub(r"^\d{2}\.\d{2}\s*", "", value)
    return value or None


def _extract_status(text: str) -> str | None:
    lowered = text.lower()
    if "действует" in lowered:
        return "active"
    if "ликвид" in lowered or "прекращ" in lowered:
        return "inactive"
    return None


def _extract_director_role(text: str) -> str | None:
    for label in ("Генеральный директор", "Директор", "Руководитель"):
        if label.lower() in text.lower():
            return label
    return None


def _extract_title_name(html_text: str) -> str | None:
    match = re.search(r"(?is)<title>(.*?)</title>", html_text)
    return _clean_text(match.group(1)) if match else None


def _extract_tag_text(html_text: str, tag: str) -> str | None:
    match = re.search(fr"(?is)<{tag}[^>]*>(.*?)</{tag}>", html_text)
    return _clean_text(match.group(1)) if match else None


def _extract_digits_value(text: str, labels: list[str]) -> str | None:
    for label in labels:
        for line in text.splitlines():
            match = re.search(fr"^{re.escape(label)}\s*[:\-]?\s*(\d{{8,15}})$", line.strip(), re.IGNORECASE)
            if match:
                return match.group(1)
    return None


def _extract_labeled_value(text: str, labels: list[str]) -> str | None:
    for label in labels:
        for line in text.splitlines():
            match = re.search(fr"{re.escape(label)}\s*[:\-]?\s*(.+)$", line, re.IGNORECASE)
            if match:
                value = match.group(1).strip(" :-")
                if value:
                    return value
    return None


def _clean_text(value: str) -> str:
    cleaned = TAG_RE.sub(" ", value)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _html_to_lines(value: str) -> list[str]:
    normalized = re.sub(r"(?i)</?(div|p|li|tr|td|h1|h2|h3|h4|section|article|br)[^>]*>", "\n", value)
    normalized = TAG_RE.sub(" ", normalized)
    normalized = html.unescape(normalized)
    return [re.sub(r"\s+", " ", line).strip() for line in normalized.splitlines() if line.strip()]


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _dedupe_list_items(items: list[CheckoListItem]) -> list[CheckoListItem]:
    seen: set[str] = set()
    result: list[CheckoListItem] = []
    for item in items:
        key = item.profile_url or item.legal_name or ""
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
