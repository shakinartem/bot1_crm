from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_website_denylist_quality_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("SEARCH_PROVIDER", "mock")

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.crm.schemas import CompanyCreate  # noqa: E402
from app.modules.crm.service import create_company  # noqa: E402
from app.modules.research.website_resolver import is_denied_website_url, run_website_search_for_company  # noqa: E402


async def main() -> None:
    smoke_db = ROOT / "app_website_denylist_quality_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()

    denied_urls = [
        "https://chrome.google.com/webstore/detail/test",
        "https://chromewebstore.google.com/detail/test",
        "https://google.com/chrome",
        "https://google.com/webstore",
        "https://yandex.ru/maps/org/test",
        "https://yandex.com/maps/org/test",
        "https://2gis.ru/saratov",
        "https://checko.ru/company/test",
        "https://vk.com/test",
        "https://t.me/test",
    ]
    for url in denied_urls:
        assert is_denied_website_url(url), url

    async with async_session_factory() as session:
        company = await create_company(
            session,
            CompanyCreate(
                name="Дентал Браво",
                legal_name='ООО "Дентал Браво"',
                inn="7701234567",
                city="Саратов",
                phone="+79991234567",
            ),
        )
        outcome = await run_website_search_for_company(session, company.id, force=True)
        assert all(not is_denied_website_url(url) for url in outcome.candidate_urls)
    print("smoke_website_denylist_quality ok")


if __name__ == "__main__":
    asyncio.run(main())
