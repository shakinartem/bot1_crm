from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.ai.prompts import (
    build_cold_call_prompt,
    build_daily_digest_recommendation_prompt,
    build_fallback_mini_audit,
    build_mini_audit_prompt,
)
from app.modules.ai.providers import get_ai_provider
from app.modules.crm.service import get_company, get_company_last_interactions, humanize_company_status
from app.modules.enrichment.service import build_enrichment_context_for_company
from app.modules.intelligence.service import build_intelligence_context_for_company


async def prepare_cold_call(session: AsyncSession, company_id: int) -> str | None:
    company = await get_company(session, company_id)
    if not company:
        return None
    enrichment = await build_enrichment_context_for_company(session, company_id)
    intelligence = await build_intelligence_context_for_company(session, company_id)
    prompt = build_cold_call_prompt(company, enrichment, intelligence)
    return await get_ai_provider().generate(prompt)


async def generate_mini_audit(session: AsyncSession, company_id: int) -> str | None:
    company = await get_company(session, company_id)
    if not company:
        return None

    interactions = await get_company_last_interactions(session, company_id, limit=5)
    company_context = {
        "name": company.name,
        "city": company.city,
        "website": company.website,
        "status": company.status,
        "status_label": humanize_company_status(company.status),
        "source": company.source,
        "notes": company.notes,
        "recent_interactions": "\n".join(
            f"- {item.created_at:%Y-%m-%d}: {item.summary or 'без комментария'}"
            for item in interactions
        )
        or "нет данных",
    }

    if get_settings().ai_provider.lower() == "fallback":
        return build_fallback_mini_audit(company_context)

    prompt = build_mini_audit_prompt(company_context)
    try:
        return await get_ai_provider().generate(prompt)
    except Exception:
        return build_fallback_mini_audit(company_context)


async def generate_daily_recommendation(summary: dict) -> str | None:
    if get_settings().ai_provider.lower() == "fallback":
        return None

    prompt = build_daily_digest_recommendation_prompt(summary)
    try:
        return await get_ai_provider().generate(prompt)
    except Exception:
        return None
