from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_discovery_cursor_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("AI_PROVIDER", "fallback")
os.environ.setdefault("LEGAL_DISCOVERY_PROVIDER", "mock")

from sqlalchemy import select  # noqa: E402

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.legal_discovery.models import LegalDiscoveryCursor  # noqa: E402
from app.modules.legal_discovery.service import reset_discovery_cursor, run_legal_discovery_preview  # noqa: E402


async def main() -> None:
    smoke_db = ROOT / "app_discovery_cursor_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()

    async with async_session_factory() as session:
        preview1 = await run_legal_discovery_preview(
            session,
            query="стоматология",
            okved_code="86.23",
            limit=10,
            page=1,
            provider_code="mock",
        )
        assert preview1.current_page == 1
        assert preview1.next_page == 2
        assert preview1.query_hash

        cursor = await session.scalar(
            select(LegalDiscoveryCursor).where(
                LegalDiscoveryCursor.provider == preview1.provider,
                LegalDiscoveryCursor.okved_code == (preview1.okved_code or "manual"),
                LegalDiscoveryCursor.query_hash == preview1.query_hash,
            )
        )
        assert cursor is not None
        assert cursor.current_page == 1
        assert cursor.previewed_count >= preview1.total_found
        assert cursor.imported_count == 0

        preview2 = await run_legal_discovery_preview(
            session,
            query="стоматология",
            okved_code="86.23",
            limit=10,
            page=2,
            provider_code="mock",
        )
        assert preview2.current_page == 2
        cursor = await session.scalar(
            select(LegalDiscoveryCursor).where(
                LegalDiscoveryCursor.provider == preview2.provider,
                LegalDiscoveryCursor.okved_code == (preview2.okved_code or "manual"),
                LegalDiscoveryCursor.query_hash == preview2.query_hash,
            )
        )
        assert cursor is not None
        assert cursor.current_page == 2
        assert cursor.previewed_count >= preview1.total_found + preview2.total_found

        reset_cursor = await reset_discovery_cursor(
            session,
            provider=preview2.provider,
            okved_code=preview2.okved_code or "manual",
            query_hash=preview2.query_hash or "",
        )
        assert reset_cursor is not None
        assert reset_cursor.current_page == 1
        assert reset_cursor.previewed_count == 0
        assert reset_cursor.imported_count == 0

    print("smoke_discovery_cursor ok")


if __name__ == "__main__":
    asyncio.run(main())
