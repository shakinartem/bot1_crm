from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_analytics_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")
os.environ.setdefault("AI_PROVIDER", "fallback")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.analytics.service import (  # noqa: E402
    build_city_analytics,
    build_cold_base,
    build_funnel_analytics,
    build_source_analytics,
    export_analytics_csv,
    get_company_lead_score,
    list_lead_scores,
)
from app.modules.crm.constants import InteractionResult, InteractionType, LeadPriority, TaskStatus  # noqa: E402
from app.modules.crm.models import FollowUpTask  # noqa: E402
from app.modules.crm.schemas import CompanyCreate, DecisionMakerCreate, InteractionCreate  # noqa: E402
from app.modules.crm.service import add_decision_maker, add_interaction, create_company  # noqa: E402


async def seed_data() -> dict[str, int]:
    now = datetime.now()

    async with async_session_factory() as session:
        hot = await create_company(
            session,
            CompanyCreate(
                name="Smile Clinic",
                city="Ufa",
                region="Bashkortostan",
                source="Yandex Maps",
                phone="+79990000001",
                website="https://smile.example.com",
                notes="Interested in consultation and proposal",
                status="proposal_sent",
                priority="high",
            ),
        )
        await add_decision_maker(
            session,
            DecisionMakerCreate(
                company_id=hot.id,
                full_name="Anna Admin",
                role="Owner",
                phone="+79990000002",
                is_primary=True,
            ),
        )
        await add_interaction(
            session,
            InteractionCreate(
                company_id=hot.id,
                type=InteractionType.CALL,
                result=InteractionResult.PROPOSAL_REQUESTED,
                summary="Requested proposal after consultation",
                created_by="smoke",
            ),
        )
        session.add(
            FollowUpTask(
                company_id=hot.id,
                title="Follow up on proposal",
                due_at=now,
                due_date=now,
                status=TaskStatus.OPEN.value,
                priority=LeadPriority.HIGH.value,
            )
        )

        warm = await create_company(
            session,
            CompanyCreate(
                name="Dental Pro",
                city="Saratov",
                region="Saratov Oblast",
                source="CSV Ufa",
                phone="+79990000003",
                notes="Consultation booked",
                status="consultation_planned",
                priority="medium",
            ),
        )
        await add_interaction(
            session,
            InteractionCreate(
                company_id=warm.id,
                type=InteractionType.CALL,
                result=InteractionResult.CONSULTATION_BOOKED,
                summary="Consultation scheduled",
                created_by="smoke",
            ),
        )

        cold = await create_company(
            session,
            CompanyCreate(
                name="Cold Base Clinic",
                city="Samara",
                region="Samara Oblast",
                source="CSV Ufa",
                status="new",
                priority="low",
            ),
        )

        stale = await create_company(
            session,
            CompanyCreate(
                name="Stale Research Lead",
                city="Ufa",
                region="Bashkortostan",
                source="2GIS",
                phone="+79990000004",
                status="interested",
                priority="high",
            ),
        )
        await add_interaction(
            session,
            InteractionCreate(
                company_id=stale.id,
                type=InteractionType.CALL,
                result=InteractionResult.INTERESTED,
                summary="Interested but went silent",
                created_by="smoke",
                next_action="Call back",
                next_action_at=now - timedelta(days=18),
            ),
        )
        session.add(
            FollowUpTask(
                company_id=stale.id,
                title="Overdue callback",
                due_at=now - timedelta(days=2),
                due_date=now - timedelta(days=2),
                status=TaskStatus.OPEN.value,
                priority=LeadPriority.HIGH.value,
            )
        )

        await session.commit()
        return {
            "hot_id": hot.id,
            "warm_id": warm.id,
            "cold_id": cold.id,
            "stale_id": stale.id,
        }


async def verify_services(company_ids: dict[str, int]) -> None:
    async with async_session_factory() as session:
        funnel = await build_funnel_analytics(session)
        assert funnel.total_companies >= 4, "funnel must count companies"

        sources = await build_source_analytics(session)
        assert sources, "source analytics must not be empty"

        cities = await build_city_analytics(session)
        assert cities, "city analytics must not be empty"

        scores = await list_lead_scores(session, limit=20)
        assert scores, "scores must not be empty"

        hot_score = await get_company_lead_score(session, company_ids["hot_id"])
        assert hot_score is not None, "company score must be available"
        assert hot_score.score >= 50, "hot lead should have high score"

        cold_base = await build_cold_base(session)
        assert any(item.company_id == company_ids["cold_id"] for item in cold_base), "cold base lead must be listed"

        export = await export_analytics_csv(session, "scores")
        assert Path(export.file_path).exists(), "analytics CSV export must exist"


def verify_api(company_ids: dict[str, int]) -> None:
    with TestClient(app) as client:
        funnel = client.get("/api/analytics/funnel")
        assert funnel.status_code == 200, "funnel endpoint must work"

        sources = client.get("/api/analytics/sources")
        assert sources.status_code == 200, "sources endpoint must work"

        cities = client.get("/api/analytics/cities")
        assert cities.status_code == 200, "cities endpoint must work"

        scores = client.get("/api/analytics/scores")
        assert scores.status_code == 200, "scores endpoint must work"

        cold = client.get("/api/analytics/cold-base")
        assert cold.status_code == 200, "cold-base endpoint must work"

        company_score = client.get(f"/api/companies/{company_ids['hot_id']}/score")
        assert company_score.status_code == 200, "company score endpoint must work"

        export = client.get("/api/analytics/export", params={"type": "sources"})
        assert export.status_code == 200, "analytics export endpoint must work"


async def main() -> None:
    smoke_db = ROOT / "app_analytics_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()

    await create_db_schema()
    company_ids = await seed_data()
    await verify_services(company_ids)
    verify_api(company_ids)
    print("smoke_analytics ok")


if __name__ == "__main__":
    asyncio.run(main())
