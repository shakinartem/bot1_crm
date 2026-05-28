from __future__ import annotations

import httpx

from app.config import get_settings
from app.modules.intelligence.providers.base import WebSearchProvider
from app.modules.intelligence.schemas import SearchResult


class GoogleSearchProvider(WebSearchProvider):
    code = "google"
    title = "Google Programmable Search"

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.google_search_api_key
        self._engine_id = settings.google_search_engine_id
        self.enabled = bool(self._api_key and self._engine_id)

    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[SearchResult]:
        if not self.enabled:
            return []
        params = {
            "key": self._api_key,
            "cx": self._engine_id,
            "q": query,
            "num": min(limit, 10),
        }
        try:
            async with httpx.AsyncClient(timeout=get_settings().intelligence_request_timeout) as client:
                response = await client.get("https://www.googleapis.com/customsearch/v1", params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return []
        items: list[SearchResult] = []
        for index, item in enumerate(payload.get("items") or [], start=1):
            url = item.get("link")
            title = item.get("title")
            if not url or not title:
                continue
            items.append(
                SearchResult(
                    title=str(title),
                    url=str(url),
                    snippet=str(item.get("snippet") or "") or None,
                    source=self.code,
                    rank=index,
                    raw_payload=item,
                )
            )
        return items[:limit]
