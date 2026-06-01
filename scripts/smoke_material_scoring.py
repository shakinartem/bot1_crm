from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.sales_intelligence.scoring import calculate_material_quality_score


def main() -> None:
    company_context = {
        "company_id": 1,
        "website": {
            "url": "https://example-clinic.test",
            "reachable": True,
            "confidence": 0.52,
            "has_phone": True,
            "has_email": False,
            "has_form": True,
            "has_messenger": False,
            "has_cta": False,
            "has_online_booking": False,
            "has_services": True,
            "has_team": False,
            "has_reviews": False,
            "has_privacy_policy": True,
        },
        "socials": {
            "links": ["https://vk.com/example_clinic"],
            "platforms": [],
            "active": False,
            "has_trust_content": False,
        },
        "maps": {
            "has_listing": True,
            "platforms": ["yandex"],
            "has_reviews": False,
            "rating": None,
            "contact_consistency": True,
            "has_photos": False,
        },
        "trust": {
            "has_decision_maker": True,
            "has_legal_identifiers": True,
            "has_reviews": False,
            "has_team": False,
            "has_licenses": False,
        },
        "contacts": {
            "phones": ["+7 900 000-00-00"],
            "emails": ["hello@example-clinic.test"],
            "messengers": [],
            "address": "Saratov, Demo street, 1",
        },
    }

    score = calculate_material_quality_score(company_context)
    assert score.website_score == 60
    assert score.socials_score == 25
    assert score.maps_score == 50
    assert score.trust_score == 62
    assert score.conversion_score == 43
    assert score.contact_score == 86
    assert score.total_score == 56
    assert score.grade == "normal"

    sparse_score = calculate_material_quality_score(
        {
            "company_id": 2,
            "website": {
                "url": "https://sparse.test",
                "reachable": True,
                "confidence": "unknown",
                "has_phone": False,
                "has_email": False,
                "has_form": False,
                "has_messenger": False,
                "has_cta": False,
                "has_online_booking": False,
                "has_services": False,
                "has_team": False,
                "has_reviews": False,
                "has_privacy_policy": False,
            },
            "contacts": {},
        }
    )
    assert sparse_score.website_score >= 0
    assert sparse_score.total_score >= 0
    assert any("missing required top-level sections" in item.lower() for item in sparse_score.risks)
    assert any("could not be parsed" in item.lower() for item in sparse_score.risks)
    assert any("'socials'" in item.lower() for item in sparse_score.next_improvements)
    print("smoke_material_scoring ok")


if __name__ == "__main__":
    main()
