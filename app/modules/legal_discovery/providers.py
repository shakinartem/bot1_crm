from __future__ import annotations

from typing import Protocol

from app.config import Settings, get_settings
from app.modules.legal_discovery.checko_html import CheckoHtmlLegalDiscoveryProvider
from app.modules.legal_discovery.mock_provider import MockLegalDiscoveryProvider
from app.modules.legal_discovery.okved_catalog import normalize_okved_code, resolve_okved_by_query
from app.modules.legal_discovery.schemas import LegalDiscoveredCompany


class LegalDiscoveryProvider(Protocol):
    code: str
    title: str
    enabled: bool

    async def search_companies(
        self,
        query: str,
        okved_code: str | None = None,
        okved_title: str | None = None,
        city: str | None = None,
        region: str | None = None,
        limit: int = 50,
        page: int = 1,
        only_main_okved: bool = True,
        only_active: bool = True,
        include_profiles: bool = True,
        concurrency: int | None = None,
    ) -> list[LegalDiscoveredCompany]:
        ...


class DisabledLegalDiscoveryProvider:
    def __init__(self, code: str, title: str) -> None:
        self.code = code
        self.title = title
        self.enabled = False

    async def search_companies(
        self,
        query: str,
        okved_code: str | None = None,
        okved_title: str | None = None,
        city: str | None = None,
        region: str | None = None,
        limit: int = 50,
        page: int = 1,
        only_main_okved: bool = True,
        only_active: bool = True,
        include_profiles: bool = True,
        concurrency: int | None = None,
    ) -> list[LegalDiscoveredCompany]:
        return []


def get_legal_discovery_provider(settings: Settings | None = None) -> LegalDiscoveryProvider:
    settings = settings or get_settings()
    code = settings.legal_discovery_provider.lower().strip()
    if code == "mock":
        return MockLegalDiscoveryProvider()
    if code == "checko_html":
        return CheckoHtmlLegalDiscoveryProvider(settings)
    if code == "api_fns":
        return DisabledLegalDiscoveryProvider("api_fns", "API-FNS")
    if code == "dadata":
        return DisabledLegalDiscoveryProvider("dadata", "DaData")
    return MockLegalDiscoveryProvider()


def resolve_okved_input(query: str, okved_code: str | None = None) -> tuple[str | None, str | None]:
    normalized = normalize_okved_code(okved_code)
    if normalized:
        item = resolve_okved_by_query(normalized)
        return normalized, item.title if item else None
    guessed = resolve_okved_by_query(query)
    if guessed:
        return guessed.normalized_code, guessed.title
    return None, None
