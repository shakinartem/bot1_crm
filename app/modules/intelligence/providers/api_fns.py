from __future__ import annotations

import httpx

from app.config import get_settings
from app.modules.intelligence.providers.base import LegalLookupProvider
from app.modules.intelligence.schemas import LegalCompany


class ApiFnsLegalProvider(LegalLookupProvider):
    code = "api_fns"
    title = "API FNS"

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.api_fns_base_url.rstrip("/")
        self._api_key = settings.api_fns_key
        self.enabled = bool(self._api_key)

    async def find_by_inn(self, inn: str) -> LegalCompany | None:
        if not self.enabled:
            return None
        params = {"req": inn, "key": self._api_key}
        try:
            async with httpx.AsyncClient(timeout=get_settings().intelligence_request_timeout) as client:
                response = await client.get(f"{self._base_url}/search", params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return None
        return _extract_legal_company(payload, self.code)

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
        params = {"req": query, "key": self._api_key}
        try:
            async with httpx.AsyncClient(timeout=get_settings().intelligence_request_timeout) as client:
                response = await client.get(f"{self._base_url}/search", params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return []

        items = payload.get("items") or []
        results: list[LegalCompany] = []
        for item in items[:limit]:
            candidate = _extract_legal_company({"items": [item]}, self.code)
            if candidate:
                results.append(candidate)
        return results


def _extract_legal_company(payload: dict, provider_code: str) -> LegalCompany | None:
    items = payload.get("items") or []
    if not items:
        return None
    item = items[0]
    name = item.get("ЮЛ") or item.get("name") or item.get("НаимСокрЮЛ")
    inn = item.get("ИНН") or item.get("inn")
    if not name or not inn:
        return None
    return LegalCompany(
        provider=provider_code,
        inn=str(inn),
        ogrn=str(item.get("ОГРН") or item.get("ogrn") or "") or None,
        kpp=str(item.get("КПП") or item.get("kpp") or "") or None,
        legal_name=str(name),
        short_name=str(item.get("НаимСокрЮЛ") or "") or None,
        address=str(item.get("АдресПолн") or item.get("address") or "") or None,
        city=None,
        region=None,
        status=str(item.get("Статус") or item.get("status") or "") or None,
        okved=str(item.get("ОКВЭД") or item.get("okved") or "") or None,
        raw_payload=item,
        confidence=0.8,
    )
