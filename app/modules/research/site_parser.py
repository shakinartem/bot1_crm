from __future__ import annotations

from app.modules.enrichment.analyzer import analyze_website_html, build_enrichment_hypotheses
from app.modules.intelligence.schemas import ParsedCompanyContacts, ParsedCompanySocials
from app.modules.research.schemas import ParsedCompanySite


def parse_company_site(html: str, url: str) -> ParsedCompanySite:
    analysis = analyze_website_html(html, url)
    return ParsedCompanySite(
        page_title=analysis.page_title,
        meta_description=analysis.meta_description,
        text_excerpt=analysis.raw_text_excerpt,
        contacts=ParsedCompanyContacts(
            phones=analysis.detected_contacts.phones,
            emails=analysis.detected_contacts.emails,
            whatsapp_links=analysis.detected_contacts.whatsapp_links,
            telegram_links=analysis.detected_contacts.telegram_links,
        ),
        socials=ParsedCompanySocials(
            vk_links=analysis.detected_socials.get("vk", []),
            instagram_links=analysis.detected_socials.get("instagram", []),
            youtube_links=analysis.detected_socials.get("youtube", []),
            tiktok_links=analysis.detected_socials.get("tiktok", []),
            dzen_links=analysis.detected_socials.get("dzen", []),
            telegram_links=analysis.detected_socials.get("telegram", []),
            whatsapp_links=analysis.detected_socials.get("whatsapp", []),
            yandex_maps_links=analysis.detected_maps.get("yandex_maps", []),
            two_gis_links=analysis.detected_maps.get("2gis", []),
        ),
        signals=analysis.signals,
    )


def build_site_hypotheses(parsed: ParsedCompanySite) -> list[str]:
    analysis = parsed_to_analysis(parsed)
    return build_enrichment_hypotheses(analysis)


def parsed_to_analysis(parsed: ParsedCompanySite):
    from app.modules.enrichment.schemas import WebsiteAnalysis

    return WebsiteAnalysis(
        page_title=parsed.page_title,
        meta_description=parsed.meta_description,
        raw_text_excerpt=parsed.text_excerpt,
        detected_socials={
            "vk": parsed.socials.vk_links,
            "instagram": parsed.socials.instagram_links,
            "telegram": parsed.socials.telegram_links,
            "whatsapp": parsed.socials.whatsapp_links,
            "youtube": parsed.socials.youtube_links,
            "tiktok": parsed.socials.tiktok_links,
            "dzen": parsed.socials.dzen_links,
        },
        detected_maps={
            "yandex_maps": parsed.socials.yandex_maps_links,
            "2gis": parsed.socials.two_gis_links,
        },
        detected_contacts={
            "phones": parsed.contacts.phones,
            "emails": parsed.contacts.emails,
            "whatsapp_links": parsed.contacts.whatsapp_links,
            "telegram_links": parsed.contacts.telegram_links,
        },
        signals=parsed.signals,
    )
