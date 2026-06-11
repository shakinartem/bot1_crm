from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_company_delete_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.crm.schemas import CompanyCreate  # noqa: E402
from app.modules.crm.service import create_company, delete_company, list_companies  # noqa: E402
from app.modules.crm.telegram_ux import render_delete_confirmation  # noqa: E402


async def main() -> None:
    smoke_db = ROOT / "app_company_delete_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()
    async with async_session_factory() as session:
        company = await create_company(session, CompanyCreate(name="Delete Clinic"))
        confirmation = render_delete_confirmation(company)
        assert "скрыта" in confirmation.lower()
        assert len(await list_companies(session, limit=20)) == 1
        assert await delete_company(session, company.id)
        assert len(await list_companies(session, limit=20)) == 0
    print("smoke_company_delete ok")


if __name__ == "__main__":
    asyncio.run(main())
