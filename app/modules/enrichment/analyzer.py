from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin, urlparse

from app.modules.enrichment.schemas import (
    DetectedContactsRead,
    DetectedLinksRead,
    WebsiteAnalysis,
    WebsiteSignalRead,
)


TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
META_DESCRIPTION_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
HREF_RE = re.compile(r'href=["\'](.*?)["\']', re.IGNORECASE)
SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
PHONE_RE = re.compile(r"(?:(?:\+7|8)[\s\-()]*)?(?:\d[\s\-()]*){10,11}")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)

SOCIAL_PATTERNS = {
    "vk": ("vk.com", "vkontakte.ru"),
    "instagram": ("instagram.com",),
    "telegram": ("t.me", "telegram.me", "telegram.org"),
    "whatsapp": ("wa.me", "api.whatsapp.com", "whatsapp.com"),
    "youtube": ("youtube.com", "youtu.be"),
    "tiktok": ("tiktok.com",),
    "dzen": ("dzen.ru", "zen.yandex"),
    "tenchat": ("tenchat.ru",),
}

MAP_PATTERNS = {
    "yandex_maps": ("yandex.ru/maps", "maps.yandex.ru"),
    "2gis": ("2gis.ru",),
    "google_maps": ("google.com/maps", "maps.google.com", "goo.gl/maps"),
    "zoon": ("zoon.ru",),
    "prodoctorov": ("prodoctorov.ru",),
    "yell": ("yell.ru",),
}

SIGNAL_KEYWORDS = {
    "has_online_booking": ("онлайн-запись", "записаться", "запись на прием", "выбрать время", "appointment", "book"),
    "has_callback_form": ("оставить заявку", "обратный звонок", "перезвоните", "форма", "заявка"),
    "has_prices": ("цены", "прайс", "стоимость", "price"),
    "has_doctors_page": ("врачи", "специалисты", "команда", "doctors"),
    "has_reviews_section": ("отзывы", "reviews"),
    "has_contacts_page": ("контакты", "адрес", "телефон"),
    "has_privacy_policy": ("политика конфиденциальности", "privacy policy"),
    "has_promotions": ("акция", "скидка", "спецпредложение"),
    "has_implantation_keywords": ("имплантация", "имплант", "all-on-4", "all on 4"),
    "has_orthodontics_keywords": ("брекеты", "элайнеры", "orthodont"),
    "has_children_dentistry_keywords": ("детская стоматология", "детям", "pediatric"),
    "has_emergency_keywords": ("острая боль", "срочно", "emergency"),
}


def analyze_website_html(html: str, base_url: str) -> WebsiteAnalysis:
    excerpt_source = _extract_text(html)
    title = _extract_match(TITLE_RE, html)
    description = _extract_match(META_DESCRIPTION_RE, html)
    links = _extract_links(html, base_url)
    socials = _collect_matches(links, SOCIAL_PATTERNS)
    maps = _collect_matches(links, MAP_PATTERNS)
    contacts = _extract_contacts(excerpt_source, links)
    lower_text = excerpt_source.lower()
    signals = WebsiteSignalRead(
        **{name: _contains_keywords(lower_text, keywords) for name, keywords in SIGNAL_KEYWORDS.items()}
    )
    signals.has_social_links = any(socials.values())
    signals.has_messenger_links = bool(socials.get("telegram") or socials.get("whatsapp"))

    return WebsiteAnalysis(
        page_title=title[:500] if title else None,
        meta_description=description[:1000] if description else None,
        raw_text_excerpt=excerpt_source[:5000] if excerpt_source else None,
        detected_links=links,
        detected_socials=socials,
        detected_maps=maps,
        detected_contacts=contacts,
        signals=signals,
    )


