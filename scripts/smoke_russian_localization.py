from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_russian_localization_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")
os.environ.setdefault("AI_PROVIDER", "fallback")
os.environ.setdefault("LEGAL_PROVIDER", "mock")
os.environ.setdefault("SEARCH_PROVIDER", "mock")

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.crm.keyboards import main_menu  # noqa: E402
from app.modules.proposals.service import suggest_packages_for_company  # noqa: E402
from app.modules.sales_intelligence.service import (  # noqa: E402
    build_closing_criteria_readiness,
    calculate_company_material_score,
    generate_cold_call_plan,
    generate_soprano_questions,
)
from scripts.smoke_call_plan import seed_company_context  # noqa: E402


CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def assert_has_russian(text: str, label: str) -> None:
    assert text.strip(), f"{label} must not be empty"
    assert CYRILLIC_RE.search(text), f"{label} must contain Russian text: {text!r}"


async def verify_localization(company_id: int) -> None:
    async with async_session_factory() as session:
        score = await calculate_company_material_score(session, company_id)
        assert score.reasons, "material score reasons must not be empty"
        assert score.risks, "material score risks must not be empty"
        for index, item in enumerate(score.reasons[:3], start=1):
            assert_has_russian(item, f"material score reason #{index}")
        for index, item in enumerate(score.risks[:3], start=1):
            assert_has_russian(item, f"material score risk #{index}")
        for index, item in enumerate(score.opportunities[:3], start=1):
            assert_has_russian(item, f"material score opportunity #{index}")
        for index, item in enumerate(score.next_improvements[:3], start=1):
            assert_has_russian(item, f"material score next improvement #{index}")

        closing = await build_closing_criteria_readiness(session, company_id)
        assert_has_russian(closing.summary, "closing summary")
        assert_has_russian(closing.next_best_question, "closing next best question")
        for index, item in enumerate(closing.risks[:3], start=1):
            assert_has_russian(item, f"closing risk #{index}")
        for label, criterion in {
            "financial_opportunity": closing.financial_opportunity,
            "conscious_need": closing.conscious_need,
            "trust": closing.trust,
            "decision_maker": closing.decision_maker,
            "here_and_now": closing.here_and_now,
        }.items():
            for index, item in enumerate(criterion.evidence[:2], start=1):
                assert_has_russian(item, f"{label} evidence #{index}")
            for index, item in enumerate(criterion.questions[:2], start=1):
                assert_has_russian(item, f"{label} question #{index}")

        soprano = await generate_soprano_questions(session, company_id)
        assert_has_russian(soprano.intro, "soprano intro")
        for section_name in ("situation", "experience", "principles", "solutions", "analogies", "undesired", "limitations"):
            items = getattr(soprano, section_name)
            assert items, f"{section_name} must not be empty"
            for index, item in enumerate(items[:2], start=1):
                assert_has_russian(item, f"{section_name} question #{index}")

        plan = await generate_cold_call_plan(session, company_id, use_ai=False)
        assert_has_russian(plan.call_goal, "call goal")
        assert_has_russian(plan.opener, "opener")
        assert_has_russian(plan.reason_for_call, "reason for call")
        assert_has_russian(plan.first_offer, "first offer")
        assert_has_russian(plan.next_best_action, "next best action")
        assert_has_russian(plan.copyable_short_script, "copyable short script")
        for index, item in enumerate(plan.manager_checklist[:3], start=1):
            assert_has_russian(item, f"manager checklist #{index}")
        for index, item in enumerate(plan.do_not_say[:3], start=1):
            assert_has_russian(item, f"do_not_say #{index}")
        for index, item in enumerate(plan.objection_preparation[:2], start=1):
            assert_has_russian(item.objection, f"objection #{index}")
            assert_has_russian(item.response_principle, f"response principle #{index}")
            assert_has_russian(item.suggested_response, f"suggested response #{index}")

        suggestions = await suggest_packages_for_company(session, company_id)
        assert suggestions, "package suggestions must not be empty"
        for index, item in enumerate(suggestions[:4], start=1):
            assert_has_russian(item.title, f"package title #{index}")
            assert_has_russian(item.reason, f"package reason #{index}")

    button_texts = [button.text for row in main_menu().keyboard for button in row]
    for expected in (
        "🔍 Поиск и импорт",
        "🏢 CRM / Компании",
        "👤 Мои лиды",
        "📞 Продажи",
        "📄 КП и документы",
        "🧠 AI / Research",
        "📊 Аналитика",
        "⚙️ Настройки",
        "🔍 Поиск компаний",
    ):
        assert expected in button_texts, f"main menu must include {expected!r}"


async def main() -> None:
    smoke_db = ROOT / "app_russian_localization_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()

    await create_db_schema()
    company_id = await seed_company_context()
    await verify_localization(company_id)
    print("smoke_russian_localization ok")


if __name__ == "__main__":
    asyncio.run(main())
