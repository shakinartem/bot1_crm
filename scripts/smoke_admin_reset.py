from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_admin_reset_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "secret")
os.environ.setdefault("ALLOW_DB_RESET", "true")

from sqlalchemy import select  # noqa: E402

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.admin_reset.service import reset_database  # noqa: E402
from app.modules.crm.models import Company  # noqa: E402
from app.modules.crm.schemas import CompanyCreate  # noqa: E402
from app.modules.crm.service import create_company  # noqa: E402


async def main() -> None:
    smoke_db = ROOT / "app_admin_reset_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()
    async with async_session_factory() as session:
        await create_company(session, CompanyCreate(name="Reset Clinic"))
        before = await session.execute(select(Company))
        assert len(before.scalars().all()) == 1
        result = await reset_database(session, full_reset=False)
        assert result["companies"] == 1
        after = await session.execute(select(Company))
        assert len(after.scalars().all()) == 0
    print("smoke_admin_reset ok")


if __name__ == "__main__":
    asyncio.run(main())
