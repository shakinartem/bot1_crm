from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.modules.research.schemas import FetchResult


def normalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if not parsed.scheme:
        return f"https://{value}"
    return value


async def fetch_url(url: str, timeout: int = 10, max_chars: int = 300_000) -> FetchResult:
    normalized_url = normalize_url(url)
    if not normalized_url:
        return FetchResult(url=url, status="failed", error_message="URL is missing")

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "SHARiK CRM Research Bot/1.0"},
        ) as client:
            response = await client.get(normalized_url)
    except httpx.TimeoutException:
        return FetchResult(url=normalized_url, status="timeout", error_message="Request timed out")
    except httpx.InvalidURL:
        return FetchResult(url=normalized_url, status="failed", error_message="Invalid URL")
    except httpx.HTTPError as exc:
        return FetchResult(url=normalized_url, status="failed", error_message=str(exc))

    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        return FetchResult(
            url=normalized_url,
            final_url=str(response.url),
            status="non_html",
            http_status=response.status_code,
            error_message="Non-HTML response",
        )

    html = response.text[:max_chars]
    if response.status_code >= 400:
        return FetchResult(
            url=normalized_url,
            final_url=str(response.url),
            status="failed",
            http_status=response.status_code,
            html=html,
            text_excerpt=html[:2000],
            error_message=f"HTTP {response.status_code}",
        )

    return FetchResult(
        url=normalized_url,
        final_url=str(response.url),
        status="success",
        http_status=response.status_code,
        html=html,
        text_excerpt=html[:2000],
    )
