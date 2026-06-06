from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_checko_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")
os.environ.setdefault("LEGAL_DISCOVERY_PROVIDER", "checko_html")
os.environ.setdefault("CHECKO_HTML_ENABLED", "1")
os.environ.setdefault("BROWSER_BACKEND", "mock")
os.environ.setdefault("CHECKO_HTML_PAGE_DELAY_MS", "0")

from sqlalchemy import select  # noqa: E402

from app.config import Settings  # noqa: E402
from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.crm.models import Company  # noqa: E402
from app.modules.legal_discovery import service as discovery_service  # noqa: E402
from app.modules.legal_discovery.checko_html import (  # noqa: E402
    CheckoHtmlLegalDiscoveryProvider,
    matches_region_filter,
    resolve_checko_region_target,
)
from app.modules.legal_discovery.checko_parser import (  # noqa: E402
    is_real_checko_profile_url,
    is_probable_checko_company_item,
    parse_checko_list_page_with_diagnostics,
    parse_checko_profile_page,
)
from app.modules.legal_discovery.handlers import (  # noqa: E402
    TELEGRAM_PREVIEW_LIMIT,
    _render_preview,
    build_message_too_long_fallback_text,
    truncate_telegram_text,
)
from app.modules.legal_discovery.okved_catalog import normalize_okved_code, resolve_okved_by_query  # noqa: E402
from app.modules.research.browser_backend import BrowserBackendError, DisabledBrowserBackend, MockBrowserBackend  # noqa: E402


