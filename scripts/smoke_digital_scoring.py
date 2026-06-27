from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./app_digital_scoring.db")
os.environ.setdefault("AI_PROVIDER", "fallback")
os.environ.setdefault("LEGAL_DISCOVERY_PROVIDER", "mock")

from app.database import create_db_schema, async_session_factory  # noqa: E402
from app.modules.crm.models import Company  # noqa: E402
from app.modules.lead_fit.service import calculate_digital_score  # noqa: E402


class DummyMapsScore:
    total_score = 42
    status = "verified"
    confidence = "normal"
    rating = 4.6
    reviews_count = 85
    blocked_reason = None
    error_message = None


class DummyWebsiteScore:
    total_score = 55


class DummyResearchContext:
    website_confidence = "high"
    website_url = "https://example.ru"
    parsed_site = None


class DummyEnrichmentContext:
    parsed_contacts = None
    parsed_socials = None
    parsed_signals = None


def run() -> None:
    company = Company(
        name="Клиника Улыбка",
        city="Москва",
        website="https://ulydka.ru",
        status="active_new",
    )

    score = calculate_digital_score(
        company,
        maps_score=DummyMapsScore(),
        website_score=DummyWebsiteScore(),
        research=DummyResearchContext(),
        enrichment=DummyEnrichmentContext(),
    )
    assert 0 <= score.total_score <= 100
    assert score.grade in {"A", "B", "C", "D", "F"}
    assert score.maps_score == 42
    assert score.website_score == 55

    zero = calculate_digital_score(
        Company(name="Пустая", city="?"),
        maps_score=None,
        website_score=None,
        research=None,
        enrichment=None,
    )
    assert 0 <= zero.total_score <= 100

    print("smoke_digital_scoring ok")


if __name__ == "__main__":
    run()