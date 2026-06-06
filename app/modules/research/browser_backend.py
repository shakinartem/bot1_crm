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
        from app.modules.legal_discovery.checko_html import resolve_checko_region_target

        region_key = _mock_region_fixture_key(url, region_query)
        html = self._fixtures.get(region_key) if region_key else None
        if html is None:
            html = self._fixtures.get(url)
        if html is None:
            return BrowserPageResult(
                url=url,
                status="failed",
                final_url=url,
                error_message=f"Mock browser fixture is missing for {url}",
            )
        debug_data: dict[str, Any] = {}
        if _meaningful_region_query(region_query):
            target = resolve_checko_region_target(region_query or "")
            selected_text = target.get("region_label") or (region_query or "").strip()
            debug_data.update(
                {
                    "region_resolved_district": target.get("federal_district"),
                    "region_resolved_label": target.get("region_label"),
                    "region_modal_opened": True,
                    "region_district_expanded": bool(target.get("federal_district")),
                    "region_search_filled": True,
                    "region_option_clicked": selected_text,
                    "region_checkbox_clicked": True,
                    "region_apply_clicked": True,
                    "filter_apply_clicked": True,
                    "region_filter_applied": True,
                    "selected_region_text_after_apply": selected_text,
                    "before_filter_url": url,
                    "after_filter_url": url,
                    "before_filter_title": "Checko mock before filter",
                    "after_filter_title": "Checko mock after filter",
                    "region_filter_error": None,
                }
            )
        return BrowserPageResult(
            url=url,
            status="success",
            final_url=url,
            html=html,
            text=html,
            http_status=200,
            debug_data=debug_data,
        )


class CamoufoxBrowserBackend(BrowserBackend):
    code = "camoufox"
    title = "Camoufox browser backend"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._launcher: Any | None = None
        self._launch_error: str | None = None
        try:
            from camoufox.async_api import AsyncCamoufox  # type: ignore
        except Exception as exc:  # pragma: no cover
            self.enabled = False
            self._launch_error = str(exc) or exc.__class__.__name__
            return
        self.enabled = True
        self._launcher = AsyncCamoufox

    async def fetch_page(self, url: str) -> BrowserPageResult:
        if not self._launcher:
            return BrowserPageResult(url=url, status="failed", error_message=CAMOUFOX_INSTALL_MESSAGE)
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
        except Exception as exc:  # pragma: no cover
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
                debug_data: dict[str, Any] = {
                    "before_filter_url": page.url,
                    "before_filter_title": await page.title(),
                }
                debug_data["before_region_html"] = await page.content()
                if _meaningful_region_query(region_query):
                    debug_data.update(await _apply_checko_region_filter(page, region_query or "", timeout_ms))
                debug_data["after_filter_url"] = page.url
                debug_data["after_filter_title"] = await page.title()
                debug_data["after_region_html"] = await page.content()
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
                    html=debug_data["after_region_html"],
                    text=text,
                    title=debug_data["after_filter_title"],
                    http_status=200,
                    warnings=warnings,
                    debug_data=debug_data,
                )
        except Exception as exc:  # pragma: no cover
            message = str(exc) or exc.__class__.__name__
            if _is_timeout_error(exc):
                return BrowserPageResult(url=url, status="timeout", error_message=f"Camoufox timed out after {timeout_ms} ms")
            if _is_browser_fetch_error(message):
                return BrowserPageResult(url=url, status="failed", error_message=CAMOUFOX_FETCH_MESSAGE)
            return BrowserPageResult(url=url, status="failed", error_message=f"Camoufox fetch failed: {message}")


