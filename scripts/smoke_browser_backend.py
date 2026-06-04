from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_browser_backend_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")

from app.config import Settings  # noqa: E402
from app.modules.research.browser_backend import (  # noqa: E402
    CAMOUFOX_FETCH_MESSAGE,
    CAMOUFOX_INSTALL_MESSAGE,
    CamoufoxBrowserBackend,
    DisabledBrowserBackend,
    MockBrowserBackend,
    get_browser_backend,
)


async def main() -> None:
    disabled = DisabledBrowserBackend()
    disabled_page = await disabled.fetch_page("https://checko.ru/company/select?code=862300")
    assert disabled_page.status == "failed", "disabled backend must return failed status"
    assert disabled_page.error_message and "disabled" in disabled_page.error_message.lower(), "disabled backend must explain configuration"

    mock = MockBrowserBackend({"https://checko.test/list": "<html><body>ok</body></html>"})
    page = await mock.fetch_page("https://checko.test/list")
    assert page.status == "success", "mock backend must succeed for known fixture"
    assert page.html == "<html><body>ok</body></html>", "mock backend must return fixture html"

    missing_mock_page = await mock.fetch_page("https://checko.test/missing")
    assert missing_mock_page.status == "failed", "missing mock fixture must return failed status"
    assert missing_mock_page.error_message and "fixture is missing" in missing_mock_page.error_message.lower(), "missing fixture must be readable"

    selected = get_browser_backend(Settings(BROWSER_BACKEND="mock"))
    assert selected.code == "mock", "factory must select mock backend"

    camoufox = CamoufoxBrowserBackend(Settings(BROWSER_BACKEND="camoufox", CAMOUFOX_TIMEOUT=1, CAMOUFOX_HEADLESS=True))
    camoufox_page = await camoufox.fetch_page("data:text/html,<html><body>camoufox smoke</body></html>")
    if camoufox_page.status == "success":
        assert camoufox_page.title is not None, "camoufox success must include title"
        assert camoufox_page.final_url and camoufox_page.final_url.startswith("data:text/html"), "camoufox success must preserve final url"
    else:
        assert camoufox_page.error_message in {CAMOUFOX_INSTALL_MESSAGE, CAMOUFOX_FETCH_MESSAGE} or (
            camoufox_page.error_message and "camoufox" in camoufox_page.error_message.lower()
        ), "camoufox failure must stay readable"

    print("smoke_browser_backend ok")


if __name__ == "__main__":
    asyncio.run(main())
