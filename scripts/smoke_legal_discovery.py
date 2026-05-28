from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_legal_discovery_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")
os.environ.setdefault("AI_PROVIDER", "fallback")
os.environ.setdefault("LEGAL_DISCOVERY_PROVIDER", "mock")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.legal_discovery.service import import_legal_discovery_preview, run_legal_discovery_preview  # noqa: E402


async def verify_service() -> str:
    async with async_session_factory() as session:
        preview = await run_legal_discovery_preview(
            session,
            query="стоматология",
            city="Саратов",
            limit=25,
            provider_code="mock",
        )
        assert preview.total_found == 25, "mock preview must return 25 items"
        assert preview.active_count >= 1, "preview must count active companies"
        assert preview.new_count >= 1, "preview must include new companies"
        first_import = await import_legal_discovery_preview(session, preview.preview_id, "active_new")
        assert first_import.added_count >= 1, "import must add companies"
        second_import = await import_legal_discovery_preview(session, preview.preview_id, "active_new")
        assert second_import.added_count == 0, "repeated import must not create duplicates"
        return preview.preview_id


def verify_api() -> None:
    with TestClient(app) as client:
        preview = client.post(
            "/api/legal-discovery/search",
            json={
                "query": "стоматология",
                "city": "Саратов",
                "limit": 10,
                "provider": "mock",
            },
        )
        assert preview.status_code == 200, "search endpoint must work"
        preview_payload = preview.json()
        assert preview_payload["total_found"] == 10, "API preview must honor limit"

        imported = client.post(
            "/api/legal-discovery/import",
            json={"preview_id": preview_payload["preview_id"], "mode": "active_new"},
        )
        assert imported.status_code == 200, "import endpoint must work"


async def main() -> None:
    smoke_db = ROOT / "app_legal_discovery_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()
    await verify_service()
    verify_api()
    print("smoke_legal_discovery ok")


if __name__ == "__main__":
    asyncio.run(main())
