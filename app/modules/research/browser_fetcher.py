from __future__ import annotations

from app.modules.research.schemas import FetchResult


BLOCK_MARKERS = ("captcha", "verify you are human", "sign in", "login", "access denied", "blocked")


async def fetch_with_browser(url: str) -> FetchResult:
    return FetchResult(
        url=url,
        status="failed",
        error_message="Browser backend is disabled",
    )


def detect_blocked_content(html: str | None) -> str | None:
    if not html:
        return None
    lowered = html.lower()
    for marker in BLOCK_MARKERS:
        if marker in lowered:
            return marker
    return None