def read_fixture(name: str) -> str:
    return (ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8")


SARATOV = "\u0421\u0430\u0440\u0430\u0442\u043e\u0432"
SARATOV_REGION = "\u0421\u0430\u0440\u0430\u0442\u043e\u0432\u0441\u043a\u0430\u044f \u043e\u0431\u043b\u0430\u0441\u0442\u044c"
SARATOV_ADDRESS_1 = "\u0433. \u0421\u0430\u0440\u0430\u0442\u043e\u0432, \u0443\u043b. \u0420\u0430\u0434\u0438\u0449\u0435\u0432\u0430, 15"
SARATOV_ADDRESS_2 = "\u0433. \u0421\u0430\u0440\u0430\u0442\u043e\u0432, \u0443\u043b. \u041c\u043e\u0441\u043a\u043e\u0432\u0441\u043a\u0430\u044f, 8"
SARATOV_ADDRESS_PRAKTIK = "410015, \u0421\u0430\u0440\u0430\u0442\u043e\u0432\u0441\u043a\u0430\u044f \u043e\u0431\u043b\u0430\u0441\u0442\u044c, \u0433. \u0421\u0430\u0440\u0430\u0442\u043e\u0432, \u043f\u043b. \u0438\u043c. \u041e\u0440\u0434\u0436\u043e\u043d\u0438\u043a\u0438\u0434\u0437\u0435 \u0413. \u041a., \u0434. 1"
OMSK = "\u041e\u043c\u0441\u043a"
OMSK_ADDRESS = "\u0433. \u041e\u043c\u0441\u043a, \u0443\u043b. \u041b\u0435\u043d\u0438\u043d\u0430, 3"
OMSK_ADDRESS_LONG = "644010, \u041e\u043c\u0441\u043a\u0430\u044f \u043e\u0431\u043b\u0430\u0441\u0442\u044c, \u0433. \u041e\u043c\u0441\u043a, \u043f\u0440-\u043a\u0442 \u041a\u0430\u0440\u043b\u0430 \u041c\u0430\u0440\u043a\u0441\u0430, \u0434. 10"
MOSCOW = "\u041c\u043e\u0441\u043a\u0432\u0430"
MOSCOW_ADDRESS = "121059, \u0433. \u041c\u043e\u0441\u043a\u0432\u0430, \u0431\u0443\u043b\u044c\u0432\u0430\u0440 \u0423\u043a\u0440\u0430\u0438\u043d\u0441\u043a\u0438\u0439, \u0434. 6, \u044d\u0442. 1, \u043f\u043e\u043c. I, \u043a\u043e\u043c. 24-41"
KRASNOYARSK = "\u041a\u0440\u0430\u0441\u043d\u043e\u044f\u0440\u0441\u043a"
KRASNOYARSK_ADDRESS = "660043, \u041a\u0440\u0430\u0441\u043d\u043e\u044f\u0440\u0441\u043a\u0438\u0439 \u043a\u0440\u0430\u0439, \u0433. \u041a\u0440\u0430\u0441\u043d\u043e\u044f\u0440\u0441\u043a, \u0443\u043b. \u0427\u0435\u0440\u043d\u044b\u0448\u0435\u0432\u0441\u043a\u043e\u0433\u043e, \u0434. 77, \u043f\u043e\u043c\u0435\u0449. 324"
ACTIVE_RU = "\u0414\u0435\u0439\u0441\u0442\u0432\u0443\u0435\u0442"


def build_profile_html(*, legal_name: str, short_name: str, inn: str, ogrn: str, address: str, status: str | None, profile_url: str) -> str:
    status_block = f"<div>РЎС‚Р°С‚СѓСЃ: {status}</div>" if status else ""
    jsonld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": short_name,
            "legalName": legal_name,
            "taxID": inn,
            "url": profile_url,
            "identifier": [
                {"propertyID": "РћР“Р Рќ", "value": ogrn},
                {"propertyID": "РљРџРџ", "value": "645301001"},
                {"propertyID": "РћРљРџРћ", "value": "12345678"},
            ],
            "address": {
                "streetAddress": address,
                "addressLocality": address.split(",")[0].replace("Рі. ", "").strip(),
            },
        },
        ensure_ascii=False,
    )
    return f"""
    <html>
      <head>
        <title>{legal_name}</title>
        <link rel="canonical" href="{profile_url}" />
        <script type="application/ld+json">{jsonld}</script>
      </head>
      <body>
        <h1>{short_name}</h1>
        <div>РџРѕР»РЅРѕРµ РЅР°РёРјРµРЅРѕРІР°РЅРёРµ: {legal_name}</div>
        <div>Р®СЂРёРґРёС‡РµСЃРєРёР№ Р°РґСЂРµСЃ: {address}</div>
        {status_block}
        <div>РћРљР’Р­Р”: 86.23 РЎС‚РѕРјР°С‚РѕР»РѕРіРёС‡РµСЃРєР°СЏ РїСЂР°РєС‚РёРєР°</div>
        <div>Р”РёСЂРµРєС‚РѕСЂ: РРІР°РЅРѕРІ РРІР°РЅ РРІР°РЅРѕРІРёС‡</div>
        <div>РРќРќ СЂСѓРєРѕРІРѕРґРёС‚РµР»СЏ: 645300000111</div>
        <div>Р СѓРєРѕРІРѕРґРёС‚РµР»СЊ СЃ: 12.03.2018</div>
        <div>РЈС‡СЂРµРґРёС‚РµР»Рё: РРІР°РЅРѕРІ РРІР°РЅ РРІР°РЅРѕРІРёС‡ РРќРќ 645300000111 100%</div>
        <div>РўРµР»РµС„РѕРЅ: +7 (8452) 11-22-33</div>
        <div>Email: info@example.test</div>
        <a href="https://example.test">РЎР°Р№С‚</a>
      </body>
    </html>
    """


def build_category_only_html() -> str:
    return """
    <html>
      <head><title>РњРµРґРёС†РёРЅСЃРєР°СЏ Рё СЃС‚РѕРјР°С‚РѕР»РѕРіРёС‡РµСЃРєР°СЏ РїСЂР°РєС‚РёРєР° - РћСЂРіР°РЅРёР·Р°С†РёРё</title></head>
      <body>
        <div class="category-header">
          <a href="/company/meditsinskaya-i-stomatologicheskaya-praktika">РњРµРґРёС†РёРЅСЃРєР°СЏ Рё СЃС‚РѕРјР°С‚РѕР»РѕРіРёС‡РµСЃРєР°СЏ РїСЂР°РєС‚РёРєР°</a>
          <div>РћСЂРіР°РЅРёР·Р°С†РёРё 1-50 РёР· 5175</div>
          <div>РћРїРёСЃР°РЅРёРµ РєР°С‚РµРіРѕСЂРёРё РћРљР’Р­Р” 86.23</div>
        </div>
        <div class="category-breadcrumb">
          <a href="/company/deyatelnost-v-oblasti-zdravoohraneniya">Р”РµСЏС‚РµР»СЊРЅРѕСЃС‚СЊ РІ РѕР±Р»Р°СЃС‚Рё Р·РґСЂР°РІРѕРѕС…СЂР°РЅРµРЅРёСЏ</a>
        </div>
      </body>
    </html>
    """


