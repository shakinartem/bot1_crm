from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_intelligence_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")
os.environ.setdefault("AI_PROVIDER", "fallback")
os.environ.setdefault("LEGAL_PROVIDER", "mock")
os.environ.setdefault("SEARCH_PROVIDER", "mock")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.crm.schemas import CompanyCreate  # noqa: E402
from app.modules.crm.service import create_company  # noqa: E402
from app.modules.enrichment.schemas import FetchResult  # noqa: E402
from app.modules.intelligence import service as intelligence_service  # noqa: E402
from app.modules.intelligence.site_parser import parse_company_site  # noqa: E402
from app.modules.intelligence.website_resolver import resolve_official_website  # noqa: E402
from app.modules.intelligence.providers.mock_search import MockSearchProvider  # noqa: E402
from app.modules.intelligence.schemas import LegalCompany  # noqa: E402


SAMPLE_HTML = """
<html>
  <head>
    <title>Дентал Браво — стоматология в Саратове</title>
    <meta name="description" content="Стоматология с онлайн-записью, отзывами, имплантацией и мессенджерами" />
  </head>
  <body>
    <header>
      <p>ООО "ДЕНТАЛ БРАВО"</p>
      <p>ИНН 7701234567</p>
      <p>г. Саратов, ул. Радищева, 15</p>
      <p>Телефон: +7 (999) 000-11-22</p>
      <p>Email: info@dental-bravo.example</p>
    </header>
    <nav>
      <a href="/doctors">Врачи</a>
      <a href="/prices">Цены</a>
      <a href="/reviews">Отзывы</a>
      <a href="/contacts">Контакты</a>
      <a href="https://vk.com/dentalbravo">VK</a>
      <a href="https://wa.me/79990001122">WhatsApp</a>
      <a href="https://t.me/dentalbravo">Telegram</a>
    </nav>
    <main>
      <h1>Онлайн-запись в стоматологию</h1>
      <p>Записаться можно онлайн. Есть отзывы, врачи, формы, цены и имплантация all-on-4.</p>
    </main>
  </body>
</html>
""".strip()


async def fake_fetch_website(url: str, timeout: int = 10) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        status="success",
        http_status=200,
        html=SAMPLE_HTML,
        error_message=None,
    )


def verify_parser() -> None:
    parsed = parse_company_site(SAMPLE_HTML, "https://dental-bravo.example")
    assert parsed.page_title == "Дентал Браво — стоматология в Саратове", "title must be parsed"
    assert parsed.contacts.phones, "phone must be parsed"
    assert parsed.contacts.emails, "email must be parsed"
    assert parsed.socials.vk_links, "VK must be parsed"
    assert parsed.socials.whatsapp_links, "WhatsApp must be parsed"
    assert parsed.signals.has_online_booking is True, "online booking must be detected"
    assert parsed.signals.has_reviews_section is True, "reviews must be detected"
    assert parsed.signals.has_implantation_keywords is True, "implantation keyword must be detected"


async def seed_company() -> int:
    async with async_session_factory() as session:
        company = await create_company(
            session,
            CompanyCreate(
                name="Дентал Браво",
                city="Саратов",
                status="consultation_planned",
                source="cold_base",
                notes="smoke intelligence",
            ),
        )
        return company.id


async def verify_resolver() -> None:
    from app.modules.intelligence import website_resolver as resolver_module

    original_fetch = resolver_module.fetch_website
    resolver_module.fetch_website = fake_fetch_website
    try:
        legal = LegalCompany(
            provider="mock",
            inn="7701234567",
            ogrn="1027700000001",
            legal_name='ООО "ДЕНТАЛ БРАВО"',
            short_name="Дентал Браво",
            address="г. Саратов, ул. Радищева, 15",
            city="Саратов",
            region="Саратовская область",
            status="active",
            okved="86.23",
            confidence=0.92,
        )
        result = await resolve_official_website(legal, MockSearchProvider(), city="Саратов", known_phone="+79990001122")
        assert result.selected_url == "https://dental-bravo.example", "resolver must select mock official site"
        assert result.confidence > 0, "resolver confidence must be positive"
    finally:
        resolver_module.fetch_website = original_fetch


