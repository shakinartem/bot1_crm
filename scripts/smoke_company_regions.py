from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_company_regions_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.crm.constants import CompanyStatus, LeadPriority  # noqa: E402
from app.modules.crm.location_utils import extract_region_city_from_address  # noqa: E402
from app.modules.crm.models import Company  # noqa: E402
from app.modules.crm.service import get_company_cities, get_company_regions, list_companies_by_region_city  # noqa: E402


async def main() -> None:
    smoke_db = ROOT / "app_company_regions_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()

    assert extract_region_city_from_address("410015, Саратовская область, г. Саратов, ул. Радищева, 15") == {
        "region": "Саратовская область",
        "city": "Саратов",
    }
    assert extract_region_city_from_address("644010, Омская область, г. Омск, ул. Ленина, 3") == {
        "region": "Омская область",
        "city": "Омск",
    }
    assert extract_region_city_from_address("236005, Калининградская область, г. Калининград, ул. Минусинская, д. 22") == {
        "region": "Калининградская область",
        "city": "Калининград",
    }
    assert extract_region_city_from_address("121059, г. Москва, бул. Украинский, 6") == {
        "region": "Москва",
        "city": "Москва",
    }
    assert extract_region_city_from_address("191000, г. Санкт-Петербург, Невский проспект, 1") == {
        "region": "Санкт-Петербург",
        "city": "Санкт-Петербург",
    }

    async with async_session_factory() as session:
        session.add_all(
            [
                Company(
                    name="Практик",
                    legal_name='ООО "Практик"',
                    city="Саратов",
                    region="Саратовская область",
                    phone="+79990000001",
                    website="https://praktik.test",
                    status=CompanyStatus.RESEARCH_NEEDED.value,
                    priority=LeadPriority.MEDIUM.value,
                ),
                Company(
                    name="Улыбка",
                    legal_name='ООО "Улыбка"',
                    city="Саратов",
                    region="Саратовская область",
                    status=CompanyStatus.DEAL_LOST.value,
                    priority=LeadPriority.LOW.value,
                ),
                Company(
                    name="Омск Дент",
                    legal_name='ООО "Омск Дент"',
                    city="Омск",
                    region="Омская область",
                    phone="+79990000002",
                    status=CompanyStatus.INTERESTED.value,
                    priority=LeadPriority.HIGH.value,
                ),
                Company(
                    name="Имплантлаб",
                    legal_name='ООО "Имплантлаб"',
                    city="Москва",
                    region="Москва",
                    website="https://implant.test",
                    status=CompanyStatus.PREPARED.value,
                    priority=LeadPriority.MEDIUM.value,
                ),
            ]
        )
        await session.commit()

        regions = await get_company_regions(session)
        assert regions[0].region == "Саратовская область"
        assert regions[0].total == 2
        assert regions[0].active == 1

        cities = await get_company_cities(session, region="Саратовская область")
        assert len(cities) == 1
        assert cities[0].city == "Саратов"
        assert cities[0].total == 2

        companies = await list_companies_by_region_city(session, region="Саратовская область", city="Саратов", limit=20)
        assert len(companies) == 2

    print("smoke_company_regions ok")


if __name__ == "__main__":
    asyncio.run(main())
