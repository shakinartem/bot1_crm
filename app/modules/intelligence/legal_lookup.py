from __future__ import annotations

from app.modules.intelligence.providers import get_legal_provider
from app.modules.intelligence.schemas import LegalCompany


async def find_legal_by_inn(inn: str) -> LegalCompany | None:
    return await get_legal_provider().find_by_inn(inn)


async def search_legal_by_name(
    name: str,
    city: str | None = None,
    region: str | None = None,
    limit: int = 10,
) -> list[LegalCompany]:
    return await get_legal_provider().search_by_name(name=name, city=city, region=region, limit=limit)
