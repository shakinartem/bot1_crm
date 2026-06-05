from __future__ import annotations

import asyncio
import json
import os
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

from app.config import Settings  # noqa: E402
from app.database import async_session_factory, create_db_schema  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.modules.crm.models import Company  # noqa: E402
from app.modules.legal_discovery import service as discovery_service  # noqa: E402
from app.modules.legal_discovery.checko_html import CheckoHtmlLegalDiscoveryProvider  # noqa: E402
from app.modules.legal_discovery.checko_parser import is_probable_checko_company_item, parse_checko_list_page, parse_checko_profile_page  # noqa: E402
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


async def main() -> None:
    list_html = read_fixture("checko_select_with_categories_and_companies.html")
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

    parse_debug: dict[str, int] = {}
    items = parse_checko_list_page(list_html, debug=parse_debug)
    assert len(items) == 3, "parser must keep only real company candidates"
    assert parse_debug["skipped_category_like_item"] >= 2, "category-like rows must be skipped"
    assert parse_debug["skipped_missing_profile_url"] >= 1, "company without profile_url must be skipped"
    assert all(is_probable_checko_company_item(item) for item in items), "remaining items must look like real companies"

    parsed_profile = parse_checko_profile_page(saratov_profile)
    assert parsed_profile.inn == "6453001234", "profile parser must parse INN"
    assert parsed_profile.ogrn == "1026403001234", "profile parser must parse OGRN"
    assert parsed_profile.legal_name == 'ООО "ДЕНТАЛ БРАВО"', "profile parser must preserve legal name"

    assert normalize_okved_code("86.23") == "862300", "OKVED normalization must strip punctuation"
    assert resolve_okved_by_query("стоматология").normalized_code == "862300", "popular OKVED heuristic must work"

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
    else:  # pragma: no cover - defensive
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
            assert all("ОМСК" not in (item.company.legal_name or "") for item in preview.items), "Omsk company must stay out of preview"

            imported_active = await discovery_service.import_legal_discovery_preview(session, preview.preview_id, "active_new")
            assert imported_active.added_count == 1, "active_new must not import unknown status candidate"
            imported_company = await session.scalar(select(Company).where(Company.id == imported_active.added_company_ids[0]))
            assert imported_company is not None and "ДЕНТАЛ БРАВО" in (imported_company.legal_name or ""), "active import must keep the active Saratov company"
    finally:
        discovery_service.get_legal_discovery_provider = original_get_provider

    print("smoke_checko_html ok")


if __name__ == "__main__":
    asyncio.run(main())
