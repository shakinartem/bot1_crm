from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_website_resolver_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("SEARCH_PROVIDER", "mock")

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.crm.models import Company  # noqa: E402
from app.modules.crm.schemas import CompanyCreate  # noqa: E402
from app.modules.crm.service import create_company  # noqa: E402
from app.modules.research.website_resolver import (  # noqa: E402
    _build_queries,
    is_denied_website_url,
    normalize_website_url,
    run_website_search_for_company,
)


async def main() -> None:
    smoke_db = ROOT / "app_website_resolver_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()

    # Check denylist
    assert is_denied_website_url("https://rmsp-pp.nalog.ru/search")
    assert is_denied_website_url("https://yandex.ru/maps/org/test")
    assert not is_denied_website_url("https://clinic-example.ru")
    assert normalize_website_url("clinic-example.ru/") == "https://clinic-example.ru"

    # Check new query strategy: first query = INN + short_name + "сайт"
    company_with_inn = Company(
        name="Тестовая Клиника",
        legal_name='ООО "Тестовая Клиника"',
        inn="6451001234",
        city="Саратов",
        phone="+79991234567",
        address="ул. Московская, д. 1",
    )
    queries = _build_queries(company_with_inn)
    assert len(queries) > 0, f"Should have at least 1 query, got {queries}"
    first_query = queries[0]
    assert "6451001234" in first_query, f"First query should contain INN: {first_query}"
    assert "Тестовая" in first_query, f"First query should contain company name: {first_query}"
    assert "сайт" in first_query, f"First query should contain 'сайт': {first_query}"
    print(f"  ✅ First website query: {first_query}")

    # Check denied URL not saved
    assert is_denied_website_url("https://rmsp-pp.nalog.ru/search")

    async with async_session_factory() as session:
        company = await create_company(
            session,
            CompanyCreate(
                name="Clinic Example",
                legal_name='ООО "Clinic Example"',
                inn="6451001234",
                city="Саратов",
                phone="+79991234567",
            ),
        )
        outcome = await run_website_search_for_company(session, company.id, force=True)
        assert outcome.status in {"not_found", "partial", "resolved"}
        assert "https://rmsp-pp.nalog.ru/search" not in outcome.candidate_urls
        print("  ✅ Denied URL not in candidates")

    print("\nsmoke_website_resolver ok")


if __name__ == "__main__":
    asyncio.run(main())