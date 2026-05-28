from __future__ import annotations

from app.modules.intelligence.providers.base import WebSearchProvider
from app.modules.intelligence.schemas import SearchResult


class MockSearchProvider(WebSearchProvider):
    code = "mock"
    title = "Mock search provider"
    enabled = True

    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[SearchResult]:
        query_lower = query.lower()
        results: list[SearchResult] = []
        if "7701234567" in query_lower or "дентал браво" in query_lower:
            results.extend(
                [
                    SearchResult(
                        title="Стоматология Дентал Браво",
                        url="https://dental-bravo.example",
                        snippet="Официальный сайт стоматологической клиники в Саратове. ИНН 7701234567.",
                        source=self.code,
                        rank=1,
                        raw_payload={"mock": True},
                    ),
                    SearchResult(
                        title="Дентал Браво на Rusprofile",
                        url="https://www.rusprofile.ru/id/7701234567",
                        snippet="Юридические данные компании",
                        source=self.code,
                        rank=2,
                        raw_payload={"mock": True},
                    ),
                ]
            )
        return results[:limit]