async def verify_service(company_id: int) -> None:
    from app.modules.intelligence import website_resolver as resolver_module

    original_service_fetch = intelligence_service.fetch_website
    original_resolver_fetch = resolver_module.fetch_website
    intelligence_service.fetch_website = fake_fetch_website
    resolver_module.fetch_website = fake_fetch_website
    try:
        async with async_session_factory() as session:
            result = await intelligence_service.enrich_company_intelligence(session, company_id, use_ai=False)
            assert result.status in {"success", "partial"}, "intelligence must finish"
            assert result.selected_legal is not None, "legal company must be selected"
            assert result.selected_legal.inn == "7701234567", "INN must be resolved"
            assert result.website_resolution is not None and result.website_resolution.selected_url, "website must be resolved"
            latest = await intelligence_service.get_latest_intelligence(session, company_id)
            assert latest is not None, "snapshot must exist"
            assert latest.inn == "7701234567", "snapshot must persist INN"
            company = await intelligence_service.get_company(session, company_id)
            assert company is not None and company.website, "company website must be updated"
            assert company.phone, "company phone must be filled from site"
            assert any(contact.type == "vk" for contact in company.contacts), "contact points must be created"
    finally:
        intelligence_service.fetch_website = original_service_fetch
        resolver_module.fetch_website = original_resolver_fetch


def verify_api(company_id: int) -> None:
    from app.modules.intelligence import website_resolver as resolver_module

    original_service_fetch = intelligence_service.fetch_website
    original_resolver_fetch = resolver_module.fetch_website
    intelligence_service.fetch_website = fake_fetch_website
    resolver_module.fetch_website = fake_fetch_website
    try:
        with TestClient(app) as client:
            legal = client.post(f"/api/companies/{company_id}/intelligence/find-legal")
            assert legal.status_code == 200, "find-legal endpoint must work"
            legal_payload = legal.json()
            assert legal_payload and legal_payload[0]["inn"] == "7701234567", "legal candidate must be returned"

            resolution = client.post(f"/api/companies/{company_id}/intelligence/resolve-website")
            assert resolution.status_code == 200, "resolve-website endpoint must work"
            assert resolution.json()["selected_url"] == "https://dental-bravo.example", "website must resolve via API"

            enriched = client.post(
                f"/api/companies/{company_id}/intelligence/enrich",
                json={"use_ai": True},
            )
            assert enriched.status_code == 200, "enrich endpoint must work"
            enriched_payload = enriched.json()
            assert enriched_payload["selected_legal"]["inn"] == "7701234567", "enrichment must return selected INN"

            latest = client.get(f"/api/companies/{company_id}/intelligence/latest")
            assert latest.status_code == 200, "latest endpoint must work"
            assert latest.json()["website_url"] == "https://dental-bravo.example", "latest snapshot must expose website"

            history = client.get(f"/api/companies/{company_id}/intelligence/history")
            assert history.status_code == 200, "history endpoint must work"
            history_payload = history.json()
            assert history_payload, "history must not be empty"

            snapshot_id = history_payload[0]["id"]
            snapshot = client.get(f"/api/companies/{company_id}/intelligence/{snapshot_id}")
            assert snapshot.status_code == 200, "snapshot endpoint must work"

            context = client.get(f"/api/bot2/companies/{company_id}/consultation-context")
            assert context.status_code == 200, "Bot2 context endpoint must work"
            context_payload = context.json()
            assert "intelligence" in context_payload, "Bot2 context must include intelligence block"
            assert context_payload["intelligence"]["inn"] == "7701234567", "Bot2 intelligence block must expose INN"
    finally:
        intelligence_service.fetch_website = original_service_fetch
        resolver_module.fetch_website = original_resolver_fetch


async def main() -> None:
    smoke_db = ROOT / "app_intelligence_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()

    verify_parser()
    await create_db_schema()
    company_id = await seed_company()
    await verify_resolver()
    await verify_service(company_id)
    verify_api(company_id)
    print("smoke_intelligence ok")


if __name__ == "__main__":
    asyncio.run(main())
