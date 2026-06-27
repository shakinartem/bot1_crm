from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_touch_workflow.db")
os.environ.setdefault("AI_PROVIDER", "fallback")
os.environ.setdefault("LEGAL_DISCOVERY_PROVIDER", "mock")

from app.database import create_db_schema, async_session_factory  # noqa: E402
from app.modules.admin_reset.service import reset_database  # noqa: E402
from app.modules.crm.models import Company, FollowUpTask, LeadInteraction  # noqa: E402
from app.modules.crm.service import _log_touch_workflow  # noqa: E402


def run() -> None:
    async def main() -> None:
        await create_db_schema()
        async with async_session_factory() as session:
            await reset_database(session, mode="crm_only", keep_users=True, clear_debug_files=False)

            company = Company(name="Клиника Улыбка", city="Москва", status="active_new")
            session.add(company)
            await session.commit()
            await session.refresh(company)

            task = await _log_touch_workflow(
                session,
                company.id,
                result="contact_made",
                comment="Договорились о встрече",
                next_due_at=datetime(2026, 5, 25, 12, 0),
                user_id=None,
            )
            assert task is not None
            assert task.company_id == company.id
            assert task.status == "open"
            assert task.title == "Следующее касание (7-touch workflow)"

            interactions = (await session.execute(LeadInteraction.__table__.select().where(LeadInteraction.company_id == company.id))).fetchall()
            assert len(interactions) == 1
            assert "Дозвонился / есть контакт" in interactions[0].summary

            print("smoke_touch_workflow ok")

    import asyncio
    asyncio.run(main())


if __name__ == "__main__":
    run()