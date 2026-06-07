from __future__ import annotations

import unittest
from pathlib import Path

from app.modules.legal_discovery.checko_html import CheckoHtmlLegalDiscoveryProvider
from app.modules.legal_discovery.checko_parser import CheckoListItem, parse_checko_profile_page
from app.modules.legal_discovery.handlers import TELEGRAM_PREVIEW_LIMIT, _render_preview
from app.modules.legal_discovery.schemas import LegalDiscoveredCompany, LegalDiscoveryPreview, LegalDiscoveryPreviewItem
from app.modules.crm.location_utils import extract_region_city_from_address


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class CheckoProfileParserTests(unittest.TestCase):
    def test_parse_profile_extracts_clean_names_status_address_and_contacts(self) -> None:
        profile = parse_checko_profile_page(_load_fixture("checko_profile_center_family_stomatology.html"))

        self.assertEqual(profile.short_name, 'ООО "ЦЕНТР СЕМЕЙНОЙ СТОМАТОЛОГИИ"')
        self.assertIn("ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ", profile.legal_name or "")
        self.assertEqual(profile.inn, "3906346966")
        self.assertEqual(profile.ogrn, "1173926000819")
        self.assertEqual(profile.status, "active")
        self.assertIn("Калининградская область", profile.legal_address or "")
        self.assertIn("+74012523698", profile.phones)
        self.assertIn("karen-8708@mail.ru", profile.emails)
        self.assertTrue(any(site in {"http://stomcenter39.ru", "https://stomcenter39.ru", "stomcenter39.ru"} for site in profile.websites))
        self.assertIn("https://t.me/stomcenter39", profile.telegram_links)
        self.assertNotIn("—", profile.telegram_links)

    def test_parse_profile_name_does_not_use_timeline_history_text(self) -> None:
        profile = parse_checko_profile_page(_load_fixture("checko_profile_center_family_stomatology.html"))

        self.assertNotIn("изменено с", (profile.short_name or "").lower())
        self.assertNotIn("изменено с", (profile.legal_name or "").lower())
        self.assertNotIn("полное наименование изменено", (profile.short_name or "").lower())
        self.assertNotIn("полное наименование изменено", (profile.legal_name or "").lower())

    def test_extract_region_city_from_address_supports_common_patterns(self) -> None:
        self.assertEqual(
            extract_region_city_from_address("410015, Саратовская область, г. Саратов, ул. Радищева, 15"),
            {"region": "Саратовская область", "city": "Саратов"},
        )
        self.assertEqual(
            extract_region_city_from_address("644010, Омская область, г. Омск, ул. Ленина, 3"),
            {"region": "Омская область", "city": "Омск"},
        )
        self.assertEqual(
            extract_region_city_from_address("236005, Калининградская область, г. Калининград, ул. Минусинская, д. 22"),
            {"region": "Калининградская область", "city": "Калининград"},
        )
        self.assertEqual(
            extract_region_city_from_address("121059, г. Москва, бул. Украинский, 6"),
            {"region": "Москва", "city": "Москва"},
        )
        self.assertEqual(
            extract_region_city_from_address("191000, г. Санкт-Петербург, Невский проспект, 1"),
            {"region": "Санкт-Петербург", "city": "Санкт-Петербург"},
        )

    def test_merge_keeps_good_list_name_when_profile_name_is_suspicious(self) -> None:
        provider = CheckoHtmlLegalDiscoveryProvider()
        item = CheckoListItem(
            legal_name='ООО "НАДЕЖНОЕ ИМЯ"',
            short_name='ООО "НАДЕЖНОЕ ИМЯ"',
            profile_url="https://checko.ru/company/test-1173926000819",
            address="236005, Калининградская область, г. Калининград, ул. Минусинская, д. 22",
            raw_text='ООО "НАДЕЖНОЕ ИМЯ"',
        )
        profile = parse_checko_profile_page(_load_fixture("checko_profile_center_family_stomatology.html"))
        profile.short_name = 'Полное наименование изменено с "СТАРОЕ" на "НОВОЕ"'

        merged = provider._merge_item(item=item, profile=profile, okved_code="86.23", okved_title="Стоматология", requested_region=None)

        self.assertEqual(merged.short_name, 'ООО "НАДЕЖНОЕ ИМЯ"')

    def test_preview_render_is_compact_and_has_no_duplicate_inn(self) -> None:
        company = LegalDiscoveredCompany(
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
        )
        preview = LegalDiscoveryPreview(
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
            items=[LegalDiscoveryPreviewItem(status="new", company=company)],
            debug_info={},
        )

        rendered = _render_preview(preview, compact=True)

        self.assertLessEqual(len(rendered), TELEGRAM_PREVIEW_LIMIT)
        self.assertIn('ООО "МЦ ИНТЕРДЕНТОС" — Королёв, Московская область — ИНН 5018179703 — действующая', rendered)
        self.assertEqual(rendered.count("ИНН 5018179703"), 1)


if __name__ == "__main__":
    unittest.main()
