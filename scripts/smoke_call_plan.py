from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_call_plan_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")
os.environ.setdefault("AI_PROVIDER", "fallback")
os.environ.setdefault("LEGAL_PROVIDER", "mock")
os.environ.setdefault("SEARCH_PROVIDER", "mock")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.crm.models import ContactPoint, DecisionMaker, FollowUpTask, LeadInteraction  # noqa: E402
from app.modules.crm.schemas import CompanyCreate  # noqa: E402
from app.modules.crm.service import create_company  # noqa: E402
from app.modules.enrichment.models import EnrichmentSnapshot  # noqa: E402
from app.modules.enrichment.schemas import dump_json_text  # noqa: E402
from app.modules.intelligence.models import IntelligenceSnapshot  # noqa: E402
from app.modules.research_queue.models import ResearchJob  # noqa: E402
from app.modules.sales_intelligence.service import (  # noqa: E402
    build_closing_criteria_readiness,
    generate_cold_call_plan,
    generate_soprano_questions,
    get_company_sales_context,
    get_latest_sales_intelligence,
)


async def seed_company_context() -> int:
    async with async_session_factory() as session:
        company = await create_company(
            session,
            CompanyCreate(
                name="Dental Bravo",
                legal_name='OOO "Dental Bravo"',
                inn="7701234567",
                ogrn="1027700000001",
                city="Saratov",
                region="Saratov Oblast",
                address="15 Radishcheva St, Saratov",
                phone="+7 999 000-11-22",
                website="https://dental-bravo.example",
                maps_url="https://yandex.ru/maps/org/dental_bravo",
                vk_url="https://vk.com/dentalbravo",
                telegram_url="https://t.me/dentalbravo",
                rating=4.6,
                reviews_count=87,
                source="cold_base",
                status="consultation_planned",
                priority="high",
                notes="Manager suspects the clinic loses demand after the first inquiry.",
            ),
        )
        session.add_all(
            [
                DecisionMaker(
                    company_id=company.id,
                    full_name="Anna Petrov",
                    role="Owner",
                    phone="+7 999 000-11-22",
                    email="owner@dental-bravo.example",
                    is_primary=True,
                    notes="Handles marketing budget personally.",
                ),
                ContactPoint(
                    company_id=company.id,
                    type="phone",
                    value="+7 999 000-11-22",
                    label="front desk",
                    is_primary=True,
                ),
                ContactPoint(
                    company_id=company.id,
                    type="email",
                    value="info@dental-bravo.example",
                    label="website",
                    is_primary=False,
                ),
                ContactPoint(
                    company_id=company.id,
                    type="telegram",
                    value="https://t.me/dentalbravo",
                    label="social",
                    is_primary=False,
                ),
                LeadInteraction(
                    company_id=company.id,
                    type="call",
                    result="interested",
                    summary="Reception said demand is uneven and the owner reviews marketing weekly.",
                    next_action="Prepare a practical diagnostic call with the owner.",
                    created_by="smoke",
                ),
                LeadInteraction(
                    company_id=company.id,
                    type="note",
                    summary="Website has online booking, reviews, and implant pages but no obvious offer.",
                    created_by="smoke",
                ),
                FollowUpTask(
                    company_id=company.id,
                    title="Call owner with diagnostic agenda",
                    description="Confirm where new-patient leads come from and what happens after first contact.",
                    status="open",
                    priority="high",
                ),
                EnrichmentSnapshot(
                    company_id=company.id,
                    website_url="https://dental-bravo.example",
                    status="success",
                    page_title="Dental Bravo | Implant and family dentistry",
                    meta_description="Dental clinic with online booking, doctors, reviews, and WhatsApp contact.",
                    detected_socials_json=dump_json_text(
                        {
                            "vk": ["https://vk.com/dentalbravo"],
                            "telegram": ["https://t.me/dentalbravo"],
                        }
                    ),
                    detected_maps_json=dump_json_text(
                        {
                            "yandex_maps": ["https://yandex.ru/maps/org/dental_bravo"],
                        }
                    ),
                    detected_contacts_json=dump_json_text(
                        {
                            "phones": ["+7 999 000-11-22"],
                            "emails": ["info@dental-bravo.example"],
                            "whatsapp_links": ["https://wa.me/79990001122"],
                            "telegram_links": ["https://t.me/dentalbravo"],
                        }
                    ),
                    signals_json=dump_json_text(
                        {
                            "has_online_booking": True,
                            "has_callback_form": True,
                            "has_prices": True,
                            "has_doctors_page": True,
                            "has_reviews_section": True,
                            "has_contacts_page": True,
                            "has_social_links": True,
                            "has_messenger_links": True,
                            "has_privacy_policy": True,
                            "has_promotions": False,
                            "has_implantation_keywords": True,
                            "has_orthodontics_keywords": True,
                            "has_children_dentistry_keywords": True,
                            "has_emergency_keywords": False,
                        }
                    ),
                    hypotheses_json=dump_json_text(
                        [
                            "The site likely does a decent job explaining services but may not make the next step prominent enough.",
                            "Visible doctors and reviews suggest trust is partly established before the first call.",
                        ]
                    ),
                    ai_summary="The clinic looks credible online, but the conversion path may still need work.",
                    raw_text_excerpt="Implants, orthodontics, pediatric care, online booking, reviews, and messenger contacts.",
                ),
                IntelligenceSnapshot(
                    company_id=company.id,
                    status="success",
                    inn="7701234567",
                    legal_name='OOO "Dental Bravo"',
                    ogrn="1027700000001",
                    legal_address="15 Radishcheva St, Saratov",
                    legal_status="active",
                    okved="86.23",
                    website_url="https://dental-bravo.example",
                    website_confidence=88,
                    website_candidates_json=dump_json_text([]),
                    parsed_contacts_json=dump_json_text(
                        {
                            "phones": ["+7 999 000-11-22"],
                            "emails": ["info@dental-bravo.example"],
                            "addresses": ["15 Radishcheva St, Saratov"],
                            "whatsapp_links": ["https://wa.me/79990001122"],
                            "telegram_links": ["https://t.me/dentalbravo"],
                        }
                    ),
                    parsed_socials_json=dump_json_text(
                        {
                            "vk_links": ["https://vk.com/dentalbravo"],
                            "telegram_links": ["https://t.me/dentalbravo"],
                            "whatsapp_links": ["https://wa.me/79990001122"],
                            "yandex_maps_links": ["https://yandex.ru/maps/org/dental_bravo"],
                        }
                    ),
                    parsed_signals_json=dump_json_text(
                        {
                            "has_online_booking": True,
                            "has_callback_form": True,
                            "has_prices": True,
                            "has_doctors_page": True,
                            "has_reviews_section": True,
                            "has_contacts_page": True,
                            "has_social_links": True,
                            "has_messenger_links": True,
                            "has_privacy_policy": True,
                            "has_promotions": False,
                            "has_implantation_keywords": True,
                            "has_orthodontics_keywords": True,
                            "has_children_dentistry_keywords": True,
                            "has_emergency_keywords": False,
                        }
                    ),
                    hypotheses_json=dump_json_text(
                        [
                            "The clinic appears to have solid service breadth for elective dentistry.",
                            "Maps and messenger coverage suggest there may already be meaningful top-of-funnel demand.",
                        ]
                    ),
                    ai_summary="Public signals suggest a real clinic with enough digital footprint to justify a diagnostic sales call.",
                    raw_references_json=dump_json_text([]),
                ),
                ResearchJob(
                    company_id=company.id,
                    job_type="company_research",
                    status="done",
                    priority="high",
                    attempts=1,
                    max_attempts=3,
                    result_json=dump_json_text(
                        {
                            "summary": "Research found strong digital proof points but no explicit first-offer CTA.",
                            "key_findings": [
                                "High review volume on maps",
                                "Online booking exists",
                                "No explicit landing-page style offer detected",
                            ],
                        }
                    ),
                ),
            ]
        )
        await session.commit()
        return company.id


