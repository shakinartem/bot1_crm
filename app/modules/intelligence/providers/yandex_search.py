from __future__ import annotations

import httpx

from app.config import get_settings
from app.modules.intelligence.providers.base import WebSearchProvider
from app.modules.intelligence.schemas import SearchResult


class YandexSearchProvider(WebSearchProvider):
    code = "yandex"
    title = "Yandex Search API"

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.yandex_search_api_key
        self._folder_id = settings.yandex_search_folder_id
        self.enabled = bool(self._api_key and self._folder_id)

    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[SearchResult]:
        if not self.enabled:
            return []
        params = {
            "folderid": self._folder_id,
            "apikey": self._api_key,
            "query": query,
            "format": "json",
            "lr": 213,
        }
        try:
            async with httpx.AsyncClient(timeout=get_settings().intelligence_request_timeout) as client:
                response = await client.get("https://yandex.ru/search/xml", params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return []

        docs = payload.get("response", {}).get("results", {}).get("grouping", {}).get("groups", [])
        items: list[SearchResult] = []
        for index, group in enumerate(docs[:limit], start=1):
            doc = group.get("doc") or {}
            url = doc.get("url")
            title = doc.get("title")
            if not url or not title:
                continue
            items.append(
                SearchResult(
                    title=str(title),
                    url=str(url),
                    snippet=str(doc.get("headline") or "") or None,
                    source=self.code,
                    rank=index,
                    raw_payload=doc,
                )
            )
        return items
