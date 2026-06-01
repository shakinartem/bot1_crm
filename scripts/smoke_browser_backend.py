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
    CamoufoxBrowserBackend,
    DisabledBrowserBackend,
    MockBrowserBackend,
    get_browser_backend,
)


async def main() -> None:
    disabled = DisabledBrowserBackend()
    try:
        await disabled.fetch_page("https://checko.ru/company/select?code=862300")
    except RuntimeError as exc:
        assert "disabled" in str(exc).lower(), "disabled backend must raise a friendly error"
    else:  # pragma: no cover - defensive
        raise AssertionError("disabled backend must fail")

    mock = MockBrowserBackend({"https://checko.test/list": "<html><body>ok</body></html>"})
    page = await mock.fetch_page("https://checko.test/list")
    assert page.html == "<html><body>ok</body></html>", "mock backend must return fixture html"

    selected = get_browser_backend(Settings(BROWSER_BACKEND="mock"))
    assert selected.code == "mock", "factory must select mock backend"

    camoufox = CamoufoxBrowserBackend(Settings(BROWSER_BACKEND="camoufox"))
    if not getattr(camoufox, "_launcher", None):
        try:
            await camoufox.fetch_page("https://checko.ru")
        except RuntimeError as exc:
            assert "camoufox" in str(exc).lower(), "missing camoufox must fail at runtime with a friendly error"
        else:  # pragma: no cover - defensive
            raise AssertionError("camoufox backend must fail without package")

    print("smoke_browser_backend ok")


if __name__ == "__main__":
    asyncio.run(main())
