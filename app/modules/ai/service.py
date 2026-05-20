from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.prompts import build_cold_call_prompt
from app.modules.ai.providers import get_ai_provider
from app.modules.crm.service import get_company


async def prepare_cold_call(session: AsyncSession, company_id: int) -> str | None:
    company = await get_company(session, company_id)
    if not company:
        return None
    prompt = build_cold_call_prompt(company)
    return await get_ai_provider().generate(prompt)