def build_enrichment_hypotheses(analysis: WebsiteAnalysis) -> list[str]:
    signals = analysis.signals
    hypotheses: list[str] = []

    if not signals.has_online_booking:
        hypotheses.append(
            "В быстрой проверке не обнаружена явная онлайн-запись. Возможно, часть пациентов теряется до обращения."
        )
    if not signals.has_messenger_links:
        hypotheses.append(
            "В быстрой проверке не обнаружены быстрые ссылки на мессенджеры. Возможно, пациенту сложнее быстро задать вопрос перед записью."
        )
    if not signals.has_doctors_page:
        hypotheses.append(
            "В быстрой проверке не обнаружен явный блок врачей. Для стоматологии это может снижать доверие к сложным услугам."
        )
    if not signals.has_reviews_section:
        hypotheses.append(
            "В быстрой проверке не обнаружен явный блок отзывов. Возможно, это ослабляет доверие перед записью."
        )
    if not signals.has_prices:
        hypotheses.append(
            "В быстрой проверке не обнаружен явный блок цен. Это может усиливать неопределенность перед обращением."
        )
    if signals.has_implantation_keywords and not (signals.has_doctors_page and signals.has_reviews_section):
        hypotheses.append(
            "По доступным данным можно предположить, что имплантация представлена, но стоит проверить, достаточно ли упакованы доверительные блоки: врачи, отзывы, кейсы, гарантии и этапы лечения."
        )
    if not signals.has_contacts_page and not analysis.detected_contacts.phones and not analysis.detected_contacts.emails:
        hypotheses.append(
            "В быстрой проверке не обнаружен явный блок контактов. Стоит проверить, насколько быстро пациент может найти адрес и телефон."
        )

    return hypotheses


def _extract_match(pattern: re.Pattern[str], html: str) -> str | None:
    match = pattern.search(html)
    if not match:
        return None
    return WHITESPACE_RE.sub(" ", unescape(match.group(1))).strip()


def _extract_text(html: str) -> str:
    without_scripts = SCRIPT_STYLE_RE.sub(" ", html)
    without_tags = TAG_RE.sub(" ", without_scripts)
    clean = WHITESPACE_RE.sub(" ", unescape(without_tags)).strip()
    return clean[:5000]


def _extract_links(html: str, base_url: str) -> DetectedLinksRead:
    base_host = urlparse(base_url).netloc.lower()
    internal_links: list[str] = []
    external_links: list[str] = []
    for href in HREF_RE.findall(html):
        href = href.strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        target = absolute[:500]
        if parsed.netloc.lower() == base_host:
            _append_unique(internal_links, target)
        else:
            _append_unique(external_links, target)
    return DetectedLinksRead(internal_links=internal_links[:30], external_links=external_links[:50])


def _collect_matches(links: DetectedLinksRead, mapping: dict[str, tuple[str, ...]]) -> dict[str, list[str]]:
    all_links = [*links.internal_links, *links.external_links]
    result: dict[str, list[str]] = {key: [] for key in mapping}
    for link in all_links:
        lowered = link.lower()
        for key, variants in mapping.items():
            if any(variant in lowered for variant in variants):
                _append_unique(result[key], link)
    return result


def _extract_contacts(text: str, links: DetectedLinksRead) -> DetectedContactsRead:
    phones = [_normalize_phone(match) for match in PHONE_RE.findall(text)]
    phones = [item for item in phones if item]
    emails = [match.lower() for match in EMAIL_RE.findall(text)]
    whatsapp_links: list[str] = []
    telegram_links: list[str] = []
    for link in [*links.internal_links, *links.external_links]:
        lowered = link.lower()
        if any(token in lowered for token in ("wa.me", "api.whatsapp.com", "whatsapp.com")):
            _append_unique(whatsapp_links, link)
        if any(token in lowered for token in ("t.me", "telegram.me", "telegram.org")):
            _append_unique(telegram_links, link)
    return DetectedContactsRead(
        phones=_limit_unique(phones, 10),
        emails=_limit_unique(emails, 10),
        whatsapp_links=whatsapp_links[:10],
        telegram_links=telegram_links[:10],
    )


def _contains_keywords(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _normalize_phone(value: str) -> str | None:
    digits = re.sub(r"\D+", "", value)
    if len(digits) < 10:
        return None
    if len(digits) == 11 and digits.startswith("8"):
        digits = f"7{digits[1:]}"
    if len(digits) == 11 and digits.startswith("7"):
        return f"+{digits}"
    return digits


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _limit_unique(items: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
        if len(result) >= limit:
            break
    return result
