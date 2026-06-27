from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_company_edit.db")
os.environ.setdefault("AI_PROVIDER", "fallback")
os.environ.setdefault("LEGAL_DISCOVERY_PROVIDER", "mock")

from app.database import create_db_schema, async_session_factory, get_settings  # noqa: E402
from app.modules.admin_reset.service import reset_database  # noqa: E402
from app.modules.crm.models import AuditLog, Company, ContactPoint  # noqa: E402
from app.modules.crm.service import update_company_manual_fields  # noqa: E402


class DummyPayload:
    def model_dump(self, exclude_unset=False):
        return {
            "name": "Название из payload",
            "city": "Казань",
            "phone": "+79271234567",
        }


def run() -> None:
    settings = get_settings()
    settings.allow_db_reset = True

    async def main() -> None:
        await create_db_schema()
        async with async_session_factory() as session:
            await reset_database(session, mode="crm_only", keep_users=True, clear_debug_files=False)

            company = Company(name="Старое название", city="Москва", phone="+74951234567", status="new")
            session.add(company)
            await session.commit()
            await session.refresh(company)

            updated = await update_company_manual_fields(
                session,
                company.id,
                DummyPayload(),
                user_id=None,
            )
            assert updated.name == "Название из payload"
            assert updated.city == "Казань"

            logs = (await session.execute(AuditLog.__table__.select().where(AuditLog.company_id == company.id))).fetchall()
            fields = {row.field_name for row in logs}
            assert "name" in fields, fields
            assert "city" in fields, fields
            assert len(logs) >= 2

            print("smoke_company_edit ok")

    import asyncio
    asyncio.run(main())


if __name__ == "__main__":
    run()