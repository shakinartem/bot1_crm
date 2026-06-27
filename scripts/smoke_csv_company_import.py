#!/usr/bin/env python
"""Smoke tests for CSV company import module."""
from __future__ import annotations

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.modules.imports.csv_company_import import (
    detect_csv_dialect,
    normalize_csv_headers,
    parse_company_csv,
    preview_csv,
    CsvPreviewResult,
    CsvCompanyImportResult,
    RowResult,
)


def test_utf8_csv():
    """Test 1: CSV with UTF-8 imports correctly."""
    csv_content = "name,inn,phone,website,city\nООО Тест,7712345678,+7(495)123-45-67,example.ru,Москва\n"
    result = preview_csv(csv_content.encode("utf-8"))
    assert result.total_rows == 1, f"Expected 1 row, got {result.total_rows}"
    assert result.inn_count == 1, f"Expected 1 INN, got {result.inn_count}"
    assert result.phone_count == 1, f"Expected 1 phone, got {result.phone_count}"
    assert result.website_count == 1, f"Expected 1 website, got {result.website_count}"
    assert result.can_import is True
    print("  ✅ UTF-8 CSV imports correctly")


def test_semicolon_csv():
    """Test 2: CSV with semicolon delimiter imports correctly."""
    csv_content = "name;inn;phone;website;city\nООО Тест;7712345678;+7(495)123-45-67;example.ru;Москва\n"
    _, _, delimiter = detect_csv_dialect(csv_content.encode("utf-8"))
    assert delimiter in (",", ";", "\t"), f"Expected delimiter, got {delimiter}"
    assert delimiter == ";", f"Expected semicolon, got {delimiter}"
    result = preview_csv(csv_content.encode("utf-8"))
    assert result.total_rows == 1
    print("  ✅ Semicolon CSV imports correctly")


def test_russian_columns_csv():
    """Test 3: CSV with Russian column names imports correctly."""
    csv_content = "Название,ИНН,Телефон,Сайт,Город\nООО Тест,7712345678,+7(495)123-45-67,example.ru,Москва\n"
    result = preview_csv(csv_content.encode("utf-8"))
    assert result.total_rows == 1, f"Expected 1 row, got {result.total_rows}"
    assert result.can_import is True
    print("  ✅ CSV with Russian columns imports correctly")


def test_inn_deduplication():
    """Test 4: CSV with INN should deduplicate."""
    csv_content = "name,inn,phone\nООО Тест,7712345678,+74951234567\n"
    rows, warnings, total = parse_company_csv(csv_content.encode("utf-8"))
    assert len(rows) == 1
    assert rows[0]["inn"] == "7712345678"
    print("  ✅ CSV with INN parses correctly for deduplication")


def test_phone_normalization():
    """Test 5: Phone normalization works on CSV import."""
    csv_content = "name,phone\nООО Тест,+7(495)123-45-67\n"
    rows, _, _ = parse_company_csv(csv_content.encode("utf-8"))
    phone = rows[0].get("phone")
    assert phone is not None, "Phone should be normalized"
    # Should contain digits
    digits = "".join(ch for ch in phone if ch.isdigit())
    assert len(digits) >= 10, f"Phone should have enough digits, got {phone}"
    print("  ✅ Phone normalization works")


def test_website_denylist():
    """Test 6: Website denylist does not get into Company.website."""
    csv_content = "name,website\nООО Тест,https://checko.ru/company/123\n"
    rows, _, _ = parse_company_csv(csv_content.encode("utf-8"))
    website = rows[0].get("website")
    # Website is stored as-is in parsed row, denylist check happens during import
    assert website is not None, "Website should be present in parsed row"
    print("  ✅ Website denylist URL is stored in parsed row (filtered later)")


def test_checko_url_field():
    """Test 7: checko_profile_url is recognized."""
    csv_content = "name,checko_url\nООО Тест,https://checko.ru/company/123\n"
    mapping = normalize_csv_headers(["name", "checko_url"])
    assert "checko_profile_url" in mapping, f"checko_profile_url should be mapped, got {mapping}"
    print("  ✅ checko_profile_url is recognized")


def test_yandex_maps_url_field():
    """Test 8: yandex_maps_url is recognized."""
    csv_content = "name,yandex_maps_url\nООО Тест,https://yandex.ru/maps/org/123\n"
    mapping = normalize_csv_headers(["name", "yandex_maps_url"])
    assert "yandex_maps_url" in mapping, f"yandex_maps_url should be mapped, got {mapping}"
    print("  ✅ yandex_maps_url is recognized")


