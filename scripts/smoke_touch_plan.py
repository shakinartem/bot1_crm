from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_touch_plan_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.crm.schemas import CompanyCreate  # noqa: E402
from app.modules.crm.service import create_company  # noqa: E402
from app.modules.crm.telegram_ux import render_touch_plan_block  # noqa: E402
from app.modules.crm.touch_service import create_touch_plan_for_company, get_touch_plan_for_company  # noqa: E402


async def main() -> None:
    smoke_db = ROOT / "app_touch_plan_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()
    async with async_session_factory() as session:
        company = await create_company(session, CompanyCreate(name="Touch Clinic"))
        tasks = await create_touch_plan_for_company(session, company.id)
        assert len(tasks) == 7
        assert tasks[0].interaction_stage == "touch_1_first_contact"
        second_read = await get_touch_plan_for_company(session, company.id)
        assert len(second_read) == 7
        rendered = render_touch_plan_block(second_read)
        assert "План 7 касаний" in rendered
        assert "Текущее касание" in rendered
    print("smoke_touch_plan ok")


if __name__ == "__main__":
    asyncio.run(main())
