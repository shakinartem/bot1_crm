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
from app.modules.legal_discovery.checko_parser import parse_checko_profile_page  # noqa: E402
from app.modules.research.browser_backend import MockBrowserBackend  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
PROFILE_FIXTURE = FIXTURES / "checko_profile_center_family_stomatology.html"


def build_list_html() -> str:
    return """
    <html>
      <head><title>Checko 86.23</title></head>
      <body>
        <article class="company-card">
          <a href="/company/firma-praktik-1026402494799">ООО "ФИРМА ПРАКТИК"</a>
          <div>Адрес: г. Саратов, ул. Радищева, 15</div>
          <div>Статус: Действующая компания</div>
        </article>
        <article class="company-card">
          <a href="/company/implantlab-1167746204120">ООО "ИМПЛАНТЛАБ"</a>
          <div>Адрес: г. Москва, бул. Украинский, 6</div>
          <div>Статус: Действующая компания</div>
        </article>
        <article class="company-card">
          <a href="/company/stomatologiya-na-leningradskoy-1025500980273">ООО "СТОМАТОЛОГИЯ"</a>
          <div>Адрес: г. Омск, ул. Ленина, 3</div>
          <div>Статус: Действующая компания</div>
        </article>
      </body>
    </html>
    """


def build_profile_html(*, legal_name: str, short_name: str, inn: str, ogrn: str, address: str, profile_url: str) -> str:
    locality = "Москва" if "г. Москва" in address else address.split(", ")[2].replace("г. ", "")
    region = "Москва" if "г. Москва" in address else address.split(", ")[1]
    street = address.split(", ", 3)[-1]
    return f"""
    <html>
      <head>
        <title>{short_name} - ИНН {inn}</title>
        <meta property="og:title" content="{short_name} - ИНН {inn}" />
        <link rel="canonical" href="{profile_url}" />
        <script type="application/ld+json">
          {{
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "{short_name}",
            "legalName": "{legal_name}",
            "taxID": "{inn}",
            "url": "{profile_url}",
            "identifier": [{{ "propertyID": "ОГРН", "value": "{ogrn}" }}],
            "description": "Компания является действующей.",
            "address": {{
              "@type": "PostalAddress",
              "addressRegion": "{region}",
              "addressLocality": "{locality}",
              "streetAddress": "{street}"
            }}
          }}
        </script>
      </head>
      <body>
        <h1 id="cn">{short_name}</h1>
        <span id="cfn">{legal_name}</span>
        <div class="status success">Действующая компания</div>
        <div>Юридический адрес: {address}</div>
        <span id="copy-address">{address}</span>
        <section id="contacts">
          <span id="copy-x-address">{address}</span>
          <a href="tel:+79990000000">+7 (999) 000-00-00</a>
          <a href="mailto:hello@example.test">hello@example.test</a>
          <a href="https://example.test">Сайт</a>
        </section>
        <div>ОКВЭД: 86.23</div>
        <div>ИНН: {inn}</div>
        <div>ОГРН: {ogrn}</div>
      </body>
    </html>
    """


async def main() -> None:
    profile = parse_checko_profile_page(PROFILE_FIXTURE.read_text(encoding="utf-8"))
    assert profile.short_name == 'ООО "ЦЕНТР СЕМЕЙНОЙ СТОМАТОЛОГИИ"'
    assert profile.legal_name and "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ" in profile.legal_name
    assert profile.inn == "3906346966"
    assert profile.ogrn == "1173926000819"
    assert profile.status == "active"
    assert profile.legal_address and "Калининградская область" in profile.legal_address
    assert profile.emails == ["karen-8708@mail.ru"]
    assert profile.websites and profile.websites[0] in {"http://stomcenter39.ru", "https://stomcenter39.ru"}

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
    assert len(companies) == 3, "Checko discovery should return parsed companies from mock list page"
    assert len(provider.last_debug_info["sample_company_links"]) == 3
    assert provider.last_debug_info["requested_region"] is None
    assert provider.last_debug_info["region_filter_applied"] is False
    assert provider.last_debug_info["region_filter_error"] is None
    assert companies[0].status == "active"
    assert companies[0].city and companies[0].region

    saratov = extract_region_city_from_address("410015, Саратовская область, г. Саратов, ул. Радищева, 15")
    omsk = extract_region_city_from_address("644010, Омская область, г. Омск, ул. Ленина, 3")
    kaliningrad = extract_region_city_from_address("236005, Калининградская область, г. Калининград, ул. Минусинская, д. 22")
    moscow = extract_region_city_from_address("121059, г. Москва, бул. Украинский, 6")
    spb = extract_region_city_from_address("191000, г. Санкт-Петербург, Невский проспект, 1")

    assert saratov == {"region": "Саратовская область", "city": "Саратов"}
    assert omsk == {"region": "Омская область", "city": "Омск"}
    assert kaliningrad == {"region": "Калининградская область", "city": "Калининград"}
    assert moscow == {"region": "Москва", "city": "Москва"}
    assert spb == {"region": "Санкт-Петербург", "city": "Санкт-Петербург"}

    print("smoke_checko_html ok")


if __name__ == "__main__":
    asyncio.run(main())