async def verify_sales_intelligence(company_id: int) -> None:
    async with async_session_factory() as session:
        context = await get_company_sales_context(session, company_id)
        assert context["company"]["name"] == "Dental Bravo"
        assert context["decision_makers"], "decision makers must be included"
        assert context["recent_interactions"], "recent interactions must be included"
        assert context["open_tasks"], "open tasks must be included"

        closing = await build_closing_criteria_readiness(session, company_id)
        assert closing.next_best_question, "next best question must be generated"
        assert closing.financial_opportunity.status in {"unknown", "weak", "possible", "strong"}

        soprano = await generate_soprano_questions(session, company_id)
        assert soprano.intro, "intro must be generated"
        assert soprano.recommended_order, "recommended order must be present"

        plan = await generate_cold_call_plan(session, company_id, use_ai=True)
        assert plan.generation_mode == "fallback", "fallback mode is expected in smoke"
        assert plan.copyable_short_script, "copyable short script must exist"
        assert len(plan.copyable_short_script) <= 1000, "manager script must stay concise"

        latest = await get_latest_sales_intelligence(session, company_id)
        assert latest.saved_at is None, "Task 3 should not persist snapshots"
        assert latest.cold_call_plan is None, "latest read should assemble on demand only for now"
        assert latest.closing_criteria.next_best_question

    with TestClient(app) as client:
        material_response = client.get(f"/api/companies/{company_id}/sales-intelligence/material-score")
        assert material_response.status_code == 200
        assert material_response.json()["company_id"] == company_id

        closing_response = client.get(f"/api/companies/{company_id}/sales-intelligence/closing-criteria")
        assert closing_response.status_code == 200
        assert closing_response.json()["next_best_question"]

        soprano_response = client.get(f"/api/companies/{company_id}/sales-intelligence/soprano-questions")
        assert soprano_response.status_code == 200
        assert soprano_response.json()["recommended_order"]

        plan_response = client.post(
            f"/api/companies/{company_id}/sales-intelligence/cold-call-plan",
            json={"use_ai": True},
        )
        assert plan_response.status_code == 200
        assert plan_response.json()["generation_mode"] == "fallback"

        latest_response = client.get(f"/api/companies/{company_id}/sales-intelligence/latest")
        assert latest_response.status_code == 200
        latest_payload = latest_response.json()
        assert latest_payload["material_score"]["total_score"] >= 0
        assert latest_payload["saved_at"] is None
        assert latest_payload["cold_call_plan"] is None

        bot2_response = client.get(f"/api/bot2/companies/{company_id}/consultation-context")
        assert bot2_response.status_code == 200
        sales_intelligence = bot2_response.json()["sales_intelligence"]
        assert sales_intelligence["material_score"]["total_score"] >= 0
        assert sales_intelligence["closing_criteria"]["next_best_question"]
        assert sales_intelligence["cold_call_plan_summary"]
        assert sales_intelligence["generation_mode"] == "fallback"


async def main() -> None:
    smoke_db = ROOT / "app_call_plan_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()

    await create_db_schema()
    company_id = await seed_company_context()
    await verify_sales_intelligence(company_id)
    print("smoke_call_plan ok")


if __name__ == "__main__":
    asyncio.run(main())
