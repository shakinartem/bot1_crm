from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_reset_clean_import_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("ALLOW_DB_RESET", "true")
os.environ.setdefault("AI_PROVIDER", "fallback")
os.environ.setdefault("LEGAL_DISCOVERY_PROVIDER", "mock")
os.environ.setdefault("STORAGE_PATH", "./storage")

from sqlalchemy import select  # noqa: E402

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.admin_reset.service import reset_database  # noqa: E402
from app.modules.crm.models import Company  # noqa: E402
from app.modules.legal_discovery.models import LegalDiscoveryCursor  # noqa: E402
from app.modules.legal_discovery.service import import_legal_discovery_preview, run_legal_discovery_preview  # noqa: E402


async def main() -> None:
    smoke_db = ROOT / "app_reset_clean_import_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()

    debug_file = ROOT / "storage" / "debug" / "checko" / "smoke-reset-clean-import.txt"
    debug_file.parent.mkdir(parents=True, exist_ok=True)
    debug_file.write_text("temporary debug data", encoding="utf-8")

    async with async_session_factory() as session:
        preview = await run_legal_discovery_preview(
            session,
            query="стоматология",
            okved_code="86.23",
            limit=10,
            page=1,
            provider_code="mock",
        )
        first_import = await import_legal_discovery_preview(session, preview.preview_id, "active_new")
        assert first_import.added_count == preview.new_count
        assert first_import.skipped_duplicates == preview.duplicate_count

        reset_result = await reset_database(session, mode="all_data", keep_users=True, clear_debug_files=True)
        assert reset_result["mode"] == "all_data"
        assert reset_result["debug_files_deleted"] >= 1

        company_count = await session.scalar(select(Company))
        cursor_count = await session.scalar(select(LegalDiscoveryCursor))
        assert company_count is None
        assert cursor_count is None

        assert not debug_file.exists()

        preview_after = await run_legal_discovery_preview(
            session,
            query="стоматология",
            okved_code="86.23",
            limit=10,
            page=1,
            provider_code="mock",
        )
        assert preview_after.new_count == preview_after.total_found
        assert preview_after.duplicate_count == 0

    print("smoke_reset_clean_import ok")


if __name__ == "__main__":
    asyncio.run(main())
