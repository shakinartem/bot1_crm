from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_company_manual_edit_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.crm.schemas import CompanyCreate, CompanyManualUpdate  # noqa: E402
from app.modules.crm.service import create_company, get_company, update_company_manual_fields  # noqa: E402


async def main() -> None:
    smoke_db = ROOT / "app_company_manual_edit_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()

    async with async_session_factory() as session:
        company = await create_company(
            session,
            CompanyCreate(
                name="Edit Clinic",
                city="Саратов",
                source="smoke",
            ),
        )
        updated = await update_company_manual_fields(
            session,
            company.id,
            CompanyManualUpdate(
                display_name="Edit Clinic Pro",
                checko_profile_url="https://checko.ru/company/edit-clinic-pro-1234567890123/",
                map_url="https://yandex.ru/maps/org/test",
                email="hello@edit-clinic.test",
                status="new",
                priority="high",
                notes="updated manually",
            ),
            user_id=123,
        )
        assert updated is not None
        refreshed = await get_company(session, company.id)
        assert refreshed is not None
        assert refreshed.name == "Edit Clinic Pro"
        assert refreshed.checko_profile_url == "https://checko.ru/company/edit-clinic-pro-1234567890123/"
        assert refreshed.maps_url == "https://yandex.ru/maps/org/test"
        assert refreshed.status == "new"
        assert refreshed.priority == "high"
        assert any(contact.value == "hello@edit-clinic.test" for contact in refreshed.contacts)
    print("smoke_company_manual_edit ok")


if __name__ == "__main__":
    asyncio.run(main())
