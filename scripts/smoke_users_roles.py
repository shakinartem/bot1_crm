from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_users_roles_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")
os.environ.setdefault("DEFAULT_NEW_USER_ROLE", "manager")
os.environ.setdefault("CRM_AUTO_CREATE_USERS", "true")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.crm.constants import CRMUserRole, InteractionType, LeadPriority, TaskStatus  # noqa: E402
from app.modules.crm.schemas import CompanyCreate, FollowUpTaskCreate, InteractionCreate  # noqa: E402
from app.modules.crm.service import add_interaction, create_company, create_task  # noqa: E402
from app.modules.users.service import (  # noqa: E402
    TelegramIdentity,
    assign_company_to_user,
    assign_task_to_user,
    get_or_create_user_from_telegram,
    get_user_companies,
    get_user_tasks,
)


async def main() -> None:
    smoke_db = ROOT / "app_users_roles_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()

    await create_db_schema()

    async with async_session_factory() as session:
        owner = await get_or_create_user_from_telegram(
            session,
            TelegramIdentity(id=1001, username="owner_user", full_name="Owner User"),
        )
        assert owner.role == CRMUserRole.OWNER.value, "first telegram user must become owner"

        manager = await get_or_create_user_from_telegram(
            session,
            TelegramIdentity(id=1002, username="manager_user", full_name="Manager User"),
        )
        assert manager.role == CRMUserRole.MANAGER.value, "second user must get default manager role"

        company = await create_company(
            session,
            CompanyCreate(
                name="Users Roles Smoke Clinic",
                city="Saratov",
                phone="+79000000001",
                status="new",
                priority="high",
                created_by_user_id=owner.id,
            ),
        )

        assignment = await assign_company_to_user(
            session,
            company.id,
            manager.id,
            actor_user_id=owner.id,
        )
        assert assignment.assigned_user_id == manager.id, "company must be assigned to manager"

        companies = await get_user_companies(session, manager.id)
        assert any(item.id == company.id for item in companies), "assigned company must be listed for manager"

        task = await create_task(
            session,
            FollowUpTaskCreate(
                company_id=company.id,
                title="Call assigned clinic",
                due_at=None,
                status=TaskStatus.OPEN,
                priority=LeadPriority.HIGH,
                assigned_user_id=manager.id,
                created_by_user_id=owner.id,
            ),
        )
        await assign_task_to_user(session, task.id, manager.id, actor_user_id=owner.id)
        tasks = await get_user_tasks(session, manager.id)
        assert any(item.id == task.id for item in tasks), "assigned task must be listed for manager"

        interaction = await add_interaction(
            session,
            InteractionCreate(
                company_id=company.id,
                type=InteractionType.NOTE,
                summary="Manual attribution check",
                created_by="smoke",
                created_by_user_id=owner.id,
            ),
        )
        assert interaction.created_by_user_id == owner.id, "interaction author must be stored"

    with TestClient(app) as client:
        users_response = client.get("/api/users")
        assert users_response.status_code == 200, "GET /api/users must work"
        users = users_response.json()
        assert len(users) >= 2, "users endpoint must list created users"

        owner_id = users[0]["id"]
        user_response = client.get(f"/api/users/{owner_id}")
        assert user_response.status_code == 200, "GET /api/users/{id} must work"

        patch_response = client.patch(
            f"/api/users/{owner_id}",
            json={"full_name": "Owner Updated"},
        )
        assert patch_response.status_code == 200, "PATCH /api/users/{id} must work"
        assert patch_response.json()["full_name"] == "Owner Updated"

        company_id = client.get("/api/users").json()[1]["id"]
        assign_response = client.post(
            "/api/companies/1/assign",
            json={"user_id": company_id},
        )
        assert assign_response.status_code == 200, "POST /api/companies/{id}/assign must work"

        user_companies = client.get(f"/api/users/{company_id}/companies")
        assert user_companies.status_code == 200, "GET /api/users/{id}/companies must work"
        assert user_companies.json(), "assigned companies endpoint must not be empty"

        user_tasks = client.get(f"/api/users/{company_id}/tasks")
        assert user_tasks.status_code == 200, "GET /api/users/{id}/tasks must work"
        assert user_tasks.json(), "assigned tasks endpoint must not be empty"

        context = client.get("/api/bot2/companies/1/consultation-context")
        assert context.status_code == 200, "Bot2 context endpoint must work"
        assignment_block = context.json()["assignment"]
        assert assignment_block["assigned_user_id"] == company_id, "Bot2 assignment block must include assigned user"

    print("smoke_users_roles ok")


if __name__ == "__main__":
    asyncio.run(main())
