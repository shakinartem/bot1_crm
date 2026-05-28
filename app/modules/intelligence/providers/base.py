from __future__ import annotations

from abc import ABC, abstractmethod

from app.modules.intelligence.schemas import LegalCompany, SearchResult


class LegalLookupProvider(ABC):
    code: str = "base"
    title: str = "Base Legal Provider"
    enabled: bool = False

    @abstractmethod
    async def find_by_inn(self, inn: str) -> LegalCompany | None:
        raise NotImplementedError

    @abstractmethod
    async def search_by_name(
        self,
        name: str,
        city: str | None = None,
        region: str | None = None,
        limit: int = 10,
    ) -> list[LegalCompany]:
        raise NotImplementedError


class WebSearchProvider(ABC):
    code: str = "base"
    title: str = "Base Search Provider"
    enabled: bool = False

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[SearchResult]:
        raise NotImplementedError
