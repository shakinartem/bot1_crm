from __future__ import annotations

import re
from urllib.parse import urlparse

from app.modules.intelligence.schemas import LegalCompany


BLOCKED_DOMAIN_MARKERS = {
    "rusprofile.ru",
    "list-org.com",
    "zachestnyibiznes.ru",
    "checko.ru",
    "sbis.ru",
    "spark-interfax.ru",
    "kartoteka.ru",
    "nalog.gov.ru",
    "egrul.nalog.ru",
    "2gis.ru",
    "zoon.ru",
    "prodoctorov.ru",
    "yell.ru",
}

DENTISTRY_KEYWORDS = (
    "стомат",
    "дентал",
    "имплант",
    "ортодонт",
    "брекет",
    "элайнер",
    "клиника",
)


def is_directory_domain(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(marker in host for marker in BLOCKED_DOMAIN_MARKERS) or "yandex.ru/maps" in url.lower()


def score_website_candidate(
    legal_company: LegalCompany,
    url: str,
    title: str | None,
    snippet: str | None,
    fetched_excerpt: str | None,
    city: str | None = None,
    known_phone: str | None = None,
) -> tuple[float, list[str], list[str], bool]:
    reasons: list[str] = []
    warnings: list[str] = []
    score = 0.0
    combined = " ".join(item for item in (title or "", snippet or "", fetched_excerpt or "") if item).lower()

    if is_directory_domain(url):
        score -= 30
        warnings.append("домен похож на справочник или агрегатор")

    if legal_company.inn and legal_company.inn in combined:
        score += 50
        reasons.append("ИНН найден на сайте")

    legal_names = [legal_company.legal_name, legal_company.short_name]
    if any(name and normalize_text(name) in normalize_text(combined) for name in legal_names):
        score += 25
        reasons.append("название юрлица найдено на сайте")

    if city and normalize_text(city) in normalize_text(combined):
        score += 20
        reasons.append("город совпадает")
    elif legal_company.city and normalize_text(legal_company.city) in normalize_text(combined):
        score += 20
        reasons.append("город юрлица совпадает")

    if legal_company.address and _contains_address_fragment(combined, legal_company.address):
        score += 20
        reasons.append("адрес или его фрагмент совпадает")

    digits_phone = digits_only(known_phone)
    if digits_phone and digits_phone[-10:] and digits_phone[-10:] in digits_only(combined):
        score += 15
        reasons.append("известный телефон найден")

    if any(keyword in combined for keyword in DENTISTRY_KEYWORDS):
        score += 10
        reasons.append("найдены стоматологические ключевые слова")

    is_official = score >= 35 and not is_directory_domain(url)
    if not is_official:
        warnings.append("нужна ручная проверка официальности сайта")
    return score, reasons, warnings, is_official


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().replace('"', " ").replace("«", " ").replace("»", " ")).strip()


def digits_only(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _contains_address_fragment(combined_text: str, address: str) -> bool:
    tokens = [token for token in re.split(r"[\s,.;:()/-]+", address.lower()) if len(token) >= 4]
    if not tokens:
        return False
    matched = sum(1 for token in tokens[:5] if token in combined_text)
    return matched >= min(2, len(tokens[:5]))
