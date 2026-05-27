from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_enrichment_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")
os.environ.setdefault("AI_PROVIDER", "fallback")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.crm.schemas import CompanyCreate  # noqa: E402
from app.modules.crm.service import create_company  # noqa: E402
from app.modules.enrichment import service as enrichment_service  # noqa: E402
from app.modules.enrichment.analyzer import analyze_website_html, build_enrichment_hypotheses  # noqa: E402
from app.modules.enrichment.schemas import FetchResult  # noqa: E402


SAMPLE_HTML = """
<html>
  <head>
    <title>Smile Clinic - Dental Care</title>
    <meta name="description" content="Стоматология с онлайн-записью, отзывами и имплантацией" />
  </head>
  <body>
    <nav>
      <a href="/doctors">Врачи</a>
      <a href="/prices">Цены</a>
      <a href="/reviews">Отзывы</a>
      <a href="/contacts">Контакты</a>
      <a href="https://vk.com/smileclinic">VK</a>
      <a href="https://t.me/smileclinic">Telegram</a>
      <a href="https://wa.me/79990001122">WhatsApp</a>
      <a href="https://yandex.ru/maps/org/smileclinic/123">Yandex Maps</a>
      <a href="https://2gis.ru/saratov/firm/123">2GIS</a>
    </nav>
    <section>
      <h1>Онлайн-запись в стоматологию</h1>
      <p>Записаться на прием можно онлайн. Есть отзывы, врачи, цены, имплантация all-on-4 и брекеты.</p>
      <p>Телефон: +7 (999) 000-11-22</p>
      <p>Email: info@smile.example.com</p>
      <p>Акция месяца и детская стоматология.</p>
    </section>
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


def verify_analyzer() -> None:
    analysis = analyze_website_html(SAMPLE_HTML, "https://smile.example.com")
    hypotheses = build_enrichment_hypotheses(analysis)
    assert analysis.page_title == "Smile Clinic - Dental Care", "title must be parsed"
    assert analysis.detected_contacts.phones, "phones must be parsed"
    assert analysis.detected_socials["vk"], "VK link must be detected"
    assert analysis.signals.has_online_booking is True, "online booking must be detected"
    assert analysis.signals.has_reviews_section is True, "reviews signal must be detected"
    assert isinstance(hypotheses, list), "hypotheses must be a list"


async def seed_company() -> int:
    async with async_session_factory() as session:
        company = await create_company(
            session,
            CompanyCreate(
                name="Enrichment Smoke Clinic",
                city="Saratov",
                phone="+79990001122",
                website="smile.example.com",
                status="consultation_planned",
                source="cold_base",
                notes="Проверка research enrichment",
            ),
        )
        return company.id


async def verify_service(company_id: int) -> None:
    original_fetch = enrichment_service.fetch_website
    enrichment_service.fetch_website = fake_fetch_website
    try:
        async with async_session_factory() as session:
            result = await enrichment_service.enrich_company_website(session, company_id, use_ai=False)
            assert result.status == "success", "service enrichment must succeed"
            latest = await enrichment_service.get_latest_enrichment(session, company_id)
            assert latest is not None, "latest enrichment must exist"
            assert latest.page_title == "Smile Clinic - Dental Care", "snapshot title must be saved"
    finally:
        enrichment_service.fetch_website = original_fetch


def verify_api(company_id: int) -> None:
    original_fetch = enrichment_service.fetch_website
    enrichment_service.fetch_website = fake_fetch_website
    try:
        with TestClient(app) as client:
            created = client.post(
                f"/api/companies/{company_id}/enrichment/website",
                json={"use_ai": True},
            )
            assert created.status_code == 200, "POST enrichment endpoint must work"
            payload = created.json()
            assert payload["status"] == "success", "enrichment result must be success"
            assert payload["signals"]["has_online_booking"] is True, "signal must be returned"

            latest = client.get(f"/api/companies/{company_id}/enrichment/latest")
            assert latest.status_code == 200, "latest enrichment endpoint must work"
            latest_payload = latest.json()
            assert latest_payload["page_title"] == "Smile Clinic - Dental Care", "latest snapshot must return title"

            history = client.get(f"/api/companies/{company_id}/enrichment/history")
            assert history.status_code == 200, "history endpoint must work"
            history_payload = history.json()
            assert history_payload, "history must not be empty"

            snapshot_id = history_payload[0]["id"]
            snapshot = client.get(f"/api/companies/{company_id}/enrichment/{snapshot_id}")
            assert snapshot.status_code == 200, "snapshot endpoint must work"

            context = client.get(f"/api/bot2/companies/{company_id}/consultation-context")
            assert context.status_code == 200, "Bot 2 context endpoint must work"
            context_payload = context.json()
            assert "enrichment" in context_payload, "Bot 2 context must include enrichment block"
            assert context_payload["enrichment"]["status"] == "success", "Bot 2 enrichment status must be present"
    finally:
        enrichment_service.fetch_website = original_fetch


async def main() -> None:
    smoke_db = ROOT / "app_enrichment_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()

    verify_analyzer()
    await create_db_schema()
    company_id = await seed_company()
    await verify_service(company_id)
    verify_api(company_id)
    print("smoke_enrichment ok")


if __name__ == "__main__":
    asyncio.run(main())