async def main() -> None:
    list_html = read_fixture("checko_select_with_categories_and_companies.html")
    live_list_html = read_fixture("checko_select_live_862300.html")
    fallback_html = list_html.replace(' class="company-card"', "").replace(' class="category-header"', "").replace(' class="category-breadcrumb"', "")
    category_only_html = build_category_only_html()
    saratov_profile = build_profile_html(
        legal_name='РћРћРћ "Р”Р•РќРўРђР› Р‘Р РђР’Рћ"',
        short_name="Р”РµРЅС‚Р°Р» Р‘СЂР°РІРѕ",
        inn="6453001234",
        ogrn="1026403001234",
        address=SARATOV_ADDRESS_1,
        status=ACTIVE_RU,
        profile_url="https://checko.ru/company/dental-bravo-1026403001234",
    )
    saratov_unknown_profile = build_profile_html(
        legal_name='РћРћРћ "РЎРњРђР™Р› Р›РђР™Рќ"',
        short_name="РЎРјР°Р№Р» Р›Р°Р№РЅ",
        inn="6453009999",
        ogrn="1026403009999",
        address=SARATOV_ADDRESS_2,
        status=None,
        profile_url="https://checko.ru/company/smile-line-1026403009999",
    )
    omsk_profile = build_profile_html(
        legal_name='РћРћРћ "РћРњРЎРљ Р”Р•РќРў"',
        short_name="РћРјСЃРє Р”РµРЅС‚",
        inn="5500001234",
        ogrn="1025500001234",
        address=OMSK_ADDRESS,
        status=ACTIVE_RU,
        profile_url="https://checko.ru/company/omsk-dent-1025500001234",
    )

    items, diagnostics = parse_checko_list_page_with_diagnostics(list_html)
    assert len(items) == 3, "parser must keep only real company candidates"
    assert diagnostics.company_links_found > 0, "diagnostics must count /company/ links"
    assert diagnostics.skipped_missing_profile_url >= 1, "category/select links must not become profile URLs"
    assert all("/company/select" not in (item.profile_url or "") for item in items), "category select links must be rejected as profile URLs"
    assert all(is_probable_checko_company_item(item) for item in items), "remaining items must look like real companies"

    fallback_items, fallback_diagnostics = parse_checko_list_page_with_diagnostics(fallback_html)
    assert fallback_diagnostics.company_links_found > 0, "fallback diagnostics must still see company links"
    assert any(item.profile_url and item.profile_url.endswith("/company/dental-bravo-1026403001234") for item in fallback_items), "fallback extraction must find real company links"

    assert is_real_checko_profile_url("/company/firma-praktik-1026402494799"), "slug+ogrn profile URLs must be accepted"
    assert not is_real_checko_profile_url("/company/select"), "select page must not be treated as a company profile"
    assert not is_real_checko_profile_url("/company/select?code=862300"), "select query links must not be treated as a company profile"
    assert not is_real_checko_profile_url("/company?code=862300"), "generic company queries must not be treated as a company profile"

    live_items, live_diagnostics = parse_checko_list_page_with_diagnostics(live_list_html)
    assert len(live_items) == 50, "live list fixture must produce 50 company candidates"
    assert live_diagnostics.company_links_found == 60, "live list fixture must preserve link diagnostics from debug capture"
    assert all("/company/select" not in (item.profile_url or "") for item in live_items), "category/select links must stay out of live company candidates"
    praktik = next((item for item in live_items if (item.profile_url or "").endswith("/company/firma-praktik-1026402494799")), None)
    assert praktik is not None, "Saratov company from live list must be parsed"
    assert praktik.profile_url and praktik.profile_url.endswith("/company/firma-praktik-1026402494799"), "Saratov company must keep its real profile URL"
    assert is_probable_checko_company_item(praktik), "candidate without INN on list page must remain valid before profile enrichment"
    assert praktik.raw_text, "raw text must stay available for post-filtering"

    parsed_profile = parse_checko_profile_page(saratov_profile)
    assert parsed_profile.inn == "6453001234", "profile parser must parse INN"
    assert parsed_profile.ogrn == "1026403001234", "profile parser must parse OGRN"
    assert parsed_profile.legal_name, "profile parser must preserve legal name"

    assert normalize_okved_code("86.23") == "862300", "OKVED normalization must strip punctuation"
    resolved_region = resolve_checko_region_target(SARATOV)
    assert resolved_region["federal_district"] == "Приволжский федеральный округ", "Saratov must resolve to Volga federal district"
    assert "64" in resolved_region["region_label"] and SARATOV_REGION in resolved_region["region_label"], "resolver must provide numbered Saratov label"
    assert SARATOV in resolved_region["fallback_terms"], "resolver must include quick-search term"

    debug_dir = ROOT / "storage" / "debug" / "checko_smoke"
    if debug_dir.exists():
        shutil.rmtree(debug_dir)

    backend = MockBrowserBackend(
        {
            "https://checko.ru/company/select?code=862300&page=1": list_html,
            "https://checko.ru/company/dental-bravo-1026403001234": saratov_profile,
            "https://checko.ru/company/smile-line-1026403009999": saratov_unknown_profile,
            "https://checko.ru/company/omsk-dent-1025500001234": omsk_profile,
        }
    )
    provider = CheckoHtmlLegalDiscoveryProvider(
        Settings(
            LEGAL_DISCOVERY_PROVIDER="checko_html",
            CHECKO_HTML_ENABLED="1",
            CHECKO_HTML_PAGE_DELAY_MS="0",
            CHECKO_HTML_PROFILE_ENABLED="1",
            CHECKO_HTML_BASE_URL="https://checko.ru",
            CHECKO_HTML_DEBUG="1",
            CHECKO_HTML_DEBUG_DIR=str(debug_dir),
        ),
        browser_backend=backend,
    )
    companies = await provider.search_companies(query="\u0441\u0442\u043e\u043c\u0430\u0442\u043e\u043b\u043e\u0433\u0438\u044f", okved_code="86.23", limit=5, city=SARATOV)
    assert len(companies) == 2, "region filter must keep only Saratov companies"
    assert all(SARATOV in (company.address or "") for company in companies), "Omsk company must be filtered out"
    assert any(company.status == "active" for company in companies), "active company must be preserved"
    assert any(company.status is None for company in companies), "unknown status company must stay unknown"
    assert provider.last_debug_info["filtered_by_region_count"] == 1, "region filter counter must track excluded companies"
    assert provider.last_debug_info["skipped_not_company_count"] >= 3, "provider debug must track non-company rows"
    assert provider.last_debug_info["company_links_found"] > 0, "provider debug must expose company link count"
    assert provider.last_debug_info["debug_snapshot_path"], "provider must save debug snapshot metadata when debug is enabled"
    assert Path(provider.last_debug_info["debug_snapshot_path"]).exists(), "snapshot metadata file must exist"
    assert provider.last_debug_info["region_resolved_district"] == "Приволжский федеральный округ", "debug must expose resolved district"
    assert "64" in (provider.last_debug_info["region_resolved_label"] or ""), "debug must expose resolved numbered region label"
    assert provider.last_debug_info["region_filter_applied"] is True, "mock region UI flow must mark filter as applied"

    live_praktik_profile = build_profile_html(
        legal_name='РћРћРћ Р¤РР РњРђ "РџР РђРљРўРРљ"',
        short_name='РћРћРћ Р¤РР РњРђ "РџР РђРљРўРРљ"',
        inn="6451001234",
        ogrn="1026402494799",
        address=SARATOV_ADDRESS_PRAKTIK,
        status=ACTIVE_RU,
        profile_url="https://checko.ru/company/firma-praktik-1026402494799",
    )
    live_moscow_profile = build_profile_html(
        legal_name='РћРћРћ "РРњРџР›РђРќРўР›РђР‘"',
        short_name='РћРћРћ "РРњРџР›РђРќРўР›РђР‘"',
        inn="7704001234",
        ogrn="1167746204120",
        address=MOSCOW_ADDRESS,
        status=ACTIVE_RU,
        profile_url="https://checko.ru/company/implantlab-1167746204120",
    )
    live_omsk_profile = build_profile_html(
        legal_name='РћРћРћ "РЎРўРћРњРђРўРћР›РћР“РРЇ \"РќРђ Р›Р•РќРРќР“Р РђР”РЎРљРћР™\""',
        short_name='РћРћРћ "РЎРўРћРњРђРўРћР›РћР“РРЇ \"РќРђ Р›Р•РќРРќР“Р РђР”РЎРљРћР™\""',
        inn="5501001234",
        ogrn="1025500980273",
        address=OMSK_ADDRESS_LONG,
        status=ACTIVE_RU,
        profile_url="https://checko.ru/company/stomatologiya-na-leningradskoy-1025500980273",
    )
    live_krasnoyarsk_profile = build_profile_html(
        legal_name='РћРћРћ "Р”Р•РќРўРђР› РљР›РРќРРљ"',
        short_name='РћРћРћ "Р”Р•РќРўРђР› РљР›РРќРРљ"',
        inn="2468001234",
        ogrn="1152468057455",
        address=KRASNOYARSK_ADDRESS,
        status=ACTIVE_RU,
        profile_url="https://checko.ru/company/dental-klinik-1152468057455",
    )
    live_backend = MockBrowserBackend(
        {
            "https://checko.ru/company/select?code=862300&page=1": live_list_html,
            "https://checko.ru/company/firma-praktik-1026402494799": live_praktik_profile,
            "https://checko.ru/company/implantlab-1167746204120": live_moscow_profile,
            "https://checko.ru/company/stomatologiya-na-leningradskoy-1025500980273": live_omsk_profile,
            "https://checko.ru/company/dental-klinik-1152468057455": live_krasnoyarsk_profile,
        }
    )
    live_provider = CheckoHtmlLegalDiscoveryProvider(
        Settings(
            LEGAL_DISCOVERY_PROVIDER="checko_html",
            CHECKO_HTML_ENABLED="1",
            CHECKO_HTML_PAGE_DELAY_MS="0",
            CHECKO_HTML_PROFILE_ENABLED="1",
            CHECKO_HTML_BASE_URL="https://checko.ru",
        ),
        browser_backend=live_backend,
    )
    live_companies = await live_provider.search_companies(query="\u0441\u0442\u043e\u043c\u0430\u0442\u043e\u043b\u043e\u0433\u0438\u044f", okved_code="86.23", limit=50, city=SARATOV)
    assert live_provider.last_debug_info["parser_candidates_count"] == 50, "provider must expose 50 live parser candidates"
    assert live_provider.last_debug_info["valid_companies_count"] > 0, "valid company count must not stay zero when Saratov candidate exists"
    assert any((company.checko_profile_url or "").endswith("/company/firma-praktik-1026402494799") for company in live_companies), "Saratov company must survive provider validation and region filtering"
    assert all(MOSCOW not in (company.address or "") for company in live_companies), "Moscow companies must be filtered out for Saratov query"
    assert all(OMSK not in (company.address or "") for company in live_companies), "Omsk companies must be filtered out for Saratov query"
    assert all(KRASNOYARSK not in (company.address or "") for company in live_companies), "Krasnoyarsk companies must be filtered out for Saratov query"
    assert all(matches_region_filter(company, SARATOV) for company in live_companies), "post-filter must keep only matching Saratov companies"

    failing_provider = CheckoHtmlLegalDiscoveryProvider(
        Settings(
            LEGAL_DISCOVERY_PROVIDER="checko_html",
            CHECKO_HTML_ENABLED="1",
            CHECKO_HTML_PAGE_DELAY_MS="0",
            CHECKO_HTML_BASE_URL="https://checko.ru",
        ),
        browser_backend=DisabledBrowserBackend(),
    )
    try:
        await failing_provider.search_companies(query="СЃС‚РѕРјР°С‚РѕР»РѕРіРёСЏ", okved_code="86.23", limit=1)
    except BrowserBackendError as exc:
        assert "browser backend failed" in str(exc).lower(), "provider must raise controlled browser backend error"
    else:
        raise AssertionError("provider must raise a controlled error when browser backend fails")

    smoke_db = ROOT / "app_checko_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()

    original_get_provider = discovery_service.get_legal_discovery_provider
    discovery_service.get_legal_discovery_provider = lambda _settings: provider
    try:
        async with async_session_factory() as session:
            preview = await discovery_service.run_legal_discovery_preview(
                session,
                query="\u0441\u0442\u043e\u043c\u0430\u0442\u043e\u043b\u043e\u0433\u0438\u044f",
                okved_code="86.23",
                city=SARATOV,
                limit=5,
                provider_code="checko_html",
            )
            assert preview.total_found >= 1, "preview must keep at least one valid company"
            assert preview.active_count >= 1, "active counter must keep active companies"
            assert preview.inactive_count == 0, "unknown status must not count as inactive"
            assert preview.filtered_by_region_count >= 1, "preview must expose region filter count"
            assert preview.skipped_not_company_count >= 3, "preview must expose skipped category/header rows"
            assert preview.company_links_found > 0, "preview must expose parser link diagnostics"
            assert preview.parser_candidates_count > 0, "preview must expose parser candidate count"
            assert all(OMSK not in (item.company.address or "") for item in preview.items), "Omsk company must stay out of preview"

            imported_active = await discovery_service.import_legal_discovery_preview(session, preview.preview_id, "active_new")
            assert imported_active.added_count == 1, "active_new must not import unknown status candidate"
            imported_company = await session.scalar(select(Company).where(Company.id == imported_active.added_company_ids[0]))
            assert imported_company is not None and SARATOV in (imported_company.address or ""), "active import must keep the active Saratov company"
    finally:
        discovery_service.get_legal_discovery_provider = original_get_provider

    zero_backend = MockBrowserBackend({"https://checko.ru/company/select?code=862300&page=1": category_only_html})
    zero_provider = CheckoHtmlLegalDiscoveryProvider(
        Settings(
            LEGAL_DISCOVERY_PROVIDER="checko_html",
            CHECKO_HTML_ENABLED="1",
            CHECKO_HTML_PAGE_DELAY_MS="0",
            CHECKO_HTML_PROFILE_ENABLED="0",
            CHECKO_HTML_BASE_URL="https://checko.ru",
        ),
        browser_backend=zero_backend,
    )
    discovery_service.get_legal_discovery_provider = lambda _settings: zero_provider
    try:
        async with async_session_factory() as session:
            zero_preview = await discovery_service.run_legal_discovery_preview(
                session,
                query="СЃС‚РѕРјР°С‚РѕР»РѕРіРёСЏ",
                okved_code="86.23",
                city="РЎР°СЂР°С‚РѕРІ",
                limit=5,
                provider_code="checko_html",
            )
        assert zero_preview.total_found == 0, "category-only page must produce zero preview items"
        assert zero_preview.company_links_found > 0, "zero-result preview must still expose /company/ link count"
        assert zero_preview.parser_candidates_count == 0, "zero-result preview must expose zero parser candidates"
        rendered_zero = _render_preview(zero_preview)
        assert "Final URL:" in rendered_zero, "zero-result preview must include debug final URL"
        assert "/company/" in rendered_zero, "zero-result preview must include link diagnostics"
        assert "CHECKO_HTML_DEBUG=true" in rendered_zero, "zero-result preview must explain parser-zero case"
    finally:
        discovery_service.get_legal_discovery_provider = original_get_provider

    assert truncate_telegram_text("x" * (TELEGRAM_PREVIEW_LIMIT + 50)) == ("x" * (TELEGRAM_PREVIEW_LIMIT - 1)) + "…", "truncate helper must keep Telegram-safe length"
    long_preview = _render_preview(preview, compact=True) + "\n" + ("debug line\n" * 1000)
    fallback_preview = build_message_too_long_fallback_text(long_preview)
    assert len(fallback_preview) <= TELEGRAM_PREVIEW_LIMIT, "MESSAGE_TOO_LONG fallback text must fit Telegram limit"
    assert "Проверьте debug/CSV" in fallback_preview, "fallback text must direct operator to debug/CSV"

    print("smoke_checko_html ok")


if __name__ == "__main__":
    asyncio.run(main())

