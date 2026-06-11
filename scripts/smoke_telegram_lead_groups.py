from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_telegram_lead_groups_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.analytics.service import format_company_card_with_score  # noqa: E402
from app.modules.crm.schemas import CompanyCreate  # noqa: E402
from app.modules.crm.service import create_company, get_company  # noqa: E402
from app.modules.crm.telegram_ux import (  # noqa: E402
    TELEGRAM_TEXT_LIMIT,
    render_lead_group_companies,
    render_lead_groups_menu,
)
from app.modules.lead_fit.service import (  # noqa: E402
    get_company_lead_fit,
    list_companies_by_lead_fit_group,
    recalculate_all_companies_lead_fit,
    summarize_lead_fit_groups,
)


async def main() -> None:
    smoke_db = ROOT / "app_telegram_lead_groups_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()
    async with async_session_factory() as session:
        hot = await create_company(
            session,
            CompanyCreate(
                name="Hot Clinic",
                inn="6451001234",
                phone="+79991234567",
                website="https://hot-clinic.test",
                city="Saratov",
                region="Saratov Oblast",
                address="Test 1",
                reviews_count=6,
                maps_url="https://maps.test/hot",
                source="legal_discovery:checko_html",
            ),
        )
        await create_company(session, CompanyCreate(name="Cold Clinic"))
        await recalculate_all_companies_lead_fit(session)
        summary = await summarize_lead_fit_groups(session)
        menu_text = render_lead_groups_menu(summary)
        assert "Группы лидов" in menu_text
        assert "Горячие" in menu_text
        companies = await list_companies_by_lead_fit_group(session, "A_hot_priority")
        lead_fit_scores = {company.id: await get_company_lead_fit(session, company.id) for company in companies[:10]}
        group_text = render_lead_group_companies("A_hot_priority", companies, lead_fit_scores, page=0)
        assert len(group_text) <= TELEGRAM_TEXT_LIMIT
        assert "Причина:" in group_text
        refreshed_hot = await get_company_lead_fit(session, hot.id)
        company = await get_company(session, hot.id)
        assert company is not None
        card_text = format_company_card_with_score(company)
        assert refreshed_hot is not None
        assert "Приоритет:" in card_text
        assert "План 7 касаний" in card_text
    print("smoke_telegram_lead_groups ok")


if __name__ == "__main__":
    asyncio.run(main())
