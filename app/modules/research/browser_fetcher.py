from __future__ import annotations

from app.config import get_settings
from app.modules.research.browser_backend import get_browser_backend
from app.modules.research.schemas import FetchResult


BLOCK_MARKERS = ("captcha", "verify you are human", "sign in", "login", "access denied", "blocked")


async def fetch_with_browser(url: str) -> FetchResult:
    backend = get_browser_backend(get_settings())
    try:
        page = await backend.fetch_page(url)
    except RuntimeError as exc:
        return FetchResult(
            url=url,
            status="failed",
            error_message=str(exc),
        )
    finally:
        await backend.close()
    return FetchResult(
        url=url,
        final_url=page.final_url,
        status="success" if page.html else "failed",
        http_status=page.http_status,
        html=page.html,
        text_excerpt=(page.html or "")[:2000] or None,
        error_message=None if page.html else "Browser backend returned empty page",
    )


def detect_blocked_content(html: str | None) -> str | None:
    if not html:
        return None
    lowered = html.lower()
    for marker in BLOCK_MARKERS:
        if marker in lowered:
            return marker
    return None
