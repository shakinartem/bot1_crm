from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_proposals_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")
os.environ.setdefault("AI_PROVIDER", "fallback")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import async_session_factory  # noqa: E402
from app.database import create_db_schema  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.crm.constants import InteractionType  # noqa: E402
from app.modules.crm.schemas import CompanyCreate, InteractionCreate  # noqa: E402
from app.modules.crm.service import add_interaction, create_company  # noqa: E402
from app.modules.proposals.service import (  # noqa: E402
    generate_commercial_proposal,
    generate_contract_draft,
    generate_service_appendix,
    list_company_proposal_drafts,
    suggest_packages_for_company,
)


async def seed_company() -> int:
    async with async_session_factory() as session:
        company = await create_company(
            session,
            CompanyCreate(
                name="Стоматология Smoke Proposals",
                city="Саратов",
                notes="Нужны соцсети, карты и CRM. Заявки теряются, администратор не фиксирует обращения.",
                status="interested",
                priority="high",
            ),
        )
        await add_interaction(
            session,
            InteractionCreate(
                company_id=company.id,
                type=InteractionType.NOTE,
                summary="Клиника интересуется соцсетями, контентом и отзывами на картах.",
                created_by="smoke",
            ),
        )
        await add_interaction(
            session,
            InteractionCreate(
                company_id=company.id,
                type=InteractionType.CONSULTATION,
                summary="После консультации попросили подготовить КП и структуру договора.",
                created_by="smoke",
            ),
        )
        return company.id


async def verify_services(company_id: int) -> None:
    async with async_session_factory() as session:
        suggestions = await suggest_packages_for_company(session, company_id)
        assert suggestions, "package suggestions must not be empty"

        proposal = await generate_commercial_proposal(session, company_id, use_ai=False)
        assert proposal.content.startswith("# Коммерческое предложение"), "proposal must be generated"
        assert proposal.file_path.exists(), "proposal file must exist"

        contract = await generate_contract_draft(session, company_id)
        assert contract.content.startswith("# Черновик структуры договора"), "contract draft must be generated"
        assert contract.file_path.exists(), "contract file must exist"

        appendix = await generate_service_appendix(session, company_id)
        assert appendix.content.startswith("# Приложение: состав услуг"), "service appendix must be generated"
        assert appendix.file_path.exists(), "appendix file must exist"

        history = await list_company_proposal_drafts(session, company_id)
        assert len(history) >= 3, "proposal history must contain generated drafts"


async def run_async_checks() -> int:
    smoke_db = ROOT / "app_proposals_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()

    await create_db_schema()
    company_id = await seed_company()
    await verify_services(company_id)
    return company_id


def verify_api(company_id: int) -> None:
    with TestClient(app) as client:
        packages = client.get("/api/proposals/packages")
        assert packages.status_code == 200, "packages endpoint must work"

        suggest = client.post(f"/api/companies/{company_id}/proposals/suggest-packages")
        assert suggest.status_code == 200, "suggest packages endpoint must work"

        proposal = client.post(
            f"/api/companies/{company_id}/proposals/generate",
            json={"selected_package_codes": ["audit_roadmap", "smm_funnel"], "use_ai": False},
        )
        assert proposal.status_code == 200, "generate proposal endpoint must work"

        contract = client.post(
            f"/api/companies/{company_id}/contracts/draft",
            json={"selected_package_codes": ["audit_roadmap"]},
        )
        assert contract.status_code == 200, "contract draft endpoint must work"

        appendix = client.post(
            f"/api/companies/{company_id}/contracts/service-appendix",
            json={"selected_package_codes": ["audit_roadmap"]},
        )
        assert appendix.status_code == 200, "service appendix endpoint must work"

        history = client.get(f"/api/companies/{company_id}/proposals/history")
        assert history.status_code == 200, "proposal history endpoint must work"
        items = history.json()
        assert items, "proposal history must not be empty"

        file_response = client.get(f"/api/companies/{company_id}/proposals/{items[0]['id']}/file")
        assert file_response.status_code == 200, "proposal file endpoint must work"


async def main() -> None:
    company_id = await run_async_checks()
    verify_api(company_id)
    print("smoke_proposals ok")


if __name__ == "__main__":
    asyncio.run(main())
