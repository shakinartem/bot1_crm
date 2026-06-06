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
    debug_data: dict[str, Any] = field(default_factory=dict)


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

    async def fetch_checko_list_page(self, url: str, *, region_query: str | None = None) -> BrowserPageResult:
        return await self.fetch_page(url)

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

    async def fetch_checko_list_page(self, url: str, *, region_query: str | None = None) -> BrowserPageResult:
        region_key = _mock_region_fixture_key(url, region_query)
        if region_key and region_key in self._fixtures:
            html = self._fixtures[region_key]
            return BrowserPageResult(
                url=url,
                status="success",
                final_url=url,
                html=html,
                text=html,
                http_status=200,
                debug_data={
                    "region_modal_opened": True,
                    "region_search_filled": True,
                    "region_option_clicked": region_query,
                    "region_apply_clicked": True,
                    "region_filter_applied": True,
                    "region_filter_error": None,
                },
            )
        result = await self.fetch_page(url)
        if region_query and region_query.strip() and region_query.strip().lower() not in {"все регионы", "all regions"}:
            result.debug_data.update(
                {
                    "region_modal_opened": False,
                    "region_search_filled": False,
                    "region_option_clicked": None,
                    "region_apply_clicked": False,
                    "region_filter_applied": False,
                    "region_filter_error": f"Mock browser fixture is missing for region UI flow: {region_query}",
                }
            )
        return result


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
                text = ""
                warnings: list[str] = []
                try:
                    text = await body_locator.inner_text(timeout=text_timeout_ms)
                except Exception:
                    warnings.append("body_text_unavailable")
                return BrowserPageResult(
                    url=url,
                    status="success",
                    final_url=page.url,
                    html=html,
                    text=text,
                    title=title,
                    http_status=200,
                    warnings=warnings,
                )
        except Exception as exc:  # pragma: no cover - depends on optional package/runtime
            message = str(exc) or exc.__class__.__name__
            if _is_timeout_error(exc):
                return BrowserPageResult(url=url, status="timeout", error_message=f"Camoufox timed out after {timeout_ms} ms")
            if _is_browser_fetch_error(message):
                return BrowserPageResult(url=url, status="failed", error_message=CAMOUFOX_FETCH_MESSAGE)
            return BrowserPageResult(url=url, status="failed", error_message=f"Camoufox fetch failed: {message}")

    async def fetch_checko_list_page(self, url: str, *, region_query: str | None = None) -> BrowserPageResult:
        if not self._launcher:
            return BrowserPageResult(url=url, status="failed", error_message=CAMOUFOX_INSTALL_MESSAGE)
        headless = bool(self._settings.camoufox_headless)
        timeout_ms = max(1, int((self._settings.camoufox_timeout or self._settings.checko_html_timeout or 20) * 1000))
        try:
            async with self._launcher(headless=headless) as browser:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                debug_data: dict[str, Any] = {}
                before_html = await page.content()
                debug_data["before_region_html"] = before_html
                if _meaningful_region_query(region_query):
                    debug_data.update(await _apply_checko_region_filter(page, region_query or "", timeout_ms))
                after_html = await page.content()
                debug_data["after_region_html"] = after_html
                title = await page.title()
                body_locator = page.locator("body")
                text_timeout_ms = min(timeout_ms, 5_000)
                text = ""
                warnings: list[str] = []
                try:
                    text = await body_locator.inner_text(timeout=text_timeout_ms)
                except Exception:
                    warnings.append("body_text_unavailable")
                return BrowserPageResult(
                    url=url,
                    status="success",
                    final_url=page.url,
                    html=after_html,
                    text=text,
                    title=title,
                    http_status=200,
                    warnings=warnings,
                    debug_data=debug_data,
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


def _mock_region_fixture_key(url: str, region_query: str | None) -> str | None:
    if not _meaningful_region_query(region_query):
        return None
    return f"{url}::region::{(region_query or '').strip().lower()}"


def _meaningful_region_query(region_query: str | None) -> bool:
    normalized = (region_query or "").strip().lower()
    return bool(normalized and normalized not in {"все регионы", "all regions"})


async def _apply_checko_region_filter(page: Any, region_query: str, timeout_ms: int) -> dict[str, Any]:
    debug_data: dict[str, Any] = {
        "region_modal_opened": False,
        "region_search_filled": False,
        "region_option_clicked": None,
        "region_apply_clicked": False,
        "region_filter_applied": False,
        "region_filter_error": None,
    }
    try:
        field = page.locator("#location_select_button input").first
        await field.click(timeout=min(timeout_ms, 5_000))
        await page.locator("text=Регионы и города").first.wait_for(state="visible", timeout=min(timeout_ms, 5_000))
        debug_data["region_modal_opened"] = True

        search_input = page.locator("input[placeholder='Быстрый поиск']").first
        await search_input.fill(region_query, timeout=min(timeout_ms, 5_000))
        debug_data["region_search_filled"] = True
        await page.wait_for_timeout(800)

        option_label, option = await _locate_region_option(page, region_query)
        if option is None:
            raise RuntimeError(f"Region option not found for {region_query}")
        await option.click(timeout=min(timeout_ms, 5_000))
        debug_data["region_option_clicked"] = option_label

        apply_button = page.locator("button:has-text('Готово')").first
        await apply_button.click(timeout=min(timeout_ms, 5_000))
        debug_data["region_apply_clicked"] = True
        try:
            await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8_000))
        except Exception:
            await page.wait_for_timeout(1500)

        try:
            selected_value = await field.input_value(timeout=min(timeout_ms, 2_000))
        except Exception:
            selected_value = ""
        normalized_value = selected_value.strip().lower()
        normalized_query = region_query.strip().lower()
        debug_data["region_filter_applied"] = bool(normalized_value and normalized_value != "все регионы" and normalized_query in normalized_value)
    except Exception as exc:
        debug_data["region_filter_error"] = str(exc) or exc.__class__.__name__
    return debug_data


async def _locate_region_option(page: Any, region_query: str) -> tuple[str | None, Any | None]:
    candidates = [region_query.strip(), f"{region_query.strip()}ская область"]
    for label in candidates:
        locator = page.locator(f"text={label}").first
        if await locator.count():
            return label, locator
    contains_locator = page.locator(f"text=/{region_query.strip()}/i").first
    if await contains_locator.count():
        return region_query.strip(), contains_locator
    return None, None


def get_browser_backend(settings: Settings | None = None) -> BrowserBackend:
    settings = settings or get_settings()
    code = (settings.browser_backend or settings.research_browser_backend or "disabled").strip().lower()
    if code == "mock":
        return MockBrowserBackend()
    if code == "camoufox":
        return CamoufoxBrowserBackend(settings)
    return DisabledBrowserBackend()
