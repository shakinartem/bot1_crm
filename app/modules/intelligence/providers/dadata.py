from __future__ import annotations

import httpx

from app.config import get_settings
from app.modules.intelligence.providers.base import LegalLookupProvider
from app.modules.intelligence.schemas import LegalCompany


class DaDataLegalProvider(LegalLookupProvider):
    code = "dadata"
    title = "DaData"

    def __init__(self) -> None:
        settings = get_settings()
        self._token = settings.dadata_token
        self._secret = settings.dadata_secret
        self.enabled = bool(self._token)

    async def find_by_inn(self, inn: str) -> LegalCompany | None:
        if not self.enabled:
            return None
        items = await self._query("party", inn)
        return _to_company(items[0], self.code) if items else None

    async def search_by_name(
        self,
        name: str,
        city: str | None = None,
        region: str | None = None,
        limit: int = 10,
    ) -> list[LegalCompany]:
        if not self.enabled:
            return []
        query = " ".join(part for part in (name, city, region) if part)
        items = await self._query("party", query, count=limit)
        return [_to_company(item, self.code) for item in items if _to_company(item, self.code)]

    async def _query(self, endpoint: str, query: str, count: int = 10) -> list[dict]:
        headers = {"Authorization": f"Token {self._token}"}
        if self._secret:
            headers["X-Secret"] = self._secret
        payload = {"query": query, "count": count}
        try:
            async with httpx.AsyncClient(timeout=get_settings().intelligence_request_timeout) as client:
                response = await client.post(
                    f"https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/{endpoint}",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except Exception:
            return []
        return data.get("suggestions") or []


def _to_company(item: dict, provider_code: str) -> LegalCompany | None:
    value = item.get("value")
    data = item.get("data") or {}
    inn = data.get("inn")
    if not value or not inn:
        return None
    return LegalCompany(
        provider=provider_code,
        inn=str(inn),
        ogrn=str(data.get("ogrn") or "") or None,
        kpp=str(data.get("kpp") or "") or None,
        legal_name=str(value),
        short_name=str(data.get("name", {}).get("short_with_opf") or "") or None,
        address=str(data.get("address", {}).get("unrestricted_value") or "") or None,
        city=str(data.get("address", {}).get("data", {}).get("city") or "") or None,
        region=str(data.get("address", {}).get("data", {}).get("region_with_type") or "") or None,
        status=str(data.get("state", {}).get("status") or "") or None,
        okved=str(data.get("okved") or "") or None,
        raw_payload=item,
        confidence=0.85,
    )
