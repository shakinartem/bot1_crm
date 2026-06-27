from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_maps_research.db")
os.environ.setdefault("AI_PROVIDER", "fallback")
os.environ.setdefault("LEGAL_DISCOVERY_PROVIDER", "mock")

from app.database import create_db_schema, async_session_factory  # noqa: E402
from app.modules.research.maps_research import score_yandex_maps_card  # noqa: E402


class DummyCompany:
    address = "Москва, проспект Мира, 1"
    city = "Москва"
    name = "ООО Тест"
    legal_name = "ООО Тест"
    phone = "+74951234567"
    website = "https://example.ru"
    inn = "7712345678"


class DummyScore:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def run() -> None:
    _score = {
        "title": "ООО Тест — Москва, проспект Мира, 1 | Яндекс Карты",
        "snippet": "+7 495 123-45-67 | example.ru",
        "url": "https://yandex.ru/maps/org/123",
        "rating": 4.5,
        "reviews_count": 120,
        "photos_present": True,
        "website_present": True,
        "phone_present": True,
        "address_present": True,
    }
    score = score_yandex_maps_card(DummyCompany(), _score)
    assert 0 <= score.total_score <= 100, score.total_score
    assert score.status in {"verified", "candidate", "mismatch", "not_found"}, score.status

    bad = score_yandex_maps_card(DummyCompany(), {"title": "что-то другое"})
    assert bad.total_score >= 0

    print("smoke_maps_research ok")


if __name__ == "__main__":
    run()