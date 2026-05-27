from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.modules.enrichment.schemas import FetchResult


MAX_HTML_CHARS = 300_000
USER_AGENT = "SHARiK CRM Research Bot/1.0"


def normalize_website_url(url: str) -> str:
    cleaned = (url or "").strip()
    if not cleaned:
        raise ValueError("Website URL is empty")
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Website URL is invalid")
    return cleaned


async def fetch_website(url: str, timeout: int = 10) -> FetchResult:
    try:
        normalized = normalize_website_url(url)
    except ValueError as exc:
        return FetchResult(url=(url or "").strip(), status="failed", error_message=str(exc))

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = await client.get(normalized)
    except httpx.TimeoutException:
        return FetchResult(url=normalized, status="failed", error_message="Website request timed out")
    except (httpx.InvalidURL, ValueError):
        return FetchResult(url=normalized, status="failed", error_message="Website URL is invalid")
    except httpx.HTTPError as exc:
        return FetchResult(url=normalized, status="failed", error_message=f"Website request failed: {exc}")

    content_type = (response.headers.get("content-type") or "").lower()
    final_url = str(response.url)
    if response.status_code >= 400:
        return FetchResult(
            url=normalized,
            final_url=final_url,
            status="failed",
            http_status=response.status_code,
            error_message=f"Website returned HTTP {response.status_code}",
        )

    if "html" not in content_type:
        return FetchResult(
            url=normalized,
            final_url=final_url,
            status="failed",
            http_status=response.status_code,
            error_message="Website response is not HTML",
        )

    html = response.text[:MAX_HTML_CHARS]
    return FetchResult(
        url=normalized,
        final_url=final_url,
        status="success",
        http_status=response.status_code,
        html=html,
    )
