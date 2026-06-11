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

from sqlalchemy import select  # noqa: E402

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.crm.models import Company  # noqa: E402
from app.modules.legal_discovery.handlers import (  # noqa: E402
    DiscoveryStates,
    TELEGRAM_PREVIEW_LIMIT,
    _render_preview,
    build_message_too_long_fallback_text,
    truncate_telegram_text,
)
from app.modules.legal_discovery.keyboards import discovery_preview_markup, discovery_zero_result_markup  # noqa: E402
from app.modules.legal_discovery.schemas import LegalDiscoveredCompany, LegalDiscoveryPreview, LegalDiscoveryPreviewItem  # noqa: E402
from app.modules.legal_discovery.service import import_legal_discovery_preview, preview_callback_token, run_legal_discovery_preview  # noqa: E402


async def main() -> None:
    smoke_db = ROOT / "app_legal_discovery_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()

    assert not hasattr(DiscoveryStates, "city"), "Telegram flow should no longer wait for region/city"

    async with async_session_factory() as session:
        preview = await run_legal_discovery_preview(
            session,
            query="",
            okved_code="86.23",
            limit=25,
            provider_code="mock",
        )
        assert preview.total_found == 25
        rendered = _render_preview(preview, compact=True)
        assert len(rendered) <= TELEGRAM_PREVIEW_LIMIT
        assert "Регион: не используется в Checko" in rendered
        assert "Отфильтровано по региону" not in rendered
        assert "Первые 5 результатов" in rendered

        imported = await import_legal_discovery_preview(session, preview.preview_id, "active_new")
        assert imported.added_count >= 1
        company = await session.scalar(select(Company).where(Company.id == imported.added_company_ids[0]))
        assert company is not None
        assert company.lead_fit_group is not None
        assert company.lead_fit_score is not None

        second_import = await import_legal_discovery_preview(session, preview_callback_token(preview.preview_id), "active_new")
        assert second_import.added_count == 0

    markup = discovery_zero_result_markup()
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert "Повторить без региона" not in labels
    assert "Mock / Dev" in labels

    preview_markup = discovery_preview_markup("12345678")
    preview_labels = [button.text for row in preview_markup.inline_keyboard for button in row]
    assert "Импортировать активные новые" in preview_labels
    assert "Импортировать все новые" in preview_labels

    shortened = truncate_telegram_text("x" * (TELEGRAM_PREVIEW_LIMIT + 100))
    assert len(shortened) == TELEGRAM_PREVIEW_LIMIT

    fallback = build_message_too_long_fallback_text("x" * (TELEGRAM_PREVIEW_LIMIT + 500))
    assert len(fallback) <= TELEGRAM_PREVIEW_LIMIT
    assert "Проверьте debug/CSV" in fallback

    custom_preview = LegalDiscoveryPreview(
        preview_id="preview-test",
        query="стоматология",
        okved_code="86.23",
        provider="checko_html",
        total_found=1,
        active_count=1,
        inactive_count=0,
        unknown_status_count=0,
        with_inn_count=1,
        with_ogrn_count=1,
        with_phone_count=1,
        with_email_count=0,
        with_website_count=1,
        with_socials_count=0,
        with_director_count=0,
        with_founders_count=0,
        new_count=1,
        duplicate_count=0,
        weak_count=0,
        items=[
            LegalDiscoveryPreviewItem(
                status="new",
                company=LegalDiscoveredCompany(
                    provider="checko_html",
                    legal_name='ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МЦ ИНТЕРДЕНТОС"',
                    short_name='ООО "МЦ ИНТЕРДЕНТОС"',
                    inn="5018179703",
                    ogrn="1234567890123",
                    city="Королёв",
                    region="Московская область",
                    status="active",
                    phones=["+74951234567"],
                    websites=["https://interdentos.example"],
                    confidence="high",
                ),
            )
        ],
        debug_info={},
    )
    rendered_custom = _render_preview(custom_preview, compact=True)
    assert rendered_custom.count("ИНН 5018179703") == 1
    assert 'ООО "МЦ ИНТЕРДЕНТОС" — Королёв, Московская область — ИНН 5018179703 — действующая' in rendered_custom
    assert len(rendered_custom) <= TELEGRAM_PREVIEW_LIMIT

    print("smoke_legal_discovery ok")


if __name__ == "__main__":
    asyncio.run(main())
