from __future__ import annotations

import asyncio
import os
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_bot2_handoff_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import async_session_factory  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.crm.constants import BOT2_READY_STATUS, CompanyStatus, InteractionResult, InteractionType  # noqa: E402
from app.modules.crm.service import get_company, get_company_open_tasks, list_interactions  # noqa: E402


@contextmanager
def temporary_env(**updates: str):
    previous = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            os.environ[key] = value
        get_settings.cache_clear()
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


async def verify_side_effects(company_id: int) -> None:
    async with async_session_factory() as session:
        company = await get_company(session, company_id)
        assert company is not None, "company must exist after handoff"
        assert company.status == CompanyStatus.INTERESTED.value, "thinking must map to interested"

        interactions = await list_interactions(session, company_id)
        assert interactions, "handoff must create an interaction"
        latest = interactions[0]
        assert latest.type == InteractionType.CONSULTATION.value, "handoff must log consultation interaction"
        assert latest.result == InteractionResult.INTERESTED.value, "thinking interaction must map to interested"
        assert latest.summary == "Smoke thinking result", "interaction summary must come from bot2 payload"

        tasks = await get_company_open_tasks(session, company_id)
        assert tasks, "thinking result must create a follow-up task"
        assert tasks[0].title == "Повторно связаться после консультации", "unexpected follow-up task title"
        assert tasks[0].description == "Smoke thinking result", "task description must come from bot2 summary"


async def main() -> None:
    smoke_db = ROOT / "app_bot2_handoff_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()

    with TestClient(app) as client:
        created = client.post(
            "/api/companies",
            json={
                "name": "Стоматология Smoke Handoff",
                "city": "Саратов",
                "phone": "+7 900 000-00-00",
                "status": BOT2_READY_STATUS,
                "priority": "high",
                "notes": "Подготовлена к консультации БОТА 2",
            },
        )
        assert created.status_code == 201, "test company must be created"
        company = created.json()
        company_id = company["id"]

        ready = client.get("/api/bot2/consultation-ready")
        assert ready.status_code == 200, "consultation-ready endpoint must be available"
        ready_ids = {item["id"] for item in ready.json()}
        assert company_id in ready_ids, "consultation-ready must include consultation_planned company"

        filtered = client.get(
            "/api/companies",
            params={"status": BOT2_READY_STATUS, "city": "Саратов", "priority": "high", "limit": 20, "offset": 0},
        )
        assert filtered.status_code == 200, "company filters endpoint must stay available"
        filtered_ids = {item["id"] for item in filtered.json()}
        assert company_id in filtered_ids, "company filters must include the matching consultation_planned company"

        with temporary_env(BOT2_API_TOKEN="bot2-token"):
            unauthorized = client.get("/api/bot2/consultation-ready")
            assert unauthorized.status_code == 401, "bot2 handoff endpoints must require token when BOT2_API_TOKEN is set"

            authorized = client.get(
                "/api/bot2/consultation-ready",
                headers={"Authorization": "Bearer bot2-token"},
            )
            assert authorized.status_code == 200, "bot2 handoff endpoints must accept valid bearer token"

            result = client.post(
                f"/api/bot2/companies/{company_id}/consultation-result",
                json={
                    "result": "thinking",
                    "summary": "Smoke thinking result",
                    "source": "bot2",
                },
                headers={"Authorization": "Bearer bot2-token"},
            )
            assert result.status_code == 200, "bot2 consultation result endpoint must accept thinking result"

        await verify_side_effects(company_id)

    print("smoke_bot2_handoff ok")


if __name__ == "__main__":
    asyncio.run(main())
