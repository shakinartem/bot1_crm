from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.config import Settings, get_settings


CAMOUFOX_INSTALL_MESSAGE = (
    'Camoufox is not installed. Run: python -m pip install -U "camoufox[geoip]" && python -m camoufox fetch'
)
CAMOUFOX_FETCH_MESSAGE = "Camoufox browser is not fetched. Run: python -m camoufox fetch"
DISABLED_BROWSER_MESSAGE = "Browser backend is disabled. Set BROWSER_BACKEND=mock or BROWSER_BACKEND=camoufox."


@dataclass(slots=True)
class BrowserPageResult:
    url: str
    status: str = "success"
    final_url: str | None = None
    html: str | None = None
    text: str | None = None
    title: str | None = None
    error_message: str | None = None
    http_status: int | None = None
    warnings: list[str] = field(default_factory=list)


class BrowserBackendError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


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
        return BrowserPageResult(url=url, status="failed", error_message=DISABLED_BROWSER_MESSAGE)


class MockBrowserBackend(BrowserBackend):
    code = "mock"
    title = "Mock browser backend"

    def __init__(self, fixtures: dict[str, str] | None = None) -> None:
        self._fixtures = dict(fixtures or {})

    async def fetch_page(self, url: str) -> BrowserPageResult:
        html = self._fixtures.get(url)
        if html is None:
            return BrowserPageResult(
                url=url,
                status="failed",
                final_url=url,
                error_message=f"Mock browser fixture is missing for {url}",
            )
        return BrowserPageResult(url=url, status="success", final_url=url, html=html, text=html, http_status=200)


class CamoufoxBrowserBackend(BrowserBackend):
    code = "camoufox"
    title = "Camoufox browser backend"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._launcher: Any | None = None
        self._launch_error: str | None = None
        try:
            from camoufox.async_api import AsyncCamoufox  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional package
            self.enabled = False
            self._launch_error = str(exc) or exc.__class__.__name__
            return
        self.enabled = True
        self._launcher = AsyncCamoufox

    async def fetch_page(self, url: str) -> BrowserPageResult:
        if not self._launcher:
            return BrowserPageResult(
                url=url,
                status="failed",
                error_message=CAMOUFOX_INSTALL_MESSAGE,
            )
        headless = bool(self._settings.camoufox_headless)
        timeout_ms = max(1, int((self._settings.camoufox_timeout or self._settings.checko_html_timeout or 20) * 1000))
        try:
            async with self._launcher(headless=headless) as browser:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                title = await page.title()
                html = await page.content()
                body_locator = page.locator("body")
                text_timeout_ms = min(timeout_ms, 5_000)
                text = await body_locator.inner_text(timeout=text_timeout_ms)
                return BrowserPageResult(
                    url=url,
                    status="success",
                    final_url=page.url,
                    html=html,
                    text=text,
                    title=title,
                    http_status=200,
                )
        except Exception as exc:  # pragma: no cover - depends on optional package/runtime
            message = str(exc) or exc.__class__.__name__
            if _is_timeout_error(exc):
                return BrowserPageResult(url=url, status="timeout", error_message=f"Camoufox timed out after {timeout_ms} ms")
            if _is_browser_fetch_error(message):
                return BrowserPageResult(url=url, status="failed", error_message=CAMOUFOX_FETCH_MESSAGE)
            return BrowserPageResult(url=url, status="failed", error_message=f"Camoufox fetch failed: {message}")


def _is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, asyncio.TimeoutError):
        return True
    name = exc.__class__.__name__.lower()
    return "timeout" in name


def _is_browser_fetch_error(message: str) -> bool:
    lowered = message.lower()
    markers = (
        "python -m camoufox fetch",
        "executable doesn't exist",
        "browser is not fetched",
        "browser not found",
        "no such file or directory",
    )
    return any(marker in lowered for marker in markers)


def get_browser_backend(settings: Settings | None = None) -> BrowserBackend:
    settings = settings or get_settings()
    code = (settings.browser_backend or settings.research_browser_backend or "disabled").strip().lower()
    if code == "mock":
        return MockBrowserBackend()
    if code == "camoufox":
        return CamoufoxBrowserBackend(settings)
    return DisabledBrowserBackend()
