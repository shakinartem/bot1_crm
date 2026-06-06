from __future__ import annotations

import asyncio
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
from app.modules.crm.location_utils import extract_region_city_from_address  # noqa: E402
from app.modules.legal_discovery.checko_html import CheckoHtmlLegalDiscoveryProvider  # noqa: E402
from app.modules.research.browser_backend import MockBrowserBackend  # noqa: E402


def build_list_html() -> str:
    return """
    <html>
      <head><title>Checko 86.23</title></head>
      <body>
        <a href="/company/firma-praktik-1026402494799">ООО "ФИРМА ПРАКТИК"</a>
        <div>г. Саратов, ул. Радищева, 15</div>
        <a href="/company/implantlab-1167746204120">ООО "ИМПЛАНТЛАБ"</a>
        <div>г. Москва, бул. Украинский, 6</div>
        <a href="/company/stomatologiya-na-leningradskoy-1025500980273">ООО "СТОМАТОЛОГИЯ"</a>
        <div>г. Омск, ул. Ленина, 3</div>
      </body>
    </html>
    """


def build_profile_html(*, legal_name: str, short_name: str, inn: str, ogrn: str, address: str, profile_url: str) -> str:
    return f"""
    <html>
      <head>
        <title>{legal_name}</title>
        <link rel="canonical" href="{profile_url}" />
      </head>
      <body>
        <h1>{short_name}</h1>
        <div>Полное наименование: {legal_name}</div>
        <div>Юридический адрес: {address}</div>
        <div>Статус: Действует</div>
        <div>ОКВЭД: 86.23</div>
        <div>Телефон: +7 (999) 000-00-00</div>
        <a href="https://example.test">Сайт</a>
        <div>ИНН: {inn}</div>
        <div>ОГРН: {ogrn}</div>
      </body>
    </html>
    """


async def main() -> None:
    list_url = "https://checko.ru/company/select?code=862300&page=1"
    fixtures = {
        list_url: build_list_html(),
        "https://checko.ru/company/firma-praktik-1026402494799": build_profile_html(
            legal_name='ООО "ФИРМА ПРАКТИК"',
            short_name='ООО "ФИРМА ПРАКТИК"',
            inn="6451001234",
            ogrn="1026402494799",
            address="410015, Саратовская область, г. Саратов, ул. Радищева, 15",
            profile_url="https://checko.ru/company/firma-praktik-1026402494799",
        ),
        "https://checko.ru/company/implantlab-1167746204120": build_profile_html(
            legal_name='ООО "ИМПЛАНТЛАБ"',
            short_name='ООО "ИМПЛАНТЛАБ"',
            inn="7704001234",
            ogrn="1167746204120",
            address="121059, г. Москва, бул. Украинский, 6",
            profile_url="https://checko.ru/company/implantlab-1167746204120",
        ),
        "https://checko.ru/company/stomatologiya-na-leningradskoy-1025500980273": build_profile_html(
            legal_name='ООО "СТОМАТОЛОГИЯ"',
            short_name='ООО "СТОМАТОЛОГИЯ"',
            inn="5501001234",
            ogrn="1025500980273",
            address="644010, Омская область, г. Омск, ул. Ленина, 3",
            profile_url="https://checko.ru/company/stomatologiya-na-leningradskoy-1025500980273",
        ),
    }
    provider = CheckoHtmlLegalDiscoveryProvider(
        Settings(
            LEGAL_DISCOVERY_PROVIDER="checko_html",
            CHECKO_HTML_ENABLED="1",
            CHECKO_HTML_PAGE_DELAY_MS="0",
            CHECKO_HTML_PROFILE_ENABLED="1",
            CHECKO_HTML_BASE_URL="https://checko.ru",
        ),
        browser_backend=MockBrowserBackend(fixtures),
    )

    companies = await provider.search_companies(
        query="стоматология",
        okved_code="86.23",
        city="Саратов",
        region="Саратовская область",
        limit=10,
    )
    assert len(companies) >= 1, "Checko discovery should still return company candidates"
    assert len(provider.last_debug_info["sample_company_links"]) == 3, "Mock list page should preserve cross-region company links"
    assert provider.last_debug_info["requested_region"] is None
    assert provider.last_debug_info["region_filter_applied"] is False
    assert provider.last_debug_info["region_filter_error"] is None

    saratov = extract_region_city_from_address("410015, Саратовская область, г. Саратов, ул. Радищева, 15")
    omsk = extract_region_city_from_address("644010, Омская область, г. Омск, ул. Ленина, 3")
    moscow = extract_region_city_from_address("121059, г. Москва, бул. Украинский, 6")
    spb = extract_region_city_from_address("191000, г. Санкт-Петербург, Невский проспект, 1")

    assert saratov == {"region": "Саратовская область", "city": "Саратов"}
    assert omsk == {"region": "Омская область", "city": "Омск"}
    assert moscow == {"region": "Москва", "city": "Москва"}
    assert spb == {"region": "Санкт-Петербург", "city": "Санкт-Петербург"}

    print("smoke_checko_html ok")


if __name__ == "__main__":
    asyncio.run(main())
