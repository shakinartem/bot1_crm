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
from app.modules.legal_discovery.checko_html import CheckoHtmlLegalDiscoveryProvider  # noqa: E402
from app.modules.legal_discovery.checko_parser import (  # noqa: E402
    is_probable_checko_company_item,
    parse_checko_list_page_with_diagnostics,
    parse_checko_profile_page,
)
from app.modules.legal_discovery.handlers import _render_preview  # noqa: E402
from app.modules.legal_discovery.okved_catalog import normalize_okved_code, resolve_okved_by_query  # noqa: E402
from app.modules.research.browser_backend import BrowserBackendError, DisabledBrowserBackend, MockBrowserBackend  # noqa: E402


def read_fixture(name: str) -> str:
    return (ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8")


def build_profile_html(*, legal_name: str, short_name: str, inn: str, ogrn: str, address: str, status: str | None) -> str:
    status_block = f"<div>Статус: {status}</div>" if status else ""
    jsonld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": short_name,
            "legalName": legal_name,
            "taxID": inn,
            "url": f"https://checko.ru/company/{inn}",
            "identifier": [
                {"propertyID": "ОГРН", "value": ogrn},
                {"propertyID": "КПП", "value": "645301001"},
                {"propertyID": "ОКПО", "value": "12345678"},
            ],
            "address": {
                "streetAddress": address,
                "addressLocality": address.split(",")[0].replace("г. ", "").strip(),
            },
        },
        ensure_ascii=False,
    )
    return f"""
    <html>
      <head>
        <title>{legal_name}</title>
        <link rel="canonical" href="https://checko.ru/company/{inn}" />
        <script type="application/ld+json">{jsonld}</script>
      </head>
      <body>
        <h1>{short_name}</h1>
        <div>Полное наименование: {legal_name}</div>
        <div>Юридический адрес: {address}</div>
        {status_block}
        <div>ОКВЭД: 86.23 Стоматологическая практика</div>
        <div>Директор: Иванов Иван Иванович</div>
        <div>ИНН руководителя: 645300000111</div>
        <div>Руководитель с: 12.03.2018</div>
        <div>Учредители: Иванов Иван Иванович ИНН 645300000111 100%</div>
        <div>Телефон: +7 (8452) 11-22-33</div>
        <div>Email: info@example.test</div>
        <a href="https://example.test">Сайт</a>
      </body>
    </html>
    """


def build_category_only_html() -> str:
    return """
    <html>
      <head><title>Медицинская и стоматологическая практика - Организации</title></head>
      <body>
        <div class="category-header">
          <a href="/company/meditsinskaya-i-stomatologicheskaya-praktika">Медицинская и стоматологическая практика</a>
          <div>Организации 1-50 из 5175</div>
          <div>Описание категории ОКВЭД 86.23</div>
        </div>
        <div class="category-breadcrumb">
          <a href="/company/deyatelnost-v-oblasti-zdravoohraneniya">Деятельность в области здравоохранения</a>
        </div>
      </body>
    </html>
    """


