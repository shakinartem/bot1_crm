from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import Settings, get_settings


@dataclass(slots=True)
class BrowserPageResult:
    url: str
    final_url: str | None = None
    html: str | None = None
    http_status: int | None = None
    warnings: list[str] = field(default_factory=list)


class BrowserBackend:
    code = "base"
    title = "Browser backend"
    enabled = True

    async def fetch_page(self, url: str) -> BrowserPageResult:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class DisabledBrowserBackend(BrowserBackend):
    code = "disabled"
    title = "Disabled browser backend"
    enabled = False

    async def fetch_page(self, url: str) -> BrowserPageResult:
        raise RuntimeError("Browser backend is disabled. Set BROWSER_BACKEND=mock or install Camoufox.")


class MockBrowserBackend(BrowserBackend):
    code = "mock"
    title = "Mock browser backend"

    def __init__(self, fixtures: dict[str, str] | None = None) -> None:
        self._fixtures = dict(fixtures or {})

    async def fetch_page(self, url: str) -> BrowserPageResult:
        html = self._fixtures.get(url)
        if html is None:
            raise RuntimeError(f"Mock browser fixture is missing for {url}")
        return BrowserPageResult(url=url, final_url=url, html=html, http_status=200)


class CamoufoxBrowserBackend(BrowserBackend):
    code = "camoufox"
    title = "Camoufox browser backend"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._launcher: Any | None = None
        self._launch_error: str | None = None
        try:
            from camoufox.sync_api import Camoufox  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional package
            self.enabled = False
            self._launch_error = str(exc) or exc.__class__.__name__
            return
        self.enabled = True
        self._launcher = Camoufox

    async def fetch_page(self, url: str) -> BrowserPageResult:
        if not self._launcher:
            raise RuntimeError(
                "Camoufox browser backend is unavailable. Install the 'camoufox' package or switch BROWSER_BACKEND."
            )
        raise RuntimeError("Camoufox runtime fetching is not wired in this environment yet.")


def get_browser_backend(settings: Settings | None = None) -> BrowserBackend:
    settings = settings or get_settings()
    code = (settings.browser_backend or settings.research_browser_backend or "disabled").strip().lower()
    if code == "mock":
        return MockBrowserBackend()
    if code == "camoufox":
        return CamoufoxBrowserBackend(settings)
    return DisabledBrowserBackend()
