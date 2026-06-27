#!/usr/bin/env python
"""Smoke tests for Telegram CSV import flow."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.modules.imports.handlers import (
    _render_preview_text,
    _render_report_text,
    MODE_LABELS,
)
from app.modules.imports.csv_company_import import (
    CsvCompanyImportResult,
    CsvPreviewResult,
    preview_csv,
)


def test_render_preview_text():
    """Test preview rendering does not exceed 3500 chars."""
    csv_content = "name,inn,phone\nООО Тест,7712345678,+74951234567\nООО Тест2,7712345679,+74951234568\n"
    preview = preview_csv(csv_content.encode("utf-8"))
    text = _render_preview_text(preview, import_mode="upsert", file_name="test.csv")
    assert isinstance(text, str)
    assert len(text) <= 3500, f"Preview text exceeds 3500 chars: {len(text)}"
    print("  ✅ Preview text <= 3500 chars")


def test_render_preview_with_warnings():
    """Test preview with warnings renders correctly."""
    csv_content = "inn,phone\n7712345678,+74951234567\n"
    preview = preview_csv(csv_content.encode("utf-8"))
    text = _render_preview_text(preview, import_mode="create_only", file_name="test.csv")
    assert isinstance(text, str)
    assert len(text) <= 3500
    print("  ✅ Preview with warnings renders correctly")


def test_render_report_text():
    """Test report rendering does not exceed 3500 chars."""
    result = CsvCompanyImportResult(
        total_rows=10,
        imported_count=5,
        updated_count=2,
        duplicate_count=1,
        skipped_count=1,
        error_count=1,
        warnings=["Test warning"],
    )
    text = _render_report_text(result, "test.csv", "upsert")
    assert isinstance(text, str)
    assert len(text) <= 3500, f"Report text exceeds 3500 chars: {len(text)}"
    print("  ✅ Report text <= 3500 chars")


def test_mode_labels():
    """Test mode labels are correct."""
    assert MODE_LABELS["create_only"] == "Только новые"
    assert MODE_LABELS["update_existing"] == "Обновить существующие"
    assert MODE_LABELS["upsert"] == "Создать/обновить"
    print("  ✅ Mode labels are correct")


def test_preview_shows_columns_and_stats():
    """Test preview includes column info and stats."""
    csv_content = "name,inn,phone,website,city\nООО Тест,7712345678,+74951234567,example.ru,Москва\n"
    preview = preview_csv(csv_content.encode("utf-8"))
    text = _render_preview_text(preview, import_mode="upsert", file_name="test.csv")
    assert "Всего строк" in text, f"Should show 'Всего строк', got: {text[:500]}"
    assert "ИНН" in text, "Should show INN count"
    assert "phone" in text.lower() or "тел" in text.lower() or "телефон" in text.lower(), "Should show phone info"
    print("  ✅ Preview shows columns and stats")


def test_preview_empty_file():
    """Test empty CSV preview handling."""
    csv_content = ""
    preview = preview_csv(csv_content.encode("utf-8"))
    assert preview.total_rows == 0
    assert preview.can_import is False
    assert len(preview.warnings) > 0
    print("  ✅ Empty CSV handled in preview")


def main():
    """Run all smoke tests."""
    print("\n🧪 Smoke tests: Telegram CSV import")
    print("=" * 40)
    
    test_render_preview_text()
    test_render_preview_with_warnings()
    test_render_report_text()
    test_mode_labels()
    test_preview_shows_columns_and_stats()
    test_preview_empty_file()
    
    print("=" * 40)
    print("✅ smoke_telegram_csv_import ok")
    print()


if __name__ == "__main__":
    main()