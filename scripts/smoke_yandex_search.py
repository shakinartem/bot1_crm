from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_yandex_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")
os.environ.setdefault("YANDEX_SEARCH_API_KEY", "test-key")
os.environ.setdefault("YANDEX_SEARCH_FOLDER_ID", "test-folder")

from app.config import get_settings  # noqa: E402
from app.modules.enrichment.schemas import FetchResult  # noqa: E402
from app.modules.intelligence.providers import get_search_provider  # noqa: E402
from app.modules.intelligence.providers.mock_search import MockSearchProvider  # noqa: E402
from app.modules.intelligence.schemas import LegalCompany  # noqa: E402
from app.modules.intelligence import website_resolver as resolver_module  # noqa: E402
from app.modules.intelligence.website_resolver import resolve_official_website  # noqa: E402


class FakeYandexProvider(MockSearchProvider):
    code = "yandex"
    title = "Fake Yandex"


async def main() -> None:
    get_settings.cache_clear()
    os.environ["SEARCH_PROVIDER"] = "yandex"
    provider = get_search_provider()
    assert provider.code == "yandex", "Yandex must be the primary active search provider"

    os.environ["SEARCH_PROVIDER"] = "google"
    get_settings.cache_clear()
    google_fallback = get_search_provider()
    assert google_fallback.code == "mock", "Google path must be disabled for MVP usage"

    legal = LegalCompany(
        provider="mock",
        inn="7701234567",
        ogrn="1027700000001",
        legal_name='ООО "ДЕНТАЛ БРАВО"',
        short_name="Дентал Браво",
        address="г. Саратов, ул. Радищева, 15",
        city="Саратов",
        region="Саратовская область",
        status="active",
        okved="86.23",
        confidence=0.9,
    )
    original_fetch = resolver_module.fetch_website

    async def fake_fetch(url: str, timeout: int = 10) -> FetchResult:
        return FetchResult(
            url=url,
            final_url=url,
            status="success",
            http_status=200,
            html="<html><title>Dental Bravo</title><body>ООО ДЕНТАЛ БРАВО ИНН 7701234567 +79990001122</body></html>",
        )

    resolver_module.fetch_website = fake_fetch
    try:
        result = await resolve_official_website(legal, FakeYandexProvider(), city="Саратов", known_phone="+79990001122")
        assert result.selected_url == "https://dental-bravo.example", "resolver must still resolve official site via Yandex-style provider"
    finally:
        resolver_module.fetch_website = original_fetch
    print("smoke_yandex_search ok")


if __name__ == "__main__":
    asyncio.run(main())
