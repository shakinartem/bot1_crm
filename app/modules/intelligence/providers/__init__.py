from __future__ import annotations

from app.config import get_settings
from app.modules.intelligence.providers.api_fns import ApiFnsLegalProvider
from app.modules.intelligence.providers.base import LegalLookupProvider, WebSearchProvider
from app.modules.intelligence.providers.dadata import DaDataLegalProvider
from app.modules.intelligence.providers.google_search import GoogleSearchProvider
from app.modules.intelligence.providers.mock_legal import MockLegalProvider
from app.modules.intelligence.providers.mock_search import MockSearchProvider
from app.modules.intelligence.providers.yandex_search import YandexSearchProvider


def get_legal_provider() -> LegalLookupProvider:
    settings = get_settings()
    providers: dict[str, LegalLookupProvider] = {
        "mock": MockLegalProvider(),
        "api_fns": ApiFnsLegalProvider(),
        "dadata": DaDataLegalProvider(),
    }
    provider = providers.get(settings.legal_provider.lower(), MockLegalProvider())
    if not provider.enabled:
        return MockLegalProvider()
    return provider


def get_search_provider() -> WebSearchProvider:
    settings = get_settings()
    providers: dict[str, WebSearchProvider] = {
        "mock": MockSearchProvider(),
        "yandex": YandexSearchProvider(),
        "yandex_search": YandexSearchProvider(),
        "google": GoogleSearchProvider(),
        "google_search": GoogleSearchProvider(),
    }
    provider = providers.get(settings.search_provider.lower(), MockSearchProvider())
    if not provider.enabled:
        return MockSearchProvider()
    return provider
