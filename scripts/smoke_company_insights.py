from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_company_insights_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.crm.schemas import CompanyCreate  # noqa: E402
from app.modules.crm.service import create_company  # noqa: E402
from app.modules.insights.schemas import CompanyInsightSnapshotCreate  # noqa: E402
from app.modules.insights.service import (  # noqa: E402
    create_company_insight_snapshot,
    get_company_insight_history,
    get_latest_company_insight,
)


async def seed_company_with_insight() -> int:
    async with async_session_factory() as session:
        company = await create_company(
            session,
            CompanyCreate(
                name="Insight Smoke Clinic",
                city="Saratov",
                source="smoke",
                status="interested",
            ),
        )
        snapshot = await create_company_insight_snapshot(
            session,
            CompanyInsightSnapshotCreate(
                company_id=company.id,
                insight_type="sales_intelligence",
                title="Sales intelligence / cold call plan",
                status="success",
                payload={
                    "material_score": {"total_score": 62, "grade": "normal"},
                    "cold_call_plan": {"generation_mode": "fallback", "first_offer": "Offer diagnostic"},
                    "saved_at": "2026-06-01T10:00:00",
                },
                summary="Material score: 62/100 (normal). First offer: Offer diagnostic. Mode: fallback.",
                source="sales_intelligence",
                version="smoke-v1",
            ),
        )
        assert snapshot.id > 0
        return company.id


async def verify_service(company_id: int) -> None:
    async with async_session_factory() as session:
        latest = await get_latest_company_insight(session, company_id, "sales_intelligence")
        assert latest is not None
        assert latest.source == "sales_intelligence"

        history = await get_company_insight_history(session, company_id, insight_type="sales_intelligence")
        assert len(history) == 1
        assert history[0].id == latest.id


async def verify_api(company_id: int) -> None:
    with TestClient(app) as client:
        history_response = client.get(
            f"/api/companies/{company_id}/insights",
            params={"insight_type": "sales_intelligence"},
        )
        assert history_response.status_code == 200
        history_payload = history_response.json()
        assert len(history_payload) == 1
        insight_id = history_payload[0]["id"]
        assert history_payload[0]["payload"]["material_score"]["total_score"] == 62

        latest_response = client.get(
            f"/api/companies/{company_id}/insights/latest",
            params={"insight_type": "sales_intelligence"},
        )
        assert latest_response.status_code == 200
        latest_payload = latest_response.json()
        assert latest_payload["id"] == insight_id
        assert latest_payload["source"] == "sales_intelligence"

        detail_response = client.get(f"/api/companies/{company_id}/insights/{insight_id}")
        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        assert detail_payload["payload"]["cold_call_plan"]["generation_mode"] == "fallback"


async def main() -> None:
    smoke_db = ROOT / "app_company_insights_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()

    await create_db_schema()
    company_id = await seed_company_with_insight()
    await verify_service(company_id)
    await verify_api(company_id)
    print("smoke_company_insights ok")


if __name__ == "__main__":
    asyncio.run(main())
