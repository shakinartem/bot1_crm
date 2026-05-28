from __future__ import annotations

import html
import re

from app.modules.enrichment.analyzer import analyze_website_html
from app.modules.intelligence.schemas import ParsedCompanyContacts, ParsedCompanySite, ParsedCompanySocials


ADDRESS_RE = re.compile(
    r"(?:г\.|город|ул\.|улица|проспект|пр-т|площадь|пер\.|переулок|шоссе|бул\.|бульвар)[^<\n]{10,180}",
    re.IGNORECASE,
)


def parse_company_site(html_text: str, url: str) -> ParsedCompanySite:
    analysis = analyze_website_html(html_text, url)
    excerpt = analysis.raw_text_excerpt or _strip_tags(html_text)[:4000]

    socials = ParsedCompanySocials(
        vk_links=analysis.detected_socials.get("vk", []),
        instagram_links=analysis.detected_socials.get("instagram", []),
        youtube_links=analysis.detected_socials.get("youtube", []),
        tiktok_links=analysis.detected_socials.get("tiktok", []),
        dzen_links=analysis.detected_socials.get("dzen", []),
        telegram_links=analysis.detected_socials.get("telegram", []),
        whatsapp_links=analysis.detected_socials.get("whatsapp", []),
        yandex_maps_links=analysis.detected_maps.get("yandex_maps", []),
        two_gis_links=analysis.detected_maps.get("2gis", []),
    )
    contacts = ParsedCompanyContacts(
        phones=analysis.detected_contacts.phones,
        emails=analysis.detected_contacts.emails,
        addresses=_dedupe([item.strip() for item in ADDRESS_RE.findall(excerpt)]),
        whatsapp_links=analysis.detected_contacts.whatsapp_links,
        telegram_links=analysis.detected_contacts.telegram_links,
    )
    return ParsedCompanySite(
        page_title=analysis.page_title,
        meta_description=analysis.meta_description,
        text_excerpt=excerpt[:4000],
        contacts=contacts,
        socials=socials,
        signals=analysis.signals,
    )


def _strip_tags(value: str) -> str:
    cleaned = re.sub(r"(?is)<script.*?>.*?</script>", " ", value)
    cleaned = re.sub(r"(?is)<style.*?>.*?</style>", " ", cleaned)
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