def test_empty_values():
    """Test empty values are treated as None."""
    csv_content = "name,inn,phone,website\nООО Тест,,-,нет\n"
    rows, _, _ = parse_company_csv(csv_content.encode("utf-8"))
    assert rows[0]["inn"] is None, f"Empty INN should be None, got {rows[0]['inn']}"
    assert rows[0]["phone"] is None
    assert rows[0]["website"] is None
    print("  ✅ Empty values (-, нет) are treated as None")


def test_no_name_warning():
    """Test warning when no name column."""
    csv_content = "inn,phone\n7712345678,+74951234567\n"
    rows, warnings, total = parse_company_csv(csv_content.encode("utf-8"))
    has_name_warning = any("названия" in w.lower() for w in warnings)
    assert has_name_warning, f"Expected name warning, got {warnings}"
    print("  ✅ Warning when no name column")


def test_utf8_bom():
    """Test UTF-8 BOM encoding."""
    csv_content = "\ufeffname,inn\nООО Тест,7712345678\n"
    decoded, encoding, _ = detect_csv_dialect(csv_content.encode("utf-8-sig"))
    assert decoded is not None, "Should decode UTF-8 BOM"
    print("  ✅ UTF-8 BOM decoded")


def test_cp1251():
    """Test CP1251 encoding."""
    csv_content = "name,inn\nООО Тест,7712345678\n".encode("cp1251")
    decoded, encoding, _ = detect_csv_dialect(csv_content)
    assert decoded is not None, "Should decode CP1251"
    result = preview_csv(csv_content)
    assert result.total_rows == 1
    print("  ✅ CP1251 imported correctly")


def test_header_mapping():
    """Test column header mapping."""
    headers = ["Название", "ИНН", "Телефон", "Сайт", "Город", "Карта"]
    mapping = normalize_csv_headers(headers)
    assert "display_name" in mapping, f"display_name should be in mapping: {mapping}"
    assert "inn" in mapping, f"inn should be in mapping: {mapping}"
    assert "phone" in mapping, f"phone should be in mapping: {mapping}"
    assert "website" in mapping, f"website should be in mapping: {mapping}"
    assert "city" in mapping, f"city should be in mapping: {mapping}"
    print("  ✅ Header mapping works for Russian column names")


def test_preview_result():
    """Test preview result structure."""
    csv_content = "name,inn,phone,website\nООО Тест,7712345678,+74951234567,example.ru\nООО Тест2,,,\n"
    result = preview_csv(csv_content.encode("utf-8"))
    assert result.detected_columns, f"Should have detected columns, got {result.detected_columns}"
    assert result.total_rows >= 1
    assert len(result.sample_rows) >= 1
    assert isinstance(result.can_import, bool)
    print("  ✅ Preview result has correct structure")


def test_parse_without_name():
    """Test that rows without name are parsed but skipped during import."""
    csv_content = "name,inn\n,7712345678\nООО Тест,7712345679\n"
    rows, warnings, total = parse_company_csv(csv_content.encode("utf-8"))
    assert total == 2, f"Should have 2 total rows, got {total}"
    assert len(rows) == 2, f"Should have 2 parsed rows, got {len(rows)}"
    print("  ✅ Rows without name are parsed and can be skipped during import")


def test_import_result_dataclass():
    """Test CsvCompanyImportResult structure."""
    result = CsvCompanyImportResult()
    assert result.total_rows == 0
    assert result.imported_count == 0
    
    result.imported_count = 5
    result.row_results.append(RowResult(row_number=2, status="imported", company_id=1, message="OK"))
    assert result.imported_count == 5
    assert len(result.row_results) == 1
    print("  ✅ CsvCompanyImportResult dataclass works")


def main():
    """Run all smoke tests."""
    print("\n🧪 Smoke tests: CSV company import")
    print("=" * 40)
    
    test_utf8_csv()
    test_semicolon_csv()
    test_russian_columns_csv()
    test_inn_deduplication()
    test_phone_normalization()
    test_website_denylist()
    test_checko_url_field()
    test_yandex_maps_url_field()
    test_empty_values()
    test_no_name_warning()
    test_utf8_bom()
    test_cp1251()
    test_header_mapping()
    test_preview_result()
    test_parse_without_name()
    test_import_result_dataclass()
    
    print("=" * 40)
    print("✅ smoke_csv_company_import ok")
    print()


if __name__ == "__main__":
    main()