from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_legal_discovery_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("STORAGE_PATH", "./storage")
os.environ.setdefault("AI_PROVIDER", "fallback")
os.environ.setdefault("LEGAL_DISCOVERY_PROVIDER", "mock")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.crm.service import get_company  # noqa: E402
from app.modules.legal_discovery.keyboards import discovery_preview_markup  # noqa: E402
from app.modules.legal_discovery.handlers import _render_preview, build_discovery_browser_error_text  # noqa: E402
from app.modules.legal_discovery.service import import_legal_discovery_preview, preview_callback_token, run_legal_discovery_preview  # noqa: E402


async def verify_service() -> str:
    async with async_session_factory() as session:
        preview = await run_legal_discovery_preview(
            session,
            query="",
            okved_code="86.23",
            limit=25,
            provider_code="mock",
        )
        assert preview.total_found == 25, "mock preview must return 25 items"
        assert preview.with_inn_count >= 1, "preview must count companies with INN"
        assert preview.active_count >= 1, "preview must count active companies"
        assert preview.new_count >= 1, "preview must include new companies"

        first_import = await import_legal_discovery_preview(session, preview.preview_id, "active_new")
        assert first_import.added_count >= 1, "import must add companies"
        company = await get_company(session, first_import.added_company_ids[0])
        assert company is not None and company.contacts, "import must create contact points"
        assert company.decision_makers, "import must create a decision maker when director exists"

        second_import = await import_legal_discovery_preview(session, preview.preview_id, "active_new")
        assert second_import.added_count == 0, "repeated import must not create duplicates"
        short_import = await import_legal_discovery_preview(session, preview_callback_token(preview.preview_id), "active_new")
        assert short_import.added_count == 0, "short preview token must resolve to the same preview"
        return preview.preview_id


def verify_api() -> None:
    with TestClient(app) as client:
        preview = client.post(
            "/api/legal-discovery/search",
            json={
                "query": "",
                "okved_code": "86.23",
                "limit": 10,
                "provider": "mock",
            },
        )
        assert preview.status_code == 200, "search endpoint must work"
        preview_payload = preview.json()
        assert preview_payload["total_found"] == 10, "API preview must honor limit"

        popular = client.get("/api/legal-discovery/okved/popular")
        assert popular.status_code == 200, "popular OKVED endpoint must work"

        imported = client.post(
            "/api/legal-discovery/import",
            json={"preview_id": preview_payload["preview_id"], "mode": "active_new", "include_weak": False},
        )
        assert imported.status_code == 200, "import endpoint must work"

        os.environ["LEGAL_DISCOVERY_PROVIDER"] = "checko_html"
        os.environ["CHECKO_HTML_ENABLED"] = "1"
        os.environ["BROWSER_BACKEND"] = "disabled"
        get_settings.cache_clear()
        browser_error = client.post(
            "/api/legal-discovery/search",
            json={
                "query": "стоматология",
                "okved_code": "86.23",
                "limit": 1,
                "provider": "checko_html",
            },
        )
        assert browser_error.status_code in {400, 503}, "browser backend failure must be controlled"
        assert "browser backend failed" in browser_error.json()["detail"].lower(), "API must expose readable backend failure"


def verify_browser_error_texts() -> None:
    timeout_text = build_discovery_browser_error_text(RuntimeError("Camoufox timed out after 20000 ms"))
    assert "слишком долго" in timeout_text.lower(), "timeout must render as a manager-facing timeout hint"

    install_text = build_discovery_browser_error_text(RuntimeError("Camoufox is not installed"))
    assert "camoufox fetch" in install_text.lower(), "install error must keep setup instructions"

    runtime_text = build_discovery_browser_error_text(RuntimeError("Camoufox fetch failed: [WinError 5] Access denied"))
    assert "camoufox запустился" in runtime_text.lower(), "runtime launch error must not be shown as install guidance"


def verify_preview_markup() -> None:
    markup = discovery_preview_markup("12345678")
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert "Импортировать активные новые" in labels, "preview button labels must be localized"
    assert "Импортировать все новые" in labels, "preview button labels must be localized"
    assert "Импортировать с телефоном или сайтом" in labels, "preview button labels must be localized"
    assert "Экспорт preview CSV" in labels, "preview button labels must be localized"
    for row in markup.inline_keyboard:
        for button in row:
            assert button.callback_data is not None and len(button.callback_data.encode("utf-8")) <= 64, (
                "preview callback_data must fit Telegram 64-byte limit"
            )


async def verify_preview_render() -> None:
    async with async_session_factory() as session:
        preview = await run_legal_discovery_preview(
            session,
            query="",
            okved_code="86.23",
            limit=5,
            provider_code="mock",
        )
    rendered = _render_preview(preview)
    assert "Найдено компаний" in rendered, "preview wording must say companies"
    assert "Статус неизвестен" in rendered, "preview must include unknown status counter"
    assert "Отфильтровано по региону" in rendered, "preview must include region filter counter"
    assert "Отброшено как не компания" in rendered, "preview must include skipped non-company counter"
    assert "Медицинская и стоматологическая практика" not in rendered, "preview must not show category-like rows"


async def main() -> None:
    smoke_db = ROOT / "app_legal_discovery_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()
    await verify_service()
    verify_api()
    verify_browser_error_texts()
    verify_preview_markup()
    await verify_preview_render()
    print("smoke_legal_discovery ok")


if __name__ == "__main__":
    asyncio.run(main())
