from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_lead_fit_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.crm.schemas import CompanyCreate  # noqa: E402
from app.modules.crm.service import create_company  # noqa: E402
from app.modules.crm.telegram_ux import render_lead_fit_block  # noqa: E402
from app.modules.lead_fit.service import get_company_lead_fit, recalculate_company_lead_fit, summarize_lead_fit_groups  # noqa: E402


async def main() -> None:
    smoke_db = ROOT / "app_lead_fit_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()
    async with async_session_factory() as session:
        hot = await create_company(
            session,
            CompanyCreate(
                name="Hot Clinic",
                inn="6451001234",
                ogrn="1026402494799",
                phone="+79991234567",
                website="https://hot-clinic.test",
                city="Саратов",
                address="Саратов, ул. Тестовая, 1",
                reviews_count=7,
                maps_url="https://maps.yandex.ru/test",
                source="legal_discovery:checko_html",
            ),
        )
        cold = await create_company(session, CompanyCreate(name="Cold Clinic"))
        hot_score = await recalculate_company_lead_fit(session, hot.id)
        cold_score = await recalculate_company_lead_fit(session, cold.id)
        assert hot_score.group == "A_hot_priority"
        assert cold_score.group in {"D_low_priority", "excluded_do_not_contact"}
        latest = await get_company_lead_fit(session, hot.id)
        assert latest is not None and latest.total_score == hot_score.total_score
        rendered = render_lead_fit_block(latest)
        assert "Приоритет:" in rendered
        assert "Следующий шаг:" in rendered
        summary = await summarize_lead_fit_groups(session)
        assert summary.total == 2
    print("smoke_lead_fit ok")


if __name__ == "__main__":
    asyncio.run(main())
