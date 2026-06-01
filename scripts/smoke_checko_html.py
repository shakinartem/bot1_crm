from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_checko_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")
os.environ.setdefault("LEGAL_DISCOVERY_PROVIDER", "checko_html")
os.environ.setdefault("CHECKO_HTML_ENABLED", "1")
os.environ.setdefault("BROWSER_BACKEND", "mock")
os.environ.setdefault("CHECKO_HTML_PAGE_DELAY_MS", "0")

from app.config import Settings  # noqa: E402
from app.modules.legal_discovery.checko_html import CheckoHtmlLegalDiscoveryProvider  # noqa: E402
from app.modules.legal_discovery.checko_parser import parse_checko_list_page, parse_checko_profile_page  # noqa: E402
from app.modules.legal_discovery.okved_catalog import normalize_okved_code, resolve_okved_by_query  # noqa: E402
from app.modules.research.browser_backend import MockBrowserBackend  # noqa: E402


def read_fixture(name: str) -> str:
    return (ROOT / "storage" / "imports" / name).read_text(encoding="utf-8")


async def main() -> None:
    list_html = read_fixture("checko_select_fixture.html")
    profile_html = read_fixture("checko_profile_fixture.html")

    items = parse_checko_list_page(list_html)
    assert len(items) == 2, "list parser must return two companies"
    assert items[0].profile_url and "/company/" in items[0].profile_url, "profile url must be parsed"

    profile = parse_checko_profile_page(profile_html)
    assert profile.inn == "6453001234", "profile parser must parse INN"
    assert profile.ogrn == "1026403001234", "profile parser must use JSON-LD fallback for OGRN"
    assert profile.websites == ["https://dental-bravo.example"], "website must be parsed"
    assert profile.founders and profile.founders[0].full_name == "Иванов Иван Иванович", "founder must be parsed"

    assert normalize_okved_code("86.23") == "862300", "OKVED normalization must strip punctuation"
    assert resolve_okved_by_query("стоматология").normalized_code == "862300", "popular OKVED heuristic must work"

    backend = MockBrowserBackend(
        {
            "https://checko.ru/company/select?code=862300&page=1": list_html,
            "https://checko.ru/company/1234567890": profile_html,
            "https://checko.ru/company/0987654321": profile_html.replace("6453001234", "6453009999").replace("Дентал Браво", "Смайл Клиник"),
        }
    )
    provider = CheckoHtmlLegalDiscoveryProvider(
        Settings(
            LEGAL_DISCOVERY_PROVIDER="checko_html",
            CHECKO_HTML_ENABLED="1",
            CHECKO_HTML_PAGE_DELAY_MS="0",
            CHECKO_HTML_PROFILE_ENABLED="1",
            CHECKO_HTML_BASE_URL="https://checko.ru",
        ),
        browser_backend=backend,
    )
    companies = await provider.search_companies(query="стоматология", okved_code="86.23", limit=2, city="Саратов")
    assert len(companies) == 2, "provider must return limited company list"
    assert companies[0].inn == "6453001234", "provider must merge profile requisites"
    assert companies[0].director and companies[0].director.full_name == "Иванов Иван Иванович", "director must be mapped"
    assert companies[0].confidence == "high", "company with INN and OGRN must be high confidence"

    print("smoke_checko_html ok")


if __name__ == "__main__":
    asyncio.run(main())
