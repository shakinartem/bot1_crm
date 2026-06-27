#!/usr/bin/env python
"""Smoke tests for CSV company import API endpoints."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.modules.imports.csv_company_import import (
    import_companies_from_csv,
    preview_csv,
    CsvCompanyImportResult,
    CsvPreviewResult,
)


def test_preview_csv_function():
    """Test preview_csv returns correct structure."""
    csv_content = "name,inn,phone\nООО Тест,7712345678,+74951234567\n"
    result = preview_csv(csv_content.encode("utf-8"))
    assert isinstance(result, CsvPreviewResult)
    assert result.total_rows == 1
    assert result.can_import is True
    assert len(result.sample_rows) == 1
    print("  ✅ preview_csv returns correct structure")


def test_import_result_format():
    """Test CsvCompanyImportResult format matches API contract."""
    result = CsvCompanyImportResult(
        total_rows=10,
        imported_count=5,
        updated_count=2,
        duplicate_count=1,
        skipped_count=1,
        error_count=1,
        warnings=["Test warning"],
    )
    assert result.total_rows == 10
    assert result.imported_count == 5
    assert result.updated_count == 2
    assert result.duplicate_count == 1
    assert result.skipped_count == 1
    assert result.error_count == 1
    assert len(result.warnings) == 1
    print("  ✅ CsvCompanyImportResult format matches API contract")


def test_import_mode_literals():
    """Test that import mode literals are correct."""
    from app.modules.imports.csv_company_import import ImportMode
    import typing
    
    # Verify it's a Literal type with correct values
    values = typing.get_args(ImportMode)
    assert "create_only" in values
    assert "update_existing" in values
    assert "upsert" in values
    print("  ✅ ImportMode literals are correct")


def main():
    """Run all smoke tests."""
    print("\n🧪 Smoke tests: CSV company import API")
    print("=" * 40)
    
    test_preview_csv_function()
    test_import_result_format()
    test_import_mode_literals()
    
    print("=" * 40)
    print("✅ smoke_csv_company_import_api ok")
    print()


if __name__ == "__main__":
    main()