from __future__ import annotations

import asyncio
import os
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_bot2_context_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import async_session_factory  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.crm.constants import ContactType, InteractionResult, InteractionType, LeadPriority, TaskStatus  # noqa: E402
from app.modules.crm.schemas import ContactPointCreate, DecisionMakerCreate, FollowUpTaskCreate, InteractionCreate  # noqa: E402
from app.modules.crm.service import add_contact_point, add_decision_maker, create_task, add_interaction  # noqa: E402


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


async def seed_related_entities(company_id: int) -> None:
    async with async_session_factory() as session:
        await add_decision_maker(
            session,
            DecisionMakerCreate(
                company_id=company_id,
                full_name="Иван Иванов",
                role="Владелец",
                phone="+79001112233",
                email="owner@example.com",
                telegram="@owner",
                is_primary=True,
                notes="Главный ЛПР",
            ),
        )
        await add_contact_point(
            session,
            ContactPointCreate(
                company_id=company_id,
                type=ContactType.TELEGRAM,
                value="@clinic_sales",
                label="TG",
                is_primary=True,
                notes="Основной контакт",
            ),
        )
        await add_interaction(
            session,
            InteractionCreate(
                company_id=company_id,
                type=InteractionType.CALL,
                result=InteractionResult.INTERESTED,
                summary="Последний звонок: готовы обсудить digital-воронку",
                next_action="Подготовить консультацию",
                created_by="smoke",
            ),
        )
        await add_interaction(
            session,
            InteractionCreate(
                company_id=company_id,
                type=InteractionType.PROPOSAL,
                result=InteractionResult.PROPOSAL_REQUESTED,
                summary="Мини-КП отправлено после звонка",
                created_by="smoke",
            ),
        )
        await create_task(
            session,
            FollowUpTaskCreate(
                company_id=company_id,
                title="Подготовить консультацию",
                description="Собрать контекст для БОТА 2",
                status=TaskStatus.OPEN,
                priority=LeadPriority.HIGH,
            ),
        )


async def main() -> None:
    smoke_db = ROOT / "app_bot2_context_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()

    with TestClient(app) as client:
        created = client.post(
            "/api/companies",
            json={
                "name": "Стоматология Context Smoke",
                "city": "Саратов",
                "phone": "+7 900 111-22-33",
                "status": "consultation_planned",
                "priority": "high",
                "source": "cold_call",
                "notes": "Нужно понять, где теряют заявки",
            },
        )
        assert created.status_code == 201, "test company must be created"
        company_id = created.json()["id"]

    await seed_related_entities(company_id)

    with TestClient(app) as client:
        with temporary_env(BOT2_API_TOKEN=""):
            context = client.get(f"/api/bot2/companies/{company_id}/consultation-context")
            assert context.status_code == 200, "consultation context endpoint must be available"
            payload = context.json()
            for key in (
                "company",
                "decision_makers",
                "contacts",
                "recent_interactions",
                "open_tasks",
                "latest_proposal",
                "latest_call_result",
                "recommended_next_step",
                "sales_summary",
            ):
                assert key in payload, f"{key} must be present in consultation context"
            assert payload["decision_makers"], "decision makers must be returned"
            assert payload["contacts"], "contacts must be returned"
            assert payload["recent_interactions"], "recent interactions must be returned"
            assert payload["open_tasks"], "open tasks must be returned"
            assert payload["latest_proposal"] is not None, "latest proposal must be present"
            assert payload["latest_call_result"] is not None, "latest call result must be present"
            assert payload["recommended_next_step"] == "Подготовить консультацию", "open task title must win as next step"

        with temporary_env(BOT2_API_TOKEN="bot2-token"):
            unauthorized = client.get(f"/api/bot2/companies/{company_id}/consultation-context")
            assert unauthorized.status_code == 401, "context endpoint must require token when BOT2_API_TOKEN is set"
            authorized = client.get(
                f"/api/bot2/companies/{company_id}/consultation-context",
                headers={"Authorization": "Bearer bot2-token"},
            )
            assert authorized.status_code == 200, "context endpoint must accept valid BOT2 token"

    print("smoke_bot2_context ok")


if __name__ == "__main__":
    asyncio.run(main())
