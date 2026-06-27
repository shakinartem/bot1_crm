from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_telegram_company_card_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.crm.schemas import CompanyCreate  # noqa: E402
from app.modules.crm.service import create_company, format_company_card  # noqa: E402
from app.modules.crm.telegram_ux import render_maps_research_result  # noqa: E402
from app.modules.research.schemas import MapsScore  # noqa: E402


async def main() -> None:
    smoke_db = ROOT / "app_telegram_company_card_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()

    async with async_session_factory() as session:
        company = await create_company(
            session,
            CompanyCreate(
                name="Telegram Card Clinic",
                city="Саратов",
                phone="+79991234567",
                website="https://telegram-card.example",
                checko_profile_url="https://checko.ru/company/telegram-card-clinic-1234567890123/",
                maps_url="https://yandex.ru/maps/org/test",
            ),
        )
        card = format_company_card(company)
        assert "Checko:" in card
        assert "Карты:" in card
        assert "Сайт компании:" in card
        maps_text = render_maps_research_result(
            MapsScore(
                total_score=82,
                status="verified",
                yandex_maps_url="https://yandex.ru/maps/org/test",
                matched_fields=["name", "address"],
                reasons=["Сигналы совпали"],
                warnings=[],
            ),
            company,
        )
        assert "Maps research" in maps_text
        assert "verified" in maps_text
    print("smoke_telegram_company_card ok")


if __name__ == "__main__":
    asyncio.run(main())
