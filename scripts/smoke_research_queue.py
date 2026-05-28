from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_research_queue_smoke.db")
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
from app.modules.research import service as research_service  # noqa: E402
from app.modules.research.schemas import FetchResult, WebsiteCandidate, WebsiteResolutionResult  # noqa: E402
from app.modules.research_queue.service import (  # noqa: E402
    create_research_jobs_for_companies,
    get_queue_status,
    get_research_jobs,
    run_research_batch,
)


SAMPLE_HTML = """
<html>
  <head>
    <title>Dental Bravo</title>
    <meta name="description" content="Стоматология с онлайн-записью и отзывами" />
  </head>
  <body>
    <p>ООО "ДЕНТАЛ БРАВО"</p>
    <p>ИНН 7701234567</p>
    <p>Телефон: +7 (999) 000-11-22</p>
    <p>Email: info@dental-bravo.example</p>
    <a href="https://vk.com/dentalbravo">VK</a>
    <a href="https://wa.me/79990001122">WhatsApp</a>
    <a href="/reviews">Отзывы</a>
    <a href="/book">Онлайн-запись</a>
    <p>Имплантация и элайнеры</p>
  </body>
</html>
""".strip()


async def fake_fetch(url: str) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        status="success",
        http_status=200,
        html=SAMPLE_HTML,
        text_excerpt=SAMPLE_HTML[:500],
    )


async def fake_backend(url: str) -> FetchResult:
    return await fake_fetch(url)


async def fake_resolve(company, legal_company=None) -> WebsiteResolutionResult:
    return WebsiteResolutionResult(
        selected_url="https://dental-bravo.example",
        confidence=80,
        reasons=["Mock website match"],
        candidates=[
            WebsiteCandidate(
                url="https://dental-bravo.example",
                confidence=80,
                reasons=["Mock website match"],
                is_official_candidate=True,
            )
        ],
        references=[],
    )


async def seed_companies() -> list[int]:
    ids: list[int] = []
    async with async_session_factory() as session:
        for index in range(3):
            company = await create_company(
                session,
                CompanyCreate(
                    name=f"Dental Bravo {index}",
                    legal_name='ООО "ДЕНТАЛ БРАВО"',
                    inn=f"770123456{index}",
                    city="Саратов",
                    source="legal_discovery:mock",
                    status="research_needed",
                ),
            )
            ids.append(company.id)
    return ids


async def verify_service(company_ids: list[int]) -> None:
    original_resolve = research_service.resolve_company_website
    original_backend = research_service.get_fetch_backend
    research_service.resolve_company_website = fake_resolve
    research_service.get_fetch_backend = lambda settings: fake_backend
    try:
        async with async_session_factory() as session:
            jobs = await create_research_jobs_for_companies(session, company_ids)
            assert len(jobs) == len(company_ids), "jobs must be created for each company"
            duplicate_jobs = await create_research_jobs_for_companies(session, company_ids)
            assert len(duplicate_jobs) == 0, "duplicate open jobs must not be created"
        await run_research_batch(async_session_factory, concurrency=2, limit=10)
        async with async_session_factory() as session:
            status = await get_queue_status(session)
            assert status.success >= len(company_ids), "jobs must finish successfully"
            jobs = await get_research_jobs(session)
            assert jobs and jobs[0].status == "success", "job status must be success"
            latest = await research_service.get_latest_research(session, company_ids[0])
            assert latest is not None and latest.website_url == "https://dental-bravo.example", "research snapshot must exist"
            company = await research_service.get_company(session, company_ids[0])
            assert company is not None and company.website == "https://dental-bravo.example", "company website must be updated"
            assert any(contact.type == "vk" for contact in company.contacts), "contact points must be created"
    finally:
        research_service.resolve_company_website = original_resolve
        research_service.get_fetch_backend = original_backend


def verify_api(company_ids: list[int]) -> None:
    original_resolve = research_service.resolve_company_website
    original_backend = research_service.get_fetch_backend
    research_service.resolve_company_website = fake_resolve
    research_service.get_fetch_backend = lambda settings: fake_backend
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/research/jobs",
                json={"company_ids": company_ids, "job_type": "full_research"},
            )
            assert created.status_code == 200, "job creation endpoint must work"

            batch = client.post("/api/research/jobs/run-batch", json={"concurrency": 2, "limit": 10})
            assert batch.status_code == 200, "batch endpoint must work"

            listing = client.get("/api/research/jobs")
            assert listing.status_code == 200 and listing.json(), "job listing endpoint must work"

            latest = client.get(f"/api/companies/{company_ids[0]}/research/latest")
            assert latest.status_code == 200, "company latest research endpoint must work"

            history = client.get(f"/api/companies/{company_ids[0]}/research/history")
            assert history.status_code == 200 and history.json(), "company research history endpoint must work"

            context = client.get(f"/api/bot2/companies/{company_ids[0]}/consultation-context")
            assert context.status_code == 200, "Bot2 context endpoint must work"
            assert "research" in context.json(), "Bot2 context must include research block"
    finally:
        research_service.resolve_company_website = original_resolve
        research_service.get_fetch_backend = original_backend


async def main() -> None:
    smoke_db = ROOT / "app_research_queue_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()
    company_ids = await seed_companies()
    await verify_service(company_ids)
    verify_api(company_ids)
    print("smoke_research_queue ok")


if __name__ == "__main__":
    asyncio.run(main())