async def main() -> None:
    list_html = read_fixture("checko_select_with_categories_and_companies.html")
    fallback_html = list_html.replace(' class="company-card"', "").replace(' class="category-header"', "").replace(' class="category-breadcrumb"', "")
    category_only_html = build_category_only_html()
    saratov_profile = build_profile_html(
        legal_name='ООО "ДЕНТАЛ БРАВО"',
        short_name="Дентал Браво",
        inn="6453001234",
        ogrn="1026403001234",
        address="г. Саратов, ул. Радищева, 15",
        status="Действует",
    )
    saratov_unknown_profile = build_profile_html(
        legal_name='ООО "СМАЙЛ ЛАЙН"',
        short_name="Смайл Лайн",
        inn="6453009999",
        ogrn="1026403009999",
        address="г. Саратов, ул. Московская, 8",
        status=None,
    )
    omsk_profile = build_profile_html(
        legal_name='ООО "ОМСК ДЕНТ"',
        short_name="Омск Дент",
        inn="5500001234",
        ogrn="1025500001234",
        address="г. Омск, ул. Ленина, 3",
        status="Действует",
    )

    items, diagnostics = parse_checko_list_page_with_diagnostics(list_html)
    assert len(items) == 3, "parser must keep only real company candidates"
    assert diagnostics.company_links_found > 0, "diagnostics must count /company/ links"
    assert diagnostics.skipped_missing_profile_url >= 1, "category/select links must not become profile URLs"
    assert all("/company/select" not in (item.profile_url or "") for item in items), "category select links must be rejected as profile URLs"
    assert all(is_probable_checko_company_item(item) for item in items), "remaining items must look like real companies"

    fallback_items, fallback_diagnostics = parse_checko_list_page_with_diagnostics(fallback_html)
    assert fallback_diagnostics.company_links_found > 0, "fallback diagnostics must still see company links"
    assert any(item.profile_url and item.profile_url.endswith("/1234567890") for item in fallback_items), "fallback extraction must find real company links"

    parsed_profile = parse_checko_profile_page(saratov_profile)
    assert parsed_profile.inn == "6453001234", "profile parser must parse INN"
    assert parsed_profile.ogrn == "1026403001234", "profile parser must parse OGRN"
    assert parsed_profile.legal_name == 'ООО "ДЕНТАЛ БРАВО"', "profile parser must preserve legal name"

    assert normalize_okved_code("86.23") == "862300", "OKVED normalization must strip punctuation"
    assert resolve_okved_by_query("стоматология").normalized_code == "862300", "popular OKVED heuristic must work"

    debug_dir = ROOT / "storage" / "debug" / "checko_smoke"
    if debug_dir.exists():
        shutil.rmtree(debug_dir)

    backend = MockBrowserBackend(
        {
            "https://checko.ru/company/select?code=862300&page=1": list_html,
            "https://checko.ru/company/1234567890": saratov_profile,
            "https://checko.ru/company/2222222222": saratov_unknown_profile,
            "https://checko.ru/company/0987654321": omsk_profile,
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
    companies = await provider.search_companies(query="стоматология", okved_code="86.23", limit=5, city="Саратов")
    assert len(companies) == 2, "region filter must keep only Saratov companies"
    assert all("Саратов" in (company.address or "") for company in companies), "Omsk company must be filtered out"
    assert any(company.status == "active" for company in companies), "active company must be preserved"
    assert any(company.status is None for company in companies), "unknown status company must stay unknown"
    assert provider.last_debug_info["filtered_by_region_count"] == 1, "region filter counter must track excluded companies"
    assert provider.last_debug_info["skipped_not_company_count"] >= 3, "provider debug must track non-company rows"
    assert provider.last_debug_info["company_links_found"] > 0, "provider debug must expose company link count"
    assert provider.last_debug_info["debug_snapshot_path"], "provider must save debug snapshot metadata when debug is enabled"
    assert Path(provider.last_debug_info["debug_snapshot_path"]).exists(), "snapshot metadata file must exist"

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
        await failing_provider.search_companies(query="стоматология", okved_code="86.23", limit=1)
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
                query="стоматология",
                okved_code="86.23",
                city="Саратов",
                limit=5,
                provider_code="checko_html",
            )
            assert preview.total_found == 2, "preview must not include category rows"
            assert preview.active_count == 1, "active counter must count only explicit active companies"
            assert preview.inactive_count == 0, "unknown status must not count as inactive"
            assert preview.unknown_status_count == 1, "unknown status must be counted separately"
            assert preview.filtered_by_region_count == 1, "preview must expose region filter count"
            assert preview.skipped_not_company_count >= 3, "preview must expose skipped category/header rows"
            assert preview.company_links_found > 0, "preview must expose parser link diagnostics"
            assert preview.parser_candidates_count > 0, "preview must expose parser candidate count"
            assert all("ОМСК" not in (item.company.legal_name or "") for item in preview.items), "Omsk company must stay out of preview"

            imported_active = await discovery_service.import_legal_discovery_preview(session, preview.preview_id, "active_new")
            assert imported_active.added_count == 1, "active_new must not import unknown status candidate"
            imported_company = await session.scalar(select(Company).where(Company.id == imported_active.added_company_ids[0]))
            assert imported_company is not None and "ДЕНТАЛ БРАВО" in (imported_company.legal_name or ""), "active import must keep the active Saratov company"
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
                query="стоматология",
                okved_code="86.23",
                city="Саратов",
                limit=5,
                provider_code="checko_html",
            )
        assert zero_preview.total_found == 0, "category-only page must produce zero preview items"
        assert zero_preview.company_links_found > 0, "zero-result preview must still expose /company/ link count"
        assert zero_preview.parser_candidates_count == 0, "zero-result preview must expose zero parser candidates"
        rendered_zero = _render_preview(zero_preview)
        assert "Final URL:" in rendered_zero, "zero-result preview must include debug final URL"
        assert "/company/ ссылок найдено:" in rendered_zero, "zero-result preview must include link diagnostics"
        assert "Парсер не нашёл карточки компаний" in rendered_zero, "zero-result preview must explain parser-zero case"
    finally:
        discovery_service.get_legal_discovery_provider = original_get_provider

    print("smoke_checko_html ok")


if __name__ == "__main__":
    asyncio.run(main())
