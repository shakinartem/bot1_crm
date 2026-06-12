from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_telegram_settings_smoke.db")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("BOT2_API_TOKEN", "")
os.environ.setdefault("ALLOW_DB_RESET", "true")
os.environ.setdefault("LEGAL_DISCOVERY_PROVIDER", "mock")

from app.database import async_session_factory, create_db_schema  # noqa: E402
from app.modules.crm.keyboards import main_menu, settings_section_menu_markup  # noqa: E402
from app.modules.crm.telegram_ux import build_system_status_snapshot, render_search_settings_text, render_system_status_text  # noqa: E402


async def main() -> None:
    smoke_db = ROOT / "app_telegram_settings_smoke.db"
    if smoke_db.exists():
        smoke_db.unlink()
    await create_db_schema()

    menu_labels = [button.text for row in main_menu().keyboard for button in row]
    assert "🔍 Поиск компаний" in menu_labels
    assert "🔍 Поиск и импорт" not in menu_labels
    assert "⚙️ Настройки" in menu_labels
    assert all("Mock" not in label for label in menu_labels)
    assert all("Dev" not in label for label in menu_labels)

    settings_labels = [button.text for row in settings_section_menu_markup(include_admin_reset=True).inline_keyboard for button in row]
    assert "ℹ️ Состояние системы" in settings_labels
    assert "🔎 Настройки поиска" in settings_labels
    assert "🧹 Очистить CRM-данные" in settings_labels
    assert "🧨 Очистить все данные" in settings_labels

    async with async_session_factory() as session:
        snapshot = await build_system_status_snapshot(session)
    status_text = render_system_status_text(snapshot)
    search_text = render_search_settings_text()
    assert "Состояние системы" in status_text
    assert "Discovery cursors" in status_text
    assert "Настройки поиска" in search_text
    assert "Настройки только для просмотра" in search_text

    print("smoke_telegram_settings ok")


if __name__ == "__main__":
    asyncio.run(main())