def _is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, asyncio.TimeoutError):
        return True
    return "timeout" in exc.__class__.__name__.lower()


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
    from app.modules.legal_discovery.checko_html import resolve_checko_region_target

    target = resolve_checko_region_target(region_query)
    timeout = min(timeout_ms, 5_000)
    debug_data: dict[str, Any] = {
        "region_resolved_district": target.get("federal_district"),
        "region_resolved_label": target.get("region_label"),
        "region_modal_opened": False,
        "region_district_expanded": False,
        "region_search_filled": False,
        "region_option_clicked": None,
        "region_checkbox_clicked": False,
        "region_apply_clicked": False,
        "filter_apply_clicked": False,
        "region_filter_applied": False,
        "selected_region_text_after_apply": None,
        "region_filter_error": None,
    }
    opener = None
    try:
        opener = await _first_existing_locator(
            page,
            [
                "#location_select_button",
                "#location_select_button input",
                "input[value='Все регионы']",
                "text=Все регионы",
            ],
        )
        if opener is None:
            raise RuntimeError("Checko region opener not found")
        await opener.click(timeout=timeout)
        modal = await _first_existing_locator(page, ["#location_tree_modal", "text=Регионы и города"])
        if modal is None:
            raise RuntimeError("Checko region modal not found")
        await modal.wait_for(state="visible", timeout=timeout)
        debug_data["region_modal_opened"] = True

        if target.get("federal_district"):
            district_locator = await _first_existing_locator(
                page,
                [
                    f"text={target['federal_district']}",
                    f"[title='{target['federal_district']}']",
                ],
            )
            if district_locator is not None:
                await district_locator.click(timeout=timeout)
                debug_data["region_district_expanded"] = True
                await page.wait_for_timeout(300)

        checkbox_label, checkbox_locator = await _locate_region_checkbox(page, target)
        if checkbox_locator is None:
            search_input = await _first_existing_locator(page, ["input[placeholder='Быстрый поиск']", "input[placeholder*='Поиск']"])
            if search_input is None:
                raise RuntimeError(f"Checko region target not found for {region_query}")
            await search_input.fill(region_query, timeout=timeout)
            debug_data["region_search_filled"] = True
            await page.wait_for_timeout(600)
            checkbox_label, checkbox_locator = await _locate_region_checkbox(page, target, use_fallback_only=True)
            if checkbox_locator is None:
                raise RuntimeError(f"Checko region target not found after quick search for {region_query}")

        await checkbox_locator.click(timeout=timeout)
        debug_data["region_option_clicked"] = checkbox_label
        debug_data["region_checkbox_clicked"] = True

        modal_apply = await _first_existing_locator(page, ["button:has-text('Готово')", "text=Готово"])
        if modal_apply is None:
            raise RuntimeError("Checko region modal apply button not found")
        await modal_apply.click(timeout=timeout)
        debug_data["region_apply_clicked"] = True
        await page.wait_for_timeout(800)

        filter_apply = await _first_existing_locator(page, ["button:has-text('Применить')", "text=Применить"])
        if filter_apply is not None:
            await filter_apply.click(timeout=timeout)
            debug_data["filter_apply_clicked"] = True

        try:
            await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8_000))
        except Exception:
            await page.wait_for_timeout(1500)

        selected_text = await _read_selected_region_text(page)
        debug_data["selected_region_text_after_apply"] = selected_text
        normalized_selected = (selected_text or "").lower()
        expected_terms = [term.lower() for term in target.get("fallback_terms") or [region_query] if term]
        debug_data["region_filter_applied"] = any(term in normalized_selected for term in expected_terms) if normalized_selected else False
    except Exception as exc:
        debug_data["region_filter_error"] = str(exc) or exc.__class__.__name__
    return debug_data


async def _locate_region_checkbox(page: Any, target: dict[str, Any], *, use_fallback_only: bool = False) -> tuple[str | None, Any | None]:
    labels: list[str] = []
    if not use_fallback_only and target.get("region_label"):
        labels.append(target["region_label"])
    labels.extend(target.get("fallback_terms") or [])
    seen: set[str] = set()
    for label in labels:
        normalized = label.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        locator = await _first_existing_locator(
            page,
            [
                f"label:has-text('{normalized}') input[type='checkbox']",
                f"text={normalized}",
            ],
        )
        if locator is not None:
            return normalized, locator
    return None, None


async def _read_selected_region_text(page: Any) -> str:
    for selector in (
        "#location_select_button input",
        "#location_select_button",
        "input[value*='область']",
        "input[value*='Москва']",
    ):
        locator = page.locator(selector).first
        try:
            if await locator.count():
                try:
                    value = await locator.input_value(timeout=1000)
                    if value:
                        return value.strip()
                except Exception:
                    text = await locator.inner_text(timeout=1000)
                    if text:
                        return text.strip()
        except Exception:
            continue
    return ""


async def _first_existing_locator(page: Any, selectors: list[str]) -> Any | None:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count():
                return locator
        except Exception:
            continue
    return None


def get_browser_backend(settings: Settings | None = None) -> BrowserBackend:
    settings = settings or get_settings()
    code = (settings.browser_backend or settings.research_browser_backend or "disabled").strip().lower()
    if code == "mock":
        return MockBrowserBackend()
    if code == "camoufox":
        return CamoufoxBrowserBackend(settings)
    return DisabledBrowserBackend()
