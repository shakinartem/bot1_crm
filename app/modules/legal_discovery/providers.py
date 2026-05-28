from __future__ import annotations

from typing import Protocol

from app.config import Settings, get_settings
from app.modules.legal_discovery.mock_provider import MockLegalDiscoveryProvider
from app.modules.legal_discovery.schemas import LegalDiscoveredCompany


class LegalDiscoveryProvider(Protocol):
    code: str
    title: str
    enabled: bool

    async def search_companies(
        self,
        query: str,
        city: str | None = None,
        region: str | None = None,
        limit: int = 50,
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
        city: str | None = None,
        region: str | None = None,
        limit: int = 50,
    ) -> list[LegalDiscoveredCompany]:
        return []


def get_legal_discovery_provider(settings: Settings | None = None) -> LegalDiscoveryProvider:
    settings = settings or get_settings()
    code = settings.legal_discovery_provider.lower().strip()
    if code == "mock":
        return MockLegalDiscoveryProvider()
    if code == "api_fns" and settings.api_fns_key:
        return DisabledLegalDiscoveryProvider("api_fns", "API-ФНС")
    if code == "dadata" and settings.dadata_token:
        return DisabledLegalDiscoveryProvider("dadata", "DaData")
    if code == "api_fns":
        return DisabledLegalDiscoveryProvider("api_fns", "API-ФНС")
    if code == "dadata":
        return DisabledLegalDiscoveryProvider("dadata", "DaData")
    return MockLegalDiscoveryProvider()
